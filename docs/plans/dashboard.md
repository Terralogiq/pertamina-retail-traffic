# Dashboard: Cloud Run app over BigQuery, Maps JS, stored Places

Bead: `pertamina-retail-traffic-907.4` (feature); stack decided in `.4.1`. Schema: `docs/plans/data-schema.md`. Collector: `docs/plans/collector.md`. Rules: `.claude/rules/data-sources.md`.

## Goal

A web app that shows Pertamina, for each of the 10 SPBU, the traffic on the road in front (Approach and Departure legs), the weather and a Places profile of the site. It sits behind one password at a public URL. It reads only what the collector and a new Places profiling job write to BigQuery. The app never calls Routes, Weather or Places at view time.

## Verified before planning (2026-10-07)

- **Data in BigQuery** (`gcp-coe-sandbox.traffic`, asia-southeast2):
  - `traffic_snapshots` receives 20 rows per slot (10 sites × Approach and Departure); `weather_slots` receives 10.
  - `v_traffic` adds `baseline_s`, `baseline_samples`, `congestion_index` and `delay_s`.
  - `routes.expected_polyline` is a `GEOGRAPHY`, so it can be served as GeoJSON with `ST_ASGEOJSON`.
- **The baseline isn't ready yet.** `v_leg_baseline` is the 7-day p10. Until about 2026-10-13 it rests on few samples, and `congestion_index` is unstable (a full window is 336 samples per leg).
- **The sites span two time zones.** Balikpapan, Makassar and Denpasar are UTC+8 (WITA); the rest are UTC+7 (WIB). Place Details returns `utcOffsetMinutes` for 10 of 10 sites.
- **Places test fetch** (`docs/plans/places-test-fetch.md`): one run is 10 Details + 20 Nearby + 450 Aggregate calls, all 200. Details fill rate: rating, reviews (5 per site, `id` language), opening hours and photos 10/10; `fuelOptions` 0/10.
- **Toolchain:**
  - Present locally: Python 3.14.7, Node 24.12, npm 11.14.
  - FastAPI is not installed. `scripts/build-and-test.sh` is offline and uses stdlib unittest.
  - **To check first in `.4.7`:** that FastAPI and pydantic wheels install on Python 3.14 locally. The container uses Python 3.12, like the collector.

## Decisions

