# Data schema — SPBU traffic demo

Decided 2026-10-06. Each table has three column groups:

- **core** — compatible with the production sources (RMI for traffic, WeatherNext 3 for weather). Anything meant to survive the switch to production builds only on these.
- **demo_*** — only available from the demo sources (Routes API, Google Weather API). Dashboard widgets that use them get a "demo-only" label.
- **raw** — the full API response as `JSON`, so a field can be added later without collecting again.

Ingestion: Cloud Scheduler (`*/30 * * * *`, Asia/Jakarta) → Cloud Run job → BigQuery. Times are stored in UTC. `slot_time` is aligned to :00 and :30; `record_time` is when the data was actually computed.

## Production-source facts that shaped this schema

Checked 2026-10-06 against official docs.

**RMI** (BigQuery tables `historical_travel_time`, and `recent_roads_data` under the real-time contract):
- Routes are identified by `selected_route_id`, which must match `[A-Za-z0-9-]{4,63}`, so it can't contain dots.
- Durations are FLOAT seconds.
- `route_geometry` is a GEOGRAPHY.
- `speed_reading_intervals` is a list of `{interval_coordinates GEOGRAPHY, speed}`. It exists only in `recent_roads_data`, which keeps data for 60 days.
- Data arrives every 10 minutes, landing about 1 hour later.

**RMI routes:**
- `dynamicRoute` takes an origin, a destination and up to 25 intermediates, as plain LatLng with no heading.
- Use one route per direction on divided roads, with at least one intermediate.
- A route is marked INVALID for `LOW_ROAD_USAGE` or `ROUTE_OUTSIDE_JURISDICTION`.
- RMI coverage of Indonesia is not documented; confirm it with Google.

**WeatherNext 3** (released Aug 2026; superseded WN2):
- Forecast only, with no current-conditions product.
- Hourly time steps on a 0.1° grid (about 11 km). An ensemble published as `_mean` / `_p50` / … statistics.
- Variables:
  - `temperature_2m` (K)
  - `dewpoint_temperature_2m` (K); there is no relative humidity variable
  - `u/v_component_of_wind_10m` and `wind_speed_10m` (m/s)
  - `mean_sea_level_pressure` (Pa)
  - `total_precipitation_1hr` (m)
  - `total_cloud_cover` (0–1)
- A slot value comes from the latest forecast initialised before the slot. Values at :30 are interpolated between the hourly steps.

Sources: `developers.google.com/maps/documentation/roads-management-insights` (accumulated-data, real-time-data, selection API reference, route-selection guide); `developers.google.com/weathernext/guides` (models, bigquery, earth-engine).

## sites
```sql
CREATE TABLE traffic.sites (
  site_id      STRING NOT NULL,   -- SPBU number, e.g. "34.121.03"; surrogate if Places shows none (site 5: "KM57A")
  name         STRING,
  place_id     STRING NOT NULL,   -- Places place_id: the anchor (storable indefinitely)
  location     GEOGRAPHY,         -- from Place Details
  road_name    STRING,
  city         STRING,
  timezone     STRING             -- IANA zone: Asia/Jakarta (WIB) or Asia/Makassar (WITA)
);
```

## routes  (one row per leg; each leg can later become an RMI SelectedRoute)

Naming:
- **Points**, along the direction of travel:
  - **Entry**: the start point, upstream.
  - **Front**: the main road in front of the SPBU.
  - **Exit**: the end point, downstream.
- **Side:** **SPBU side**, the carriageway the station is on. Only this side is measured (opposite carriageways dropped on 2026-10-06). `side` stays as a column so an opposite side can be added back.
- **Legs:** **Approach** (Entry → Front) and **Departure** (Front → Exit). Both measure main-road traffic and are RMI-compatible.
- **One Routes call gives both legs.** The call runs Entry → Front → Exit, with Front as a stop (`via: false`, lat/lng with heading), so the response splits into two legs.

Driving into and out of the SPBU (Turn-in/Turn-out, via a `place_id` stop) was tested and dropped on 2026-10-06 to keep every measurement on the main road.

```sql
CREATE TABLE traffic.routes (
  -- core (maps to RMI SelectedRoute)
  selected_route_id   STRING NOT NULL,  -- RMI-legal "spbu-<site_id without dots>-<spbuside|opposite>-<approach|departure>"
  display_name        STRING,           -- e.g. "SPBU 34.121.03 TB Simatupang · SPBU side · Approach"
  origin              GEOGRAPHY,        -- leg start (Entry or Front)
  destination         GEOGRAPHY,        -- leg end (Front or Exit)
  intermediates       ARRAY<GEOGRAPHY>, -- for RMI registration: at least 1 mid-leg point (RMI has no heading)
  -- ours
  site_id             STRING NOT NULL,
  side                STRING,           -- "spbu_side" | "opposite"
  leg                 STRING,           -- "approach" | "departure"
  call_id             STRING,           -- the two legs fetched by the same computeRoutes call share this id
  leg_index           INT64,            -- 0 = approach, 1 = departure
  expected_polyline   GEOGRAPHY,        -- reference line for the reroute check
  expected_distance_m INT64,
  active              BOOL,
  rmi_state           STRING,           -- null until registered with RMI (RUNNING / INVALID …)
  -- demo-only (Routes API Waypoint heading)
  demo_origin_heading INT64,
  demo_dest_heading   INT64
);
```

