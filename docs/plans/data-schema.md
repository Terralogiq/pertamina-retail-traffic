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
  road_type    STRING,            -- text from data/sites.csv; road_class is toll when this contains "toll"
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

**Runs.** One run has one `run_id`; its rows share one `fetched_at`, except after a Cloud Run retry (see below). `run_id` is the Cloud Run execution name (`CLOUD_RUN_EXECUTION`, the same for every attempt of a task; a uuid when run outside Cloud Run). The job MERGEs each table on a key that starts with `run_id`: a Cloud Run retry of the same execution overwrites its own rows, and a new execution (the next Monday, or `gcloud run jobs execute`) has a new `run_id` and only adds rows, so earlier runs are never touched. A retry overwrites the rows it fetches again, `fetched_at` included, and leaves rows it did not return with the first attempt's `fetched_at`; so one `run_id` can hold two `fetched_at` values a few minutes apart. `run_id` is therefore the run key, and `fetched_at` is only the partition column: take the latest run as the `run_id` of the row with the greatest `fetched_at` (filter `fetched_at` to bound the scan), then filter `run_id = <that>`. Only successful API calls produce rows: a failed call leaves no row, it is not stored as null. `/api/places` reads `places_nearby` per (site, radius) from the latest `fetched_at` within the run (bead `.4.10`), so a retry's re-fetched rows win over the first attempt's extras. If a retry's Nearby call for a radius fails, or succeeds with zero results, that radius still shows the first attempt's rows: neither case leaves a row to tell them apart.

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

## Reviews tables
Written by the Cloud Run job `reviews-poller` (`reviews_job/`, bead `.10.14`). DDL: the review section at the end of `sql/ddl.sql`. Source: the **legacy** Place Details endpoint (`maps.googleapis.com/maps/api/place/details/json`, `fields=reviews,user_ratings_total,rating`, `reviews_no_translations=true`), because only it takes `reviews_sort=newest`; Places API (New) returns 5 reviews in Google's order with no sort. Legacy Places is enabled only in `demogcp-terra2021`, so the job runs in `gcp-coe-sandbox`, writes to `traffic`, and reads the API key from Secret Manager in `demogcp-terra2021` (`maps-api-key`). Why newest-first and what each variant returns: `docs/plans/reviews-feasibility.md`, section "Test". Places storage limits are waived for the demo; core + `raw`, no `demo_*` column.

**Schedule and volume.** `--mode newest` runs once a day (`0 6 * * *` Asia/Jakarta): 1 call per site (`newest`, `id`). `--mode sample` runs weekly (`0 3 * * 1`): 3 calls per site (`newest_id`, `most_relevant_id`, `most_relevant_en`). About 10 x 30 + 130 = 430 calls a month, inside the 1,000 free calls a month cap. At KM57A (about 2.5 reviews a day) a daily newest-5 poll can miss reviews on a busy day; the snapshot table shows how often a poll returns 5 new ones. `--mode label` runs daily after it (`30 6 * * *` Asia/Jakarta, Scheduler job `reviews-poller-label`): it sends the text reviews that have no `gemini` row at the current `model_version` to the Gemini API (`gemini-3.8-flash`, 10 reviews per call, key from Secret Manager `gemini-api-key` in `gcp-coe-492507`) and MERGEs the labels into `place_review_labels`. The first run (2026-10-10) labelled all 129 text reviews in 13 calls; afterwards only the new text reviews are sent (a few a day, 0 to 2 calls), and a day with nothing new makes no call. Not part of the 1,000 free calls a month cap (that cap is for legacy Place Details only). Logs carry counts only, never review text or gists.

| Table | Grain (MERGE key) | Rows |
|---|---|---|
| `place_reviews` | `review_key` | one per distinct review; about 15 per site after the first sample, then the new reviews |
| `place_review_snapshots` | `run_id`, `site_id`, `variant` | 10 (newest) or 30 (sample) per run |
| `place_review_labels` | `review_key`, `method` | one per review per labelling method; 127 `manual` rows from the first pass |