| Topic | Decision | Why |
|---|---|---|
| Service | One Cloud Run service `traffic-dashboard`, asia-southeast2, `--allow-unauthenticated`. FastAPI serves `/api/*` and the Vite build as static files. Multi-stage Dockerfile: Node build → `python:3.12-slim` | One URL, one deploy; the user chose it in `.4.1` |
| Frontend | Vite + React + TypeScript; Maps JS via `@googlemaps/js-api-loader`; ECharts | Decided in `.4.1`; ECharts handles time series and day×hour heatmaps |
| Password gate | `POST /api/login` compares the input with secret `DASHBOARD_PASSWORD` (constant time). Success sets cookie `session` = expiry + HMAC-SHA256, keyed from the same secret, valid 7 days, `HttpOnly; Secure; SameSite=Lax`. Without a valid cookie, `/api/*` (except `/api/login`) returns 401 and the UI shows the login form. Static assets aren't gated. Rotating the secret logs everyone out | Minimal; stateless across instances; nothing secret lives in the bundle |
| Keys | New browser key `MAPS_BROWSER_KEY`, restricted to the Maps JavaScript API and the referrers `https://traffic-dashboard-509833145296.asia-southeast2.run.app/*` and `http://localhost:5173/*`. Kept in Secret Manager and served by `GET /api/config` after login. The service never gets `MAPS_API_KEY`; only the Places job does | No unrestricted key reaches a browser |
| Identity | `deploy_dashboard.sh --default-sa`, like the collector: the Compute Engine default SA, plus `secretAccessor` on the two dashboard secrets. Dedicated SA later (with `.7.12`) | Keeps project IAM unchanged during the `.7.8` acceptance window |
| BigQuery access | Parameterised queries only. Every query on `traffic_snapshots`/`v_traffic`/`weather_slots` filters `slot_time` (the partition column); the range is capped at 31 days | Cost and latency stay flat as history grows |
| Caching | In-process TTL cache per (endpoint, params). It expires at the next :05/:35 after the slot (the collector finishes in about 60 s), max 30 min. No Redis | One BigQuery job per slot per view, not per page load |
| Time | Stored in UTC. The UI shows each site's local time, labelled WIB/WITA. New column `timezone` (`Asia/Jakarta` / `Asia/Makassar`) in `data/sites.csv` → `sites.timezone`, loaded by `load_reference.py`. The day×hour pattern is computed in local time in SQL (`EXTRACT(HOUR FROM slot_time AT TIME ZONE timezone)`) | Without it, the three WITA sites' patterns shift by an hour |
| Baseline pending | While `baseline_samples < 302` (90% of 7 days × 48 = 336), the UI shows congestion with a "baseline building (n/302)" badge, and map colouring falls back to `speed_kmh` bands. The view window is not shortened | An honest early state; the metric definition stays fixed. 90% so that one missed slot, or the gap before each write, doesn't hold a leg in fallback for 7 days (review 2026-10-07) |
| Places data | Stored results only, from a new Cloud Run job `places-profiler`. It reuses the request/field logic of `scripts/places_test_fetch.py` and writes `places_details`, `places_nearby`, `places_aggregate`. Weekly Scheduler (Mon 02:00 Asia/Jakarta) plus a manual `gcloud run jobs execute` | Decided in `.4.1`; history across runs makes Places quality measurable |
| Places tables | Grain: `places_details` = site × `fetched_at`; `places_nearby` = site × radius × result place × `fetched_at`; `places_aggregate` = site × type × radius × `fetched_at`. Column groups: core (production uses the same API) + `raw` JSON; `demo_*` stays empty unless a field is demo-only. Partitioned by `DATE(fetched_at)` | Follows `data-sources.md`; runs can be compared |
| Labels | A "demo-only" badge goes on widgets that use `static_ratio`, `demo_rerouted`, `demo_rain_flag`, `demo_condition_*`, `demo_precip_probability`, `demo_thunderstorm_prob`, `demo_feels_like_c`, `demo_uv_index`, `demo_visibility_km` or `demo_cloud_cover`. Core widgets (`congestion_index`, `delay_s`, `speed_kmh`, `duration_in_seconds`, `rain_flag`, `precipitation_mm`, `temperature_c`, `relative_humidity`, `wind_speed_kmh`) carry no badge. Places panels carry no badge (same source in production) | Follows `data-sources.md` |
| Language | UI copy in English; site names as in Places | Demo audience is Terralogiq + Pertamina technical staff. Indonesian is a later bead if asked |

## Screens

1. **Overview:** Google basemap, capped at the page max width (90rem), with 10 SPBU markers and both legs drawn as polylines, coloured by the latest `congestion_index` (or `speed_kmh` while the baseline is pending). A side list shows each site's city, latest delay per leg, current weather icon and temperature, and the "baseline building" badge where it applies. Below the map and list, a "Stations at a glance" table has one row per station: slower-before-than-after tier, confidence, queue complaints, top complaint, reviews labelled; default sort by name (see [overview-station-table.md](overview-station-table.md)).
2. **Site detail** (`/site/:site_id`), nav order Traffic, Typical day, Review themes, Weather, Places:
   - Map zoomed to the site's legs.
   - Per-leg time series for the last 24 h / 7 d (`congestion_index`, `delay_s`, `speed_kmh`), with `precipitation_mm` bars on the same time axis.
   - Typical day: day × hour heatmap of mean `congestion_index` in local time.
   - Review themes, in the left column under Typical day.
   - Weather panel.
   - Places panel.
3. **Traffic vs rain:** per site, mean `delay_s` in slots with `rain_flag` vs without, plus a scatter of `precipitation_mm` against `congestion_index`. A `demo_rain_flag` toggle carries the demo-only badge.

## API

All endpoints are GET unless noted, return JSON, and require the session cookie except `/api/login` and `/health`.