Urban legs are **500 m**. Toll legs (site 5) are **about 1 km**, on the Jakarta→Cikampek carriageway the rest area serves.

## traffic_snapshots
```sql
CREATE TABLE traffic.traffic_snapshots (
  -- core (RMI historical_travel_time / recent_roads_data)
  selected_route_id           STRING NOT NULL,
  display_name                STRING,
  record_time                 TIMESTAMP NOT NULL,   -- when the value was computed (demo: fetch time)
  duration_in_seconds         FLOAT64,
  static_duration_in_seconds  FLOAT64,
  route_geometry              GEOGRAPHY,            -- traffic-aware polyline
  road_segment_ids            ARRAY<STRING>,        -- RMI only; empty in the demo
  speed_reading_intervals     ARRAY<STRUCT<interval_coordinates GEOGRAPHY, speed STRING>>,  -- NORMAL|SLOW|TRAFFIC_JAM; empty at the Routes Pro tier
  -- ours
  slot_time                   TIMESTAMP NOT NULL,   -- :00/:30 slot this row belongs to (RMI: nearest record_time per slot)
  -- derived (computed from core only)
  static_ratio                FLOAT64,  -- duration / static_duration; reference only, since staticDuration is not free-flow (observed < 1)
  speed_kmh                   FLOAT64,  -- routes.expected_distance_m / duration
  -- demo-only (Routes API)
  demo_distance_m             INT64,
  demo_rerouted               BOOL,     -- demo_distance_m deviates >10% from expected, or route_geometry leaves a 30 m buffer around expected_polyline
  demo_routing_preference     STRING,
  -- raw
  raw                         JSON,
  fetched_at                  TIMESTAMP
)
PARTITION BY DATE(slot_time)
CLUSTER BY selected_route_id;
```

**Congestion is measured against our own baseline, not `staticDuration`.** Google's no-traffic time is a model estimate, and live durations come in below it (site 1, 2026-10-06: 67 s observed vs 97 s "static"). Views:
- `v_leg_baseline`: per `selected_route_id`, the free-flow time = the 10th-percentile `duration_in_seconds` over the trailing 7 days. It needs about 7 days of data first.
- `v_traffic`: adds:
  - `congestion_index` = `duration_in_seconds` / baseline (≥ 1 in practice)
  - `delay_s` = `duration_in_seconds` − baseline

Both use only core columns, so they work unchanged on RMI data.

## weather_slots
```sql
CREATE TABLE traffic.weather_slots (
  -- core (WeatherNext 3-compatible)
  site_id            STRING NOT NULL,     -- demo: queried at the SPBU-side Front point (our coordinate, not Places)
  slot_time          TIMESTAMP NOT NULL,  -- valid time
  forecast_init_time TIMESTAMP,           -- WN3 init used; null for the demo (observed current conditions)
  temperature_c      FLOAT64,             -- WN3 temperature_2m_mean − 273.15
  dewpoint_c         FLOAT64,             -- WN3 dewpoint_temperature_2m_mean − 273.15
  relative_humidity  FLOAT64,             -- % 0–100; WN3: derived from temperature and dewpoint (Magnus)
  precipitation_mm   FLOAT64,             -- mm in the hour ending at slot_time; WN3 total_precipitation_1hr × 1000
  rain_flag          BOOL,                -- precipitation_mm > 0.1
  wind_speed_kmh     FLOAT64,             -- WN3 wind_speed_10m × 3.6
  wind_direction_deg FLOAT64,             -- direction the wind comes from; WN3: atan2(−u, −v)
  msl_pressure_hpa   FLOAT64,             -- mean sea-level pressure; WN3 Pa ÷ 100
  source             STRING,              -- "google_weather" now, "weathernext3" later
  ensemble_stat      STRING,              -- WN3 statistic used ("mean"); null for the demo
  -- demo-only (Google Weather currentConditions)
  demo_condition_type     STRING,    -- e.g. LIGHT_RAIN
  demo_condition_text     STRING,    -- localized description
  demo_rain_flag          BOOL,      -- weatherCondition.type is a rain type; catches light rain that qpf misses
  demo_icon_uri           STRING,
  demo_precip_probability FLOAT64,
  demo_thunderstorm_prob  FLOAT64,
  demo_feels_like_c       FLOAT64,
  demo_uv_index           INT64,
  demo_visibility_km      FLOAT64,
  demo_cloud_cover        INT64,
  demo_is_daytime         BOOL,
  -- raw
  raw                JSON,
  fetched_at         TIMESTAMP
)
PARTITION BY DATE(slot_time)
CLUSTER BY site_id;
```