### place_reviews
| Column | Type | Source |
|---|---|---|
| `review_key` | STRING | sha256 hex of `place_id|author_url` (one review per author per place; only when `author_url` is missing: `place_id|author_name|time`). Rating, text and time are not in the URL form, so an edited review keeps its row |
| `site_id`, `place_id` | STRING | `traffic.sites` |
| `published_at` | TIMESTAMP | `time` (epoch seconds) |
| `rating` | INT64 | `rating` |
| `text` | STRING | `text`; NULL when empty (a rating-only review) |
| `language`, `original_language` | STRING | same names; absent on rating-only reviews |
| `first_seen_at`, `last_seen_at` | TIMESTAMP | `fetched_at` of the first and the latest poll that returned the review |
| `seen_in` | ARRAY<STRING> | variants that returned it, e.g. `["newest_id", "most_relevant_id"]` |
| `raw` | JSON | the review object, author name, profile URL and photo URL included |

**Merge.** One MERGE per run on `review_key`: new reviews are inserted; a review seen again gets `last_seen_at = GREATEST(...)` and `seen_in` as the union of the old and new variants. `rating`, `text` and `raw` keep what was first seen (edits are not tracked). Re-running a poll, or a Cloud Run retry, only moves `last_seen_at`, so no run id is needed on this table. The same review comes back from several variants (in the test, one review came back from both `newest_id` and `most_relevant_id` at the urban site: 15 returned, 14 distinct); the job dedupes within a run before the MERGE.

**Partitioning.** `place_reviews` is clustered by `site_id` and **not partitioned**. `DATE(published_at)` would spread a few hundred rows over thousands of partitions (reviews date back to 2017), `DATE(first_seen_at)` has no use for a table this size (a few thousand rows a year), and the MERGE finds a row by `review_key`, so no partition filter can prune it either way. Partition if it ever grows past a few GB.