| Endpoint | Returns | Source |
|---|---|---|
| `POST /api/login` `{password}` | 204 + cookie, or 401 | secret |
| `GET /api/config` | `{maps_browser_key}` | secret |
| `GET /api/sites` | sites with `timezone`, location, and legs with `expected_polyline` GeoJSON | `sites`, `routes` |
| `GET /api/traffic/latest` | latest slot per leg: duration, delay, congestion, speed, baseline_samples | `v_traffic`, last 2 h |
| `GET /api/traffic/series?site_id&from&to` | per slot per leg | `v_traffic` |
| `GET /api/traffic/pattern?site_id&days=28` | day-of-week × local hour → mean congestion, n | `v_traffic` ⨝ `sites` |
| `GET /api/traffic/queue-risk` | all sites, 28-day window: tier, metrics and reviewed confidence | `v_traffic` ⨝ `routes` ⨝ `sites` (core columns) |
| `GET /api/review-themes` | per site: negative/mixed review category counts, queue complaints, top category; no review text | `place_review_labels` ⨝ `v_place_reviews` |
| `GET /api/weather/latest` | latest slot per site | `weather_slots`, last 2 h |
| `GET /api/weather/series?site_id&from&to` | per slot | `weather_slots` |
| `GET /api/rain?site_id&days=28` | rain vs dry delay summary + scatter points | `v_traffic` ⨝ `weather_slots` |
| `GET /api/places/{site_id}` | latest run: details (rating, review count, 5 reviews, hours), competitors by brand per radius, POI counts per type × radius, `fetched_at` | `places_*` |
| `GET /health` | 200 | — |

## Phases

### Phase 1: scaffold (`.4.7`)

- `dashboard/api/` (FastAPI app, auth, BigQuery wrapper, cache), `dashboard/web/` (Vite + React + TS shell, login form, router, API client), `dashboard/Dockerfile`, `dashboard/requirements.txt`.
- `sites.timezone`: column in `sql/ddl.sql` (`ALTER TABLE … ADD COLUMN`) and `data/sites.csv`, loaded by `load_reference.py`.
- `scripts/dev-setup.sh` (one-time, needs network): creates `.venv`, runs `pip install -r dashboard/requirements.txt` and `npm ci` in `dashboard/web`.
- `scripts/build-and-test.sh` stays offline. It uses `.venv/bin/python` when present and runs `tsc --noEmit`, `vite build` and `vitest run` in `dashboard/web`. If `.venv` or `node_modules` is missing, it fails with one line: "run scripts/dev-setup.sh".
- `scripts/deploy_dashboard.sh` with `--dry-run` and `--default-sa`: creates the secrets `DASHBOARD_PASSWORD` and `MAPS_BROWSER_KEY` if missing (the user sets the values; they are never printed), the browser key with its restrictions, and the Cloud Run deploy from source.
- Acceptance:
  - Build & test is green, with `TestClient` tests for login (correct/wrong password, expired/tampered cookie → 401), `/api/sites` with BigQuery mocked, and the cache TTL boundary.
  - Deployed: the URL shows the login form, the right password lands on an empty overview with the basemap, and a wrong one gets 401.

### Phase 2: features (parallel after `.4.7`)

- **`.4.2` Map view:** overview and site map, polylines coloured by congestion band, speed fallback while the baseline is pending. Acceptance: all 20 legs drawn on the right carriageway at all 10 sites; the fallback is visible when `baseline_samples < 302`.
- **`.4.3` Traffic charts:** series and pattern endpoints plus charts, core columns only. Acceptance: the pattern for Makassar (WITA) puts hours in local time; a test pins `AT TIME ZONE` in the SQL; charts show the "baseline building" badge.
- **`.4.4` Weather + traffic vs rain:** weather endpoints, weather panel, rain view; demo-only badges per the Labels decision. Acceptance: every `demo_*` widget carries the badge (tested against a list).
- **`.4.6` Places profiling job:** `places_job/`, DDL for the three tables, schema doc, deploy (weekly Scheduler), first run. Acceptance: a run writes 10 details, ~240 nearby and 450 aggregate rows; a re-run on the same day adds a second `fetched_at` without touching the first.

### Phase 3: Places panels (`.4.5`, needs `.4.6` + `.4.7`)

- `GET /api/places/{site_id}` plus a panel showing rating and review count, the 5 latest reviews, opening hours, competitor counts by brand (1 km / 3 km, `*` when capped at 20) and a POI table (500 m / 1 km / 3 km).
- Acceptance: all 10 sites render; the panel shows `fetched_at`.

