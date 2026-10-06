-- Dataset `traffic` (asia-southeast2) in gcp-coe-sandbox. Spec: docs/plans/data-schema.md.
-- Run via scripts/bq_setup.sh; safe to re-run (tables IF NOT EXISTS, views OR REPLACE).

CREATE TABLE IF NOT EXISTS traffic.sites (
  site_id      STRING NOT NULL,   -- SPBU number, e.g. "34.121.03"; surrogate if Places shows none (site 5: "KM57A")
  name         STRING,
  place_id     STRING NOT NULL,   -- Places place_id: the anchor (storable indefinitely)
  location     GEOGRAPHY,         -- from Place Details
  road_name    STRING,
  city         STRING
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
