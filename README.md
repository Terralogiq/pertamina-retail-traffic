# pertamina-retail-traffic

Terralogiq demo for Pertamina: monitors traffic on the road in front of 10 SPBU (fuel stations) every 30 minutes, alongside the weather and a Places-based profile of each site (nearby POIs, competitors, reviews).

**Status (2026-10-07):**
- Done:
  - 10 SPBU chosen and anchored on `place_id` (`data/sites.csv`).
  - Places test fetch.
  - Collector plan (`docs/plans/collector.md`).
  - Road segments for all 10 sites, validated and user-checked (`data/routes.csv`).
  - BigQuery dataset `gcp-coe-sandbox.traffic` (asia-southeast2) with reference data loaded (10 sites, 20 legs).
  - Collector deployed 2026-10-07 00:40 WIB: Cloud Run job `traffic-collector`, Scheduler `traffic-collector-every-30min` (`*/30` Asia/Jakarta), failure alert by email. Every slot so far has 20 traffic + 10 weather rows, no gaps.
- In progress: 24 h acceptance run (through ~2026-10-07 18:00 UTC).
- Next: recheck rain flags after 24–48 h, then choose the dashboard stack.

## Data sources

The demo uses stand-in sources until the production ones are licensed. Binding rules: [`.claude/rules/data-sources.md`](.claude/rules/data-sources.md).

| Layer | Demo source | Production source |
|---|---|---|
| Traffic | Routes API `computeRoutes` (`TRAFFIC_AWARE`), every 30 min, cached in BigQuery as a "pretend RMI" feed | Roads Management Insights (RMI), pending Google approval |
| Weather | Google Weather API `currentConditions`, cached per 30-min slot | WeatherNext (Earth Engine) |
| Places | Places API (New) + Places Aggregate, fetched and stored for quality measurement | Same |

RMI is contract-gated and aimed at road operators. It covers only the customer's managed territory and can reject routes as `LOW_ROAD_USAGE` or `OUTSIDE_JURISDICTION`. It delivers data every 2 minutes over Pub/Sub, or every 10 minutes into BigQuery.

## Architecture

```
Cloud Scheduler (*/30, Asia/Jakarta)
  → Cloud Run job
      ├─ Routes computeRoutes   (1 call per SPBU: Approach + Departure legs, SPBU side)
      └─ Weather currentConditions (1 call per SPBU)
  → BigQuery dataset `traffic`
  → Dashboard: Maps JS basemap + charts from BigQuery + Places panels
```

- Times are stored in UTC, and slots are aligned to :00 and :30.
- Frontend recommendation (not final): a custom app. Looker Studio can't make live Places calls.
- Maps use a Google basemap only (no Leaflet, OSM or Mapbox).

## Data model

Spec: [`docs/plans/data-schema.md`](docs/plans/data-schema.md). DDL: [`sql/ddl.sql`](sql/ddl.sql).

| Table | Grain | Purpose |
|---|---|---|
| `sites` | SPBU | ID, name, `place_id`, location, road, city |
| `routes` | SPBU × direction | Segment endpoints with headings, plus the expected polyline and distance. Later becomes the RMI route registration. |
| `traffic_snapshots` | route × 30-min slot | Duration, static duration and derived metrics. Partitioned by date, clustered by `route_id`. |
| `weather_slots` | SPBU × 30-min slot | Temperature, precipitation, humidity, wind and pressure. Partitioned by date, clustered by `site_id`. |