## Later (not in this plan)

- Dedicated service accounts for the dashboard (with `.7.12`).
- `demo_rerouted` filtering in charts, once `.7.6` lands.
- Indonesian UI copy; custom domain; per-user accounts.
- Places quality report across runs (diff of ratings and POI counts between `fetched_at` values).

## Cost (per month)

| Item | Volume | Est. |
|---|---|---|
| Cloud Run service (min 0 instances, demo traffic) | < 100k requests | ≈ $0 within the free tier |
| BigQuery queries | partition-filtered, cached per slot; tables < 1 GB | ≈ $0 |
| Maps JS dynamic map loads | < 1k/month (10k free on Essentials) | ≈ $0 |
| Places job, weekly | 4 × (10 Details with reviews + 20 Nearby + 450 Aggregate) | Details ≈ $1, Nearby ≈ $3, Aggregate 1,800 < 5k free → ≈ $4 (prices unverified, bead `.5`) |
| **Total added** | | **≈ $5** on top of the collector's ≈ $95 |

## File ownership

| Path | Owner bead | Notes |
|---|---|---|
| `dashboard/api/main.py`, `dashboard/api/auth.py`, `dashboard/api/bq.py`, `dashboard/api/cache.py`, `dashboard/api/routers/sites.py`, `dashboard/requirements.txt`, `dashboard/Dockerfile`, `dashboard/.dockerignore` | `.4.7` | `main.py` mounts every router. Later beads add one `include_router` line each, the only shared edit |
| `dashboard/web/` scaffold (`package.json`, lockfile, `vite.config.ts`, `tsconfig.json`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/api.ts`, `src/login/`) | `.4.7` | Later beads add routes in `App.tsx` (one line each) and dependencies only via `.4.7`'s lockfile, so add them in `.4.7` up front: `@googlemaps/js-api-loader`, `echarts` |
| `scripts/dev-setup.sh`, `scripts/build-and-test.sh`, `scripts/deploy_dashboard.sh` | `.4.7` | |
| `sql/ddl.sql` (sites.timezone), `data/sites.csv` (timezone), `scripts/load_reference.py`, `tests/test_load_reference.py` | `.4.7` | |
| `tests/test_dashboard_auth.py`, `tests/test_dashboard_sites.py`, `tests/test_dashboard_cache.py` | `.4.7` | |
| `dashboard/web/src/map/` (tests in `src/map/*.test.ts`) | `.4.2` | Uses `/api/sites`, `/api/traffic/latest` |
| `dashboard/api/routers/traffic.py`, `tests/test_dashboard_traffic.py`, `dashboard/web/src/traffic/` | `.4.3` | `.4.2` reads `/api/traffic/latest` from this router; `.4.7` stubs it so `.4.2` can start in parallel |
| `dashboard/api/routers/weather.py`, `tests/test_dashboard_weather.py`, `dashboard/web/src/weather/` | `.4.4` | |
| `places_job/` (`main.py`, `places.py`, `bq.py`, `Dockerfile`, `requirements.txt`), `tests/test_places_job.py`, `scripts/deploy_places_job.sh`, `sql/ddl.sql` (Places tables section), `docs/plans/data-schema.md` (Places tables) | `.4.6` | `sql/ddl.sql` is shared with `.4.7`; different sections, `.4.7` first |
| `dashboard/api/routers/places.py`, `tests/test_dashboard_places.py`, `dashboard/web/src/places/` | `.4.5` | |
| `README.md`, `docs/plans/*.md` (except the schema's Places section) | orchestrator | |

Order:
1. `.4.7` (it stubs `/api/traffic/latest` returning `[]`).
2. `.4.2` ∥ `.4.3` ∥ `.4.4` ∥ `.4.6`, in worktrees; each adds only its `include_router` and route lines in shared files.
3. `.4.5`.

## Open questions for the user

- **Password value:** you set it with `gcloud secrets versions add DASHBOARD_PASSWORD` (it never passes through the session).
- **Places cadence:** weekly is the default. Daily costs about 7× (≈ $28/month).
