# Collector: Scheduler → Cloud Run job → Routes + Weather → BigQuery

Bead: `pertamina-retail-traffic-907.7` (feature), plan bead `.2`. Schema: `docs/plans/data-schema.md`. Sites: `data/sites.csv`. Rules: `.claude/rules/data-sources.md`.

## Goal

Every 30 minutes, write the main-road traffic legs for every SPBU, plus weather per SPBU, into BigQuery. The interval is the same everywhere; only the leg length differs between urban and toll sites. History starts only when this runs, because there is no backfill. **Phase 1 is the minimum that starts collecting; everything else waits.**

## What gets measured

Names, along the direction of travel:
- **Points:** **Entry** (start, upstream), **Front** (main road in front of the SPBU), **Exit** (end, downstream).
- **Side:** only the **SPBU side** (the station's carriageway) is measured. The user checked all 10 sites on 2026-10-06 and dropped the opposite carriageway: it isn't the traffic the station sees.

| Leg | Route | Measures |
|---|---|---|
| Approach | Entry → Front | traffic on the main road before the SPBU |
| Departure | Front → Exit | traffic on the main road after the SPBU |

Both legs are core and RMI-compatible.

**One `computeRoutes` call returns both legs.** The call runs Entry → Front → Exit, with Front as a stop (`via: false`, lat/lng with heading), so the route stays on the main road and the response splits at Front.

| Site type | Sides | Leg length | Calls per slot |
|---|---|---|---|
| Urban (9 sites) | SPBU side | 500 m | 1 |
| Toll (site 5, KM57A) | SPBU side (Jakarta→Cikampek) | ~1 km | 1 |

Exception: site 3 (TB Simatupang) uses the user's Entry and Exit points as given (Approach 463 m, Departure 483 m). Its Departure carries a "Turn left" label that the user verified is a lane split, not a turn: the route is 483 m against 480 m in a straight line. This is set in `LINK_ENTRY_SITES` in `scripts/propose_segments.py`. A "Keep left/right to continue on <same road>" step counts as staying on the road, not as a turn.

Every call runs every 30 minutes: 10 calls and 20 legs per slot. `sides_for()` in `scripts/propose_segments.py` sets the sides. The opposite-side derivation is kept there and can be switched back on per site.

**Turn-in/Turn-out was tested and dropped** (2026-10-06). It drove into the forecourt via a `place_id` stop. It's demo-only, mixes road traffic with U-turns and driveways, and would double the Routes cost. The prototype and the site 1 and site 5 results are recorded on bead `.7.4` in case it comes back.

## Verified before planning (2026-10-06, key `MAPS_API_KEY`)

- **Routes `TRAFFIC_AWARE`:**
  - Returns `duration` ≠ `staticDuration`, as Duration strings (`"1481s"`).
  - Waypoint `location.heading` is accepted.
  - A `via: false` stop splits the route into legs, each with its own `duration`, `staticDuration`, `distanceMeters` and polyline.
- **`staticDuration` is not free-flow.** Observed durations come in below it (site 1: 67 s vs 97 s). Congestion is therefore measured against our own baseline (`data-schema.md`, `v_leg_baseline`).
- **Points can't be placed automatically from the Places location.** That location sits inside the forecourt. Every automatic attempt (sites 3, 6, 7, 9) snapped to driveways or side streets and gave legs of 1.3–3.9 km with ramps and U-turns.
- **Points from a Google Maps directions link work.** One link per site, from the Entry point to the SPBU, gives the Entry point and the place. Front and Exit are then derived along the main road:
  - Site 1: all 4 main-road legs 417–500 m, with no U-turns or ramps.
  - Site 5: Approach and Departure are about 1,000 m each on the toll road, with no maneuvers.
- **Weather `currentConditions:lookup`** returns every field the schema needs for Jakarta coordinates.

## Decisions

| Topic | Decision | Why |
|---|---|---|
| Region | Cloud Run job, Scheduler and BigQuery dataset `traffic` in `asia-southeast2` (Jakarta), project `gcp-coe-sandbox` | Data stays next to the users, in a single region |
| Runtime | Python 3.12 container. Maps calls use `urllib` (as in `scripts/places_test_fetch.py`); BigQuery writes use `google-cloud-bigquery` | Pure logic stays importable without the client library, so tests need no pip install |
| Trigger | Scheduler `*/30 * * * *` (Asia/Jakarta) → Cloud Run Admin API `jobs:run` with OAuth | The standard pattern for jobs |
| Slot | `slot_time` = wall clock rounded to the **nearest** :00/:30 UTC. Every leg runs every slot | Start jitter (e.g. :29:58) must not shift the slot. Jakarta is UTC+7 with no DST, so slots line up |
| Idempotency | One `MERGE` per table per run, keyed on `(selected_route_id, slot_time)` and `(site_id, slot_time)` | Retries must not double-insert |
| Segment input | A human sends a Google Maps directions link per site/side, from the Entry point to the SPBU, plus an optional SPBU → Exit link where a junction or U-turn slot is in the way. A script derives Front and Exit and validates every leg. A preview map is checked by the user | Automatic placement failed at 4 of 4 sites |
| Weather location | Each site's SPBU-side **Front** point (our own coordinate, not `sites.location`) | It's the road point the traffic legs measure; the WeatherNext grid is about 11 km anyway |
| Congestion metric | `congestion_index` = duration ÷ per-leg 7-day 10th-percentile duration (`v_traffic`). Raw `static_ratio` is kept for reference | Google's no-traffic time is a pessimistic model on these roads |
| Speed intervals | Not requested (Pro tier) | `TRAFFIC_ON_POLYLINE` bills at the Enterprise tier |
| Failures | A failed call is logged and the run continues; its row is still written, with null durations and the error in `raw`. The job fails only if every call fails | One bad leg must not drop the whole slot |
| Secrets | Secret `MAPS_API_KEY` is mounted into the job as an env var | Never in code, image or logs |

## Phases

### Phase 1: start collecting

Target: rows landing within 2 days of receiving the directions links.

**1a. Dataset and tables** (bead `.7.2`)
- `sql/ddl.sql`: the four tables from `data-schema.md`, in dataset `traffic`, location `asia-southeast2`.
- `scripts/bq_setup.sh`: creates the dataset and runs the DDL. Re-runnable (`CREATE … IF NOT EXISTS`).

**1b. Segments** (bead `.7.4`)
- `data/segment_links.csv`: `site_no, side, entry_url, exit_url (optional)`. These are the user's directions links.
- `scripts/segments_lib.py`: pure helpers covering polyline decoding, geometry, left-hand-traffic side logic, directions URL → Entry/Exit/`place_id`, road-name matching and leg validation. No network.
- `scripts/propose_segments.py` derives and validates in one pass:
  1. **Parse links.** Entry from the link's start coordinate; for a site with an `exit_url`, Exit from its destination coordinate. The place comes from the `!1s0x…:0x…` ID, converted to a `place_id` and checked against `sites.csv`.
  2. **Find the main road.** Sites without a link are probed by routing from the Places pin until a step runs on the station's named road.
  3. **Place Front and Exit.** Front is the main-road point nearest the SPBU; Exit is 500 m further on (about 1 km for toll), along the main-road geometry. The SPBU side is the direction with the station on the driver's left.
  4. **Validate.** One traffic-aware call per site (Entry → Front stop → Exit). Each leg must:
     - be 400–700 m long (urban) or 500–1,300 m (toll);
     - be at most 1.15× the straight-line distance;
     - not run on a toll road (urban sites);
     - have no `UTURN`, `RAMP`, `TURN` or `ROUNDABOUT` maneuvers. A "Keep left/right to continue on <the same road>" step doesn't count, and neither do labels a user verified per site (`LINK_ENTRY_SITES`; site 3's Departure "Turn left").
     - If no 500 m variant passes, urban legs may shorten to 300 m (`SHORT_VARIANTS`) and get a "short leg" note.
  5. **Write** `data/routes.csv`: one row per leg, with status `ok` or `needs_link`, plus `expected_distance_m` and `expected_polyline`. Route IDs are `spbu-<code>-spbuside-<approach|departure>`.

  Routes and Places responses are cached in the git-ignored `out/segments/cache/`.