**View `v_place_reviews`.** All columns except `raw`: no author name, profile URL or photo. Use it for analysis (the feasibility plan's analysis input drops author fields).

### place_review_snapshots
One row per successful API call, to measure the review rate (growth of `user_ratings_total`) and the rating over time. Partitioned by `DATE(fetched_at)`, clustered by `site_id`; MERGE key `run_id`, `site_id`, `variant`, with the one-day `fetched_at` window of the places tables, so a Cloud Run retry overwrites its own rows.

| Column | Type | Source |
|---|---|---|
| `run_id`, `site_id`, `fetched_at` | STRING, STRING, TIMESTAMP | run; `traffic.sites` |
| `mode`, `variant` | STRING | `newest` or `sample`; `<reviews_sort>_<language>` |
| `user_ratings_total` | INT64 | `result.user_ratings_total` |
| `rating` | FLOAT64 | `result.rating` |
| `n_reviews` | INT64 | reviews in that response (at most 5) |
| `raw` | JSON | the whole Place Details response of that call (`status`, `result`; no API key in it). Its reviews carry author name, profile URL and photo URL, like `place_reviews.raw`; analysis uses `v_place_reviews`, which has no `raw` |

Core + `raw`, like the other tables. A failed call leaves no row. The job exits 1 when any call failed (after writing the successful ones) and Cloud Run retries once.

### place_review_labels
Derived table (bead `.10.5.1`): labels per review for the complaints analysis and the Review themes panel, written by `scripts/load_review_labels.py` (manual pass) and by `reviews_job --mode label` (Gemini, bead `.10.5.4`). Core columns only, no `raw`: it holds labels and a masked English gist, never review text or author fields. Clustered by `site_id`, not partitioned (same reasoning as `place_reviews`). Taxonomy and sentiment rules: `docs/plans/complaints-analysis.md`.

| Column | Type | Source |
|---|---|---|
| `review_key` | STRING | `place_reviews.review_key`; MERGE key with `method` |
| `site_id` | STRING | `v_place_reviews.site_id` for that `review_key`; cluster column |
| `labels` | ARRAY<STRING> | taxonomy values, e.g. `["antrian", "pelayanan_petugas"]` |
| `sentiment` | STRING | `neg`, `mixed` or `pos` |
| `praise_only` | BOOL | true when `sentiment` is `pos` |
| `gist` | STRING | one-line English gist, masked |
| `road_queue` | BOOL, nullable | `gemini` rows from prompt p4 on: true only when the review says the queue reaches the road or roadside (spills onto or blocks the road, or drivers wait on the shoulder); false for forecourt queues, slow service and jams not tied to the station's queue. `manual` rows and rows from older prompts are NULL. Added with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`; no backfill beyond the relabel. Readers treat NULL as false |
| `method` | STRING | `manual` or `gemini`; MERGE key with `review_key` |
| `model_version` | STRING | `taxonomy_v1` for `manual`; `gemini-3.8-flash/p1` (pinned model id + prompt version) for `gemini`. The model id and prompt version are constants in `reviews_job/gemini.py`; `PROMPT_VERSION` is bumped by hand (a test pins the prompt hash). A new `model_version` makes every text review unlabelled again, so the MERGE replaces the `gemini` rows |
| `labeled_at` | TIMESTAMP | when the row was written |

**Merge.** One MERGE on `(review_key, method)` per load: a rerun, or a new taxonomy or model version, overwrites that method's row and leaves the other method's row alone. The loader fails on a `review_key` that is not in `v_place_reviews` rather than writing a label with no site.

## ai_summaries
Derived table: AI summaries per site and 30-minute slot, written by the dashboard API (`dashboard/api/routers/summary.py`, `GET /api/sites/{site_id}/ai-summary`). Design: `docs/plans/ai-summaries.md`. DDL: the last section of `sql/ddl.sql`. **Proposed, not yet created**: the table does not exist until the DDL is applied, and until then the endpoint answers `summary: null`.

**Cadence (on demand).** The first site-page view in a slot looks the row up by `(site_id, slot_time, model, prompt_version)`. On a miss the API builds the facts, calls Gemini once and runs the validator; only a passing summary is MERGEd and shown, a failure shows no card and writes nothing (counts are logged). A view belongs to the slot that started at least 5 minutes earlier (it changes at :05 and :35 UTC, the dashboard cache boundary), so the slot's own traffic readings are in. At most one row per site and slot (480 a day at 10 sites); only slots with a view get one, up to about 1,500 a month at 50 views a day.

Core columns only (the facts use core columns and Places), no `demo_*`, no `raw`: `facts` is the model's whole input and `sentences` its checked output. Partitioned by `DATE(slot_time)` (the lookup filters it), clustered by `site_id`.

| Column | Type | Source |
|---|---|---|
| `site_id` | STRING | `traffic.sites`; MERGE key, cluster column |
| `slot_time` | TIMESTAMP | the :00/:30 UTC slot the summary serves; MERGE key, partition column |
| `as_of` | TIMESTAMP, nullable | the latest traffic slot in the facts (UTC); behind `slot_time` when the collector missed a slot; NULL when the site had no reading in 28 days |
| `generated_at` | TIMESTAMP | when the API wrote the row |
| `model` | STRING | pinned model id (`gemini-3.8-flash`); MERGE key |
| `model_version` | STRING | the response's `modelVersion`: ids alias forward, so this records what actually answered |
| `prompt_version` | STRING | `PROMPT_VERSION` in `dashboard/api/ai_summary.py` (`s5`); MERGE key |
| `facts` | JSON | the facts the model saw, one key per topic (`site`, `traffic`, `weather`, `places`, `review_themes`): aggregated delays, counts and the rating; label counts only, never review text, gists or authors |
| `sentences` | ARRAY<STRUCT<topic STRING, text STRING, ok BOOL, problems ARRAY<STRING>, number_matches ARRAY<STRUCT<number STRING, match STRING>>>> | the model's sentences in order with the validator's verdict; `topic` is `traffic`, `weather`, `places` or `review_themes` (one dashboard card each); `match` is `exact` or `rounded` |
| `validation_ok` | BOOL | the validator's verdict; true on every row, because only passing summaries are stored |
| `input_tokens`, `output_tokens` | INT64 | `usageMetadata.promptTokenCount`; `candidatesTokenCount` + `thoughtsTokenCount` (both bill as output). Cost is derived |
| `latency_ms` | INT64 | the Gemini call, retries included |

**Merge.** One MERGE per generated summary on `(site_id, slot_time, model, prompt_version)`. Two dashboard instances that miss the same slot at once both generate; the second MERGE overwrites the first's row. A new prompt or model version starts new rows beside the old ones.

**Access.** The dashboard's service account is a dataset READER; it needs `roles/bigquery.dataEditor` on this table only (step 4 of `scripts/deploy_dashboard.sh`, once the table exists).
