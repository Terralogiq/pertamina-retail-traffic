-- Dataset `traffic` (asia-southeast2) in gcp-coe-sandbox. Spec: docs/plans/data-schema.md.
-- Run via scripts/bq_setup.sh; safe to re-run (tables IF NOT EXISTS, views OR REPLACE).

CREATE TABLE IF NOT EXISTS traffic.sites (
  site_id      STRING NOT NULL,   -- SPBU number, e.g. "34.121.03"; surrogate if Places shows none (site 5: "KM57A")
  name         STRING,
  place_id     STRING NOT NULL,   -- Places place_id: the anchor (storable indefinitely)
  location     GEOGRAPHY,         -- from Place Details
  road_name    STRING,
  city         STRING,
  road_type    STRING,            -- text from data/sites.csv; road_class is toll when this contains "toll"
  timezone     STRING             -- IANA zone: Asia/Jakarta (WIB) or Asia/Makassar (WITA)
);

CREATE TABLE IF NOT EXISTS traffic.routes (
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

CREATE TABLE IF NOT EXISTS traffic.traffic_snapshots (
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

CREATE TABLE IF NOT EXISTS traffic.weather_slots (
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

-- CREATE ... IF NOT EXISTS leaves old tables as they were: bring them up to date.
ALTER TABLE traffic.weather_slots ADD COLUMN IF NOT EXISTS demo_rain_flag BOOL;
ALTER TABLE traffic.sites ADD COLUMN IF NOT EXISTS timezone STRING;
ALTER TABLE traffic.sites ADD COLUMN IF NOT EXISTS road_type STRING;

-- Free-flow time per leg: 10th-percentile duration over the trailing 7 days of slots.
-- Needs about 7 days of data before it is meaningful. Core columns only.
CREATE OR REPLACE VIEW traffic.v_leg_baseline AS
SELECT DISTINCT
  selected_route_id,
  PERCENTILE_CONT(duration_in_seconds, 0.1) OVER (PARTITION BY selected_route_id) AS baseline_s,
  COUNT(duration_in_seconds) OVER (PARTITION BY selected_route_id) AS sample_count
FROM traffic.traffic_snapshots
WHERE slot_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  AND duration_in_seconds IS NOT NULL;

-- Snapshots with congestion measured against our own baseline (null while a leg has no baseline).
CREATE OR REPLACE VIEW traffic.v_traffic AS
SELECT
  t.*,
  b.baseline_s,
  b.sample_count AS baseline_samples,
  SAFE_DIVIDE(t.duration_in_seconds, b.baseline_s) AS congestion_index,
  t.duration_in_seconds - b.baseline_s AS delay_s
FROM traffic.traffic_snapshots AS t
LEFT JOIN traffic.v_leg_baseline AS b USING (selected_route_id);

-- Places tables (bead .4.6, job places-profiler). One run = one run_id (rows share one fetched_at, except
-- after a Cloud Run retry: select the latest run by run_id, see data-schema.md); the job MERGEs on a key that starts with run_id, so a retry of the same Cloud Run
-- execution does not duplicate and a new run adds rows. No demo_* columns: Details, Nearby Search and
-- Places Aggregate are the production sources too.
CREATE TABLE IF NOT EXISTS traffic.places_details (
  -- core
  run_id               STRING NOT NULL,     -- CLOUD_RUN_EXECUTION (uuid when run locally)
  site_id              STRING NOT NULL,
  fetched_at           TIMESTAMP NOT NULL,
  place_id             STRING,              -- as returned by Details (may differ from sites.place_id if Google merged ids)
  display_name         STRING,
  rating               FLOAT64,
  user_rating_count    INT64,
  business_status      STRING,              -- OPERATIONAL | CLOSED_TEMPORARILY | CLOSED_PERMANENTLY
  primary_type         STRING,
  open_now             BOOL,                -- currentOpeningHours.openNow at fetched_at
  weekday_descriptions ARRAY<STRING>,       -- regularOpeningHours.weekdayDescriptions, language id
  utc_offset_minutes   INT64,
  reviews              ARRAY<STRUCT<rating INT64, text STRING, language STRING, publish_time TIMESTAMP, author_name STRING>>,
  -- raw
  raw                  JSON                 -- the whole Details response (full field mask)
)
PARTITION BY DATE(fetched_at)
CLUSTER BY site_id;

CREATE TABLE IF NOT EXISTS traffic.places_nearby (
  -- core
  run_id            STRING NOT NULL,
  site_id           STRING NOT NULL,
  radius_m          INT64 NOT NULL,         -- 1000 | 3000
  place_id          STRING NOT NULL,        -- the result place (a gas station); may be the site itself
  fetched_at        TIMESTAMP NOT NULL,
  name              STRING,
  brand             STRING,                 -- Pertamina | Shell | BP | Vivo | other, derived from name (brand_of)
  primary_type      STRING,
  distance_m        INT64,                  -- haversine from the site's Details location; not in the API response
  rating            FLOAT64,
  user_rating_count INT64,
  business_status   STRING,
  rank              INT64,                  -- 1-based position in the DISTANCE-ranked response (max 20 results)
  -- raw
  raw               JSON                    -- the one result place
)
PARTITION BY DATE(fetched_at)
CLUSTER BY site_id;

CREATE TABLE IF NOT EXISTS traffic.places_aggregate (
  -- core
  run_id      STRING NOT NULL,
  site_id     STRING NOT NULL,
  place_type  STRING NOT NULL,              -- Places type, e.g. "restaurant"
  radius_m    INT64 NOT NULL,               -- 500 | 1000 | 3000
  fetched_at  TIMESTAMP NOT NULL,
  count       INT64,                        -- operational places of that type within the circle around the site's place_id
  -- raw
  raw         JSON                          -- the computeInsights response
)
PARTITION BY DATE(fetched_at)
CLUSTER BY site_id;

-- Review tables (bead .10.14, job reviews-poller, legacy Place Details; see data-schema.md "Reviews tables").
-- place_reviews: one row per distinct review, MERGEd on review_key. Not partitioned: published_at spans years
-- (2017 onward) and the MERGE looks a row up by review_key, so no partition could be pruned; a few thousand rows
-- a year do not need one. raw holds the author fields; analysis reads v_place_reviews instead.
CREATE TABLE IF NOT EXISTS traffic.place_reviews (
  -- core
  review_key        STRING NOT NULL,        -- sha256 hex of place_id | author_url (without it: place_id | author_name | time)
  site_id           STRING NOT NULL,
  place_id          STRING NOT NULL,        -- sites.place_id at fetch time
  published_at      TIMESTAMP,              -- review `time` (epoch seconds, UTC)
  rating            INT64,                  -- 1..5
  text              STRING,                 -- review text in its original language; NULL when the review has none
  language          STRING,                 -- review `language` (absent for rating-only reviews)
  original_language STRING,
  first_seen_at     TIMESTAMP NOT NULL,     -- fetched_at of the first poll that returned it
  last_seen_at      TIMESTAMP NOT NULL,     -- fetched_at of the latest poll that returned it
  seen_in           ARRAY<STRING>,          -- variants that returned it: newest_id | most_relevant_id | most_relevant_en
  -- raw
  raw               JSON                    -- the review object as returned, author fields included
)
CLUSTER BY site_id;

-- One row per API call: rating and review count over time, to measure the real review rate per site.
CREATE TABLE IF NOT EXISTS traffic.place_review_snapshots (
  -- core
  run_id             STRING NOT NULL,       -- CLOUD_RUN_EXECUTION (uuid when run locally)
  site_id            STRING NOT NULL,
  mode               STRING NOT NULL,       -- newest | sample
  variant            STRING NOT NULL,       -- <reviews_sort>_<language>, e.g. newest_id
  fetched_at         TIMESTAMP NOT NULL,
  user_ratings_total INT64,                 -- result.user_ratings_total (all-time count)
  rating             FLOAT64,               -- result.rating
  n_reviews          INT64,                 -- reviews returned by this call (max 5)
  -- raw
  raw                JSON                   -- the whole Place Details response of that call (key-free; reviews carry author fields)
)
PARTITION BY DATE(fetched_at)
CLUSTER BY site_id;

-- CREATE ... IF NOT EXISTS leaves an old table as it was: bring it up to date.
ALTER TABLE traffic.place_review_snapshots ADD COLUMN IF NOT EXISTS raw JSON;

-- Reviews for analysis without author name, profile URL or photo (raw is left out too: it holds them).
CREATE OR REPLACE VIEW traffic.v_place_reviews AS
SELECT
  review_key, site_id, place_id, published_at, rating, text, language, original_language,
  first_seen_at, last_seen_at, seen_in
FROM traffic.place_reviews;

-- place_review_labels (bead .10.5.1): derived labels per review and method (manual | gemini), MERGEd on
-- (review_key, method) so a new taxonomy or model version replaces that method's row. Holds labels and a
-- masked English gist, never review text or author fields. Not partitioned, same reasoning as place_reviews.
CREATE TABLE IF NOT EXISTS traffic.place_review_labels (
  -- core
  review_key    STRING NOT NULL,            -- key into place_reviews
  site_id       STRING NOT NULL,            -- from v_place_reviews at label time
  labels        ARRAY<STRING>,              -- taxonomy values (docs/plans/complaints-analysis.md)
  sentiment     STRING,                     -- neg | mixed | pos
  praise_only   BOOL,                       -- true when sentiment is pos
  gist          STRING,                     -- one-line English gist, masked; no text, no author
  method        STRING NOT NULL,            -- manual | gemini
  model_version STRING,                     -- taxonomy_v1 (manual) | gemini-<ver>/<prompt version>
  labeled_at    TIMESTAMP NOT NULL
)
CLUSTER BY site_id;