- `scripts/preview_segments.py`: writes `out/segments/preview.html` (Maps JS, Google basemap, Entry/Front/Exit labels, per-leg timings). The file is git-ignored because it holds the key.
- **Human check:** the user reviews the preview. Points that fail get a new or corrected directions link.
- `scripts/load_reference.py` (bead `.7.11`, after `.7.2`): `MERGE`s `data/sites.csv` and `data/routes.csv` into `traffic.sites` and `traffic.routes`.

**1c. Collector job** (beads `.7.5` traffic, `.7.7` weather)

`collector/` holds:
- `main.py`: entry point.
- `slots.py`: nearest-slot rounding.
- `traffic.py`:
  - builds the request per `call_id` (Entry → Front stop → Exit, with headings);
  - parses Duration strings (`"123s"` → 123.0);
  - decodes the polyline;
  - maps legs to rows;
  - computes `static_ratio` and `speed_kmh`.
- `weather.py`: field mapping and units, and `rain_flag`.
- `bq.py`: reads active routes and runs the `MERGE`s (staging table + MERGE per table). This is the only module that imports `google.cloud`. The views `v_leg_baseline` and `v_traffic` are created by `sql/ddl.sql` (1a).
- `Dockerfile` and `requirements.txt`.

Each run:
1. Read active routes and group them into calls by `call_id`.
2. Call `computeRoutes` once per call (field mask: legs' duration, staticDuration, distanceMeters, polyline) and `currentConditions` for each site.
3. Build rows: core, `demo_*`, `raw` and `fetched_at`.
4. Run two `MERGE`s.

Tests go in `tests/test_collector_*.py`, cover the pure functions only and make no network calls.

**1d. Deploy** (bead `.7.8`)
- **First deploy uses `--default-sa`** (user, 2026-10-07). The job and the Scheduler run as the Compute Engine default service account, which has Editor. Editor already covers BigQuery jobs, table writes (the dataset access list gives project editors write access) and starting the job. The only grant added is `secretmanager.secretAccessor` on `MAPS_API_KEY`. Moving to the dedicated accounts below is bead `pertamina-retail-traffic-907.7.12`: re-run the script without `--default-sa`.
- `scripts/deploy_collector.sh`, re-runnable:
  - enables `cloudscheduler`, `cloudbuild` and `artifactregistry`;
  - creates service accounts:
    - `traffic-collector`: `bigquery.dataEditor` on the dataset, `bigquery.jobUser`, `secretmanager.secretAccessor` on `MAPS_API_KEY`;
    - `traffic-scheduler`: `run.invoker` on the job;
  - `gcloud run jobs deploy --source collector` (task timeout 10 min, max retries 1);
  - creates the Scheduler job.
- An alert policy on failed job executions emails farry@terralogiq.com.
- A budget alert needs billing-account access. **Ask the user before creating it.**

**Phase 1 acceptance**
- `scripts/build-and-test.sh` is green: the existing tests (Places fetch and segments) plus the collector tests.
- `propose_segments.py` writes every row of `data/routes.csv` with status `ok`, and the user has checked the preview map (done 2026-10-07).
- For 24 consecutive hours after deploy:
  - every slot has 20 traffic rows (10 sites × 2 legs) and 10 weather rows;
  - no duplicate keys and no missing slots;
  - fewer than 2% of rows have null `duration_in_seconds`.
- No API key appears in the logs, the image or the repo.

### Phase 2: refine (after collecting has started)

- **`v_leg_baseline` and `v_traffic`:** created in 1a (`sql/ddl.sql`), meaningful after about 7 days of data.
- **Reroute check** (bead `.7.6`): `demo_rerouted` on every leg (`collector/reroute.py`). True when `abs(demo_distance_m - expected_distance_m) > 0.1 * expected_distance_m` (more than 10% longer or shorter), or when any point of the returned polyline is more than 30 m from `expected_polyline`. False when `expected_distance_m` is missing or not positive; a missing returned distance or polyline skips its own check. NULL when the call failed. Computed at ingest; `scripts/backfill_rerouted.py` fills the earlier NULL rows from `route_geometry` with the same function.
- **Optional: speed intervals** on the legs, at Enterprise pricing ($15/1k instead of $10/1k).

## Later (not in this plan)

- An RMI-shaped view (`v_historical_travel_time`) so the dashboard can switch source by repointing a view.
- RMI registration of the legs (`rmi_state`), once Google approves RMI and confirms it covers Indonesia.
- WeatherNext 3 ingest (`forecast_init_time`, `ensemble_stat`).

## Cost (per month)

| Item | How it's counted | Calls / month | Unit price | Est. |
|---|---|---|---|---|
| Routes, main-road pairs | 10 sites × 48 slots × 30 days | 14,400 | Pro $10/1k | |
| **Routes total** | 10 calls per slot | **14,400** | 5k free | **≈ $94** (≈ $144 if the free allowance is used elsewhere on the billing account) |
| Weather `currentConditions` | 10 × 48 × 30 | 14,400 | $0.15/1k after 10k free (unverified, bead `.5`) | ≈ $0.66 (≈ $2 without the free allowance) |
| Cloud Run job | 1,440 runs × ~60 s, 1 vCPU / 512 MiB | | 180k vCPU-s free | $0 (≈ $2 without the free allowance) |
| Scheduler, BigQuery (≈ 0.6 GB/month added, `MERGE` ≈ 30 GB scanned), Secret Manager, Logging, Artifact Registry | | | free allowances | ≈ $0 |
| **Total** | | | | **≈ $95** (worst case ≈ $148) |

Levers:
- Each site costs about $14/month (one call per slot).
- Re-adding an opposite side: about +$14 per site.
- Adding Turn-in/Turn-out on both sides at every site: about +$274.
- One-offs: the Places test fetch and Text Search (done) were about $1–6; segment proposal and validation take about 200–400 Routes calls, about $2–4.

## File ownership

| Path | Owner bead | Notes |
|---|---|---|
| `sql/ddl.sql`, `scripts/bq_setup.sh` | `.7.2` | |
| `data/segment_links.csv`, `scripts/segments_lib.py`, `scripts/propose_segments.py`, `scripts/preview_segments.py`, `data/routes.csv`, `tests/test_segments.py` | `.7.4` | `data/routes.csv` is generated; fix inputs via links, not by hand |
| `scripts/load_reference.py`, `tests/test_load_reference.py` | `.7.11` | Needs the `.7.2` tables |
| `collector/main.py`, `collector/slots.py`, `collector/bq.py`, `collector/httpjson.py`, `collector/Dockerfile`, `collector/.dockerignore`, `collector/requirements.txt`, `tests/test_collector_http.py`, `tests/test_collector_bq.py` | `.7.5` | Shared entry point. `.7.7` hands its row builder to `.7.5` rather than editing these files |
| `collector/traffic.py`, `tests/test_collector_traffic.py` | `.7.5` | |
| `collector/weather.py`, `tests/test_collector_weather.py` | `.7.7` | Can run in parallel with `.7.5` |
| `scripts/deploy_collector.sh`, `scripts/collector_alert_policy.json` | `.7.8` | |
| `scripts/build-and-test.sh` | `.7.5` | Add `collector/*.py` to `py_compile` |
| `docs/plans/*.md`, `data/sites.csv`, `README.md`, `.gitignore` | orchestrator | |

Order:
1. `.7.2` and `.7.4` (independent: `.7.4` writes CSV), then `.7.11` (`load_reference.py`), which needs both.
2. `.7.5` ∥ `.7.7`, once `collector/main.py` and `bq.py` exist (`.7.5` creates them first).
3. `.7.8`.