Views: `v_leg_baseline` (each leg's 7-day p10 duration) and `v_traffic` (snapshots joined with the derived metrics below).

Every table has three column groups:
- **core:** compatible with RMI or WeatherNext. Production metrics build only on these.
- **`demo_*`:** available only from the demo source. Widgets that use them show a "demo-only" label.
- **`raw`:** the full API response as `JSON`.

### Traffic metrics

| Metric | Formula | Note |
|---|---|---|
| `congestion_index` | `duration / baseline`, where baseline = the leg's 10th-percentile duration over the last 7 days | Our own measure. Google's `staticDuration` is not free-flow (observed durations come in below it), so it isn't used as the base. Needs about 7 days of data. |
| `delay_s` | `duration − baseline` | |
| `static_ratio` | `duration / staticDuration` | Reference only. |
| `speed_kmh` | `routes.expected_distance_m / duration` | Uses the registered distance, not the per-call distance, so it also works on RMI data. |
| `demo_rerouted` | distance differs >10% from expected, or the polyline leaves a 30 m buffer around the expected route | Demo-only check that the router stayed on the intended road. |

## Key API facts

- **Routes:** must set `routingPreference: TRAFFIC_AWARE`. The default `TRAFFIC_UNAWARE` returns `duration == staticDuration`, which carries no traffic signal.
- **Routes:** use `computeRoutes`, not `computeRouteMatrix`. A matrix bills every origin × destination pair, which wastes elements on independent segments.
- **Routes:** pin each waypoint with a `heading` so the router stays on the correct carriageway.
- **Routes:** `speedReadingIntervals` (NORMAL / SLOW / TRAFFIC_JAM) needs `extraComputations: TRAFFIC_ON_POLYLINE`. That bills at the Enterprise tier and gives route- and leg-level detail only. It is optional here.
- **No backfill:** a past `departureTime` is allowed only for transit, so history starts when the scheduler starts. Start collecting early.
- **Places:**
  - Places ToS storage limits are waived for the demo (2026-10-07): Places responses may be stored to measure their quality before using Places Aggregate.
  - Popular times is not available in any official API.

## Cost estimate

Prices as of 2026-10-06.

| Item | Volume / month | Price | Est. |
|---|---|---|---|
| Routes, 1 call per SPBU (Approach + Departure) | 10 × 48/day × 30 ≈ 14,400 | Pro $10/1k after 5k free | ≈ $94 (≈ $144 if the free allowance is used elsewhere) |
| Re-adding an opposite side | +1,440 per site | Pro | +$14 per site |
| Routes with `TRAFFIC_ON_POLYLINE` | — | Enterprise $15/1k after 1k free | optional |
| Weather `currentConditions` | 10 × 48/day ≈ 14,400 | $0.15/1k after 10k free* | ≈ $0.66 |
| Nearby Search | per profiling run | $32–40/1k by tier* | — |
| Place Details with reviews | live, per view | $25/1k* | — |
| Places Aggregate | per profiling run | $10/1k after 5k free* | — |

\* Taken directly from Google's pricing pages but not double-checked like the Routes prices. Recheck in the console; the Weather price looks low.

## Roadmap

Tracked in Beads (`bd ready`, epic `pertamina-retail-traffic-907`).

1. ~~Inputs:~~ done: 10 SPBU and GCP project `gcp-coe-sandbox`.
2. ~~Places test fetch:~~ done: `docs/plans/places-test-fetch.md`.
3. **Collector** (`docs/plans/collector.md`):
   - segments ✓
   - BigQuery tables ✓
   - reference load ✓
   - collector job ✓
   - Scheduler deploy ✓ (24 h acceptance pending)
   - later: dedicated service accounts instead of the Compute Engine default SA; `demo_rerouted` check
4. **Dashboard frontend:** stack not chosen yet.

## Repo layout

```
.claude/           harness: settings, Stop hook, advisor-reviewer agent, rules
collector/         Cloud Run job: Routes + Weather calls, staging table + guarded MERGE (idempotent)
data/              sites.csv (place_id anchors), segment_links.csv (user links), routes.csv (validated legs)
docs/plans/        plans and specs (collector, data-schema, sites, places-test-fetch)
docs/handoffs/     session handoffs
scripts/           build-and-test.sh, bq_setup.sh, load_reference.py, deploy_collector.sh,
                   places_test_fetch.py, segments (segments_lib, propose_segments, preview_segments)
sql/               ddl.sql (BigQuery tables and views)
tests/             unittest, no network
out/               git-ignored outputs (raw API responses, preview map)
```

## Operations

Always pass `--project gcp-coe-sandbox --billing-project gcp-coe-sandbox`; the gcloud default quota project is a different one.

```bash
scripts/bq_setup.sh                       # dataset, tables, views
python3 scripts/load_reference.py         # MERGE sites.csv + routes.csv into BigQuery
scripts/deploy_collector.sh --default-sa  # job + Scheduler + alert; also --dry-run, --no-schedule

# Health check: every execution should succeed
gcloud run jobs executions list --job traffic-collector --region asia-southeast2 \
  --project gcp-coe-sandbox --billing-project gcp-coe-sandbox --limit 100
```

In BigQuery, each `slot_time` should have 20 rows in `traffic_snapshots` (all with a duration) and 10 in `weather_slots`, with no missing :00/:30 slots.

- The Maps key lives in Secret Manager (`MAPS_API_KEY`). Never print it.
- The collector costs about $95/month while the Scheduler is enabled. Pause it with `gcloud scheduler jobs pause traffic-collector-every-30min --location asia-southeast2 --project gcp-coe-sandbox`.

## Workflow

`/plan` → `docs/plans/<feature>.md` → Beads → claim → implement → Stop hook runs `scripts/build-and-test.sh` → `advisor-reviewer` → human review + CI → `bd close`. Details in [`CLAUDE.md`](CLAUDE.md).

## Tooling versions

- Claude Code: 2.1.291
- bd: 1.3.1 (Homebrew)