## Places
Places ToS storage limits are waived for the demo (2026-10-07). Places responses (details, ratings, reviews, Nearby and Aggregate results) may be stored to measure their quality before Places Aggregate is relied on. `place_id` stays the site anchor. Test-fetch results: `docs/plans/places-test-fetch.md`.

## Places tables
Written by the Cloud Run job `places-profiler` (`places_job/`, bead `.4.6`), weekly plus manual runs. DDL: the Places section at the end of `sql/ddl.sql`. All three are partitioned by `DATE(fetched_at)` and clustered by `site_id`.

**Runs.** One run has one `run_id`; its rows share one `fetched_at`, except after a Cloud Run retry (see below). `run_id` is the Cloud Run execution name (`CLOUD_RUN_EXECUTION`, the same for every attempt of a task; a uuid when run outside Cloud Run). The job MERGEs each table on a key that starts with `run_id`: a Cloud Run retry of the same execution overwrites its own rows, and a new execution (the next Monday, or `gcloud run jobs execute`) has a new `run_id` and only adds rows, so earlier runs are never touched. A retry overwrites the rows it fetches again, `fetched_at` included, and leaves rows it did not return with the first attempt's `fetched_at`; so one `run_id` can hold two `fetched_at` values a few minutes apart. `run_id` is therefore the run key, and `fetched_at` is only the partition column: take the latest run as the `run_id` of the row with the greatest `fetched_at` (filter `fetched_at` to bound the scan), then filter `run_id = <that>`. Only successful API calls produce rows: a failed call leaves no row, it is not stored as null.

**Column groups.** core + `raw`. No `demo_*` column: Place Details, Nearby Search and Places Aggregate are the production sources, so nothing here is demo-only and no Places panel carries a "demo-only" badge.

| Table | Grain (MERGE key) | Rows per run |
|---|---|---|
| `places_details` | `run_id`, `site_id` | 10 |
| `places_nearby` | `run_id`, `site_id`, `radius_m`, `place_id` | up to 20 per site and radius; about 240 observed |
| `places_aggregate` | `run_id`, `site_id`, `place_type`, `radius_m` | 15 types × 3 radii × 10 sites = 450 |

### places_details
| Column | Type | Source |
|---|---|---|
| `run_id`, `site_id`, `fetched_at` | STRING, STRING, TIMESTAMP | run; `sites.site_id` |
| `place_id` | STRING | `id` |
| `display_name` | STRING | `displayName.text` |
| `rating`, `user_rating_count` | FLOAT64, INT64 | `rating`, `userRatingCount` |
| `business_status`, `primary_type` | STRING | `businessStatus`, `primaryType` |
| `open_now` | BOOL | `currentOpeningHours.openNow` at `fetched_at` |
| `weekday_descriptions` | ARRAY<STRING> | `regularOpeningHours.weekdayDescriptions` (language `id`) |
| `utc_offset_minutes` | INT64 | `utcOffsetMinutes` |
| `reviews` | ARRAY<STRUCT<rating INT64, text STRING, language STRING, publish_time TIMESTAMP, author_name STRING>> | `reviews[]`: `rating`, `originalText.text`, `originalText.languageCode`, `publishTime` (cut to microseconds), `authorAttribution.displayName`. At most 5 per site |
| `raw` | JSON | the whole response, requested with the full field mask of `scripts/places_test_fetch.py` (36 fields) |

### places_nearby
Nearby Search: `includedTypes = [gas_station]`, `rankPreference = DISTANCE`, `maxResultCount = 20`, radii 1000 and 3000 m, centred on the site's Details location. 20 results means the list is capped, so a count is a lower bound.

| Column | Type | Source |
|---|---|---|
| `run_id`, `site_id`, `radius_m`, `place_id`, `fetched_at` | | `place_id` is the result place |
| `name` | STRING | `displayName.text` |
| `brand` | STRING | `Pertamina`, `Shell`, `BP`, `Vivo` or `other`, derived from `name` by `brand_of` |
| `primary_type`, `rating`, `user_rating_count`, `business_status` | | same fields as Details |
| `distance_m` | INT64 | haversine from the site's Details location; the API does not return it |
| `rank` | INT64 | 1-based position in the response (distance order) |
| `raw` | JSON | the one result, with `fuelOptions` (0 of 240 filled in the test fetch) |

The site itself is in the results and is stored like any other place. Exclude it when counting competitors: `place_id != sites.place_id`.

### places_aggregate
Places Aggregate `computeInsights`, `INSIGHT_COUNT`, circle around `places/<place_id>`, operational places only. The 15 types are those of the test fetch; radii 500, 1000 and 3000 m.

| Column | Type | Source |
|---|---|---|
| `run_id`, `site_id`, `place_type`, `radius_m`, `fetched_at` | | |
| `count` | INT64 | `count`; the API omits it for zero, stored as 0 |
| `raw` | JSON | the response |
