# Data schema — SPBU traffic demo

Decided 2026-10-06. Each table has three column groups:

- **core** — compatible with the production sources (RMI for traffic, WeatherNext for weather). Anything meant to survive the switch to production builds only on these.
- **demo_*** — only available from the demo sources (Routes API, Google Weather API). Dashboard widgets that use them get a "demo-only" label.
- **raw** — the full API response as `JSON`, so a field can be added later without collecting again.

Ingestion: Cloud Scheduler (`*/30 * * * *`, Asia/Jakarta) → Cloud Run job → BigQuery. Times are stored in UTC and slots are aligned to :00 and :30.

TODO: check the RMI BigQuery export field names and the WeatherNext variable list against current docs before the first ingest.

## sites
```sql
CREATE TABLE traffic.sites (
  site_id      STRING NOT NULL,   -- SPBU number, e.g. "31.128.02"
  name         STRING,
  place_id     STRING,            -- Places place_id (storable indefinitely)
  location     GEOGRAPHY,
  road_name    STRING,
  city         STRING
);
```

## routes  (later becomes RMI Roads Selection registrations)
```sql
CREATE TABLE traffic.routes (
  route_id          STRING NOT NULL,  -- "<site_id>-<dir>"
  site_id           STRING NOT NULL,
  direction         STRING,           -- e.g. "NB", "SB", or a destination name
  origin            GEOGRAPHY,
  origin_heading    INT64,            -- degrees, pins the carriageway
  destination       GEOGRAPHY,
  dest_heading      INT64,
  expected_polyline GEOGRAPHY,        -- reference line for the reroute check
  expected_distance_m INT64,
  active            BOOL
);
```

## traffic_snapshots
```sql
CREATE TABLE traffic.traffic_snapshots (
  -- core (RMI-compatible)
  route_id                    STRING NOT NULL,
  record_time                 TIMESTAMP NOT NULL,   -- slot time
  duration_in_seconds         INT64,
  static_duration_in_seconds  INT64,
  speed_reading_intervals     ARRAY<STRUCT<start_idx INT64, end_idx INT64, speed STRING>>,  -- NORMAL|SLOW|TRAFFIC_JAM; null at Pro tier
  -- derived (computed from core only)
  congestion_index            FLOAT64,  -- duration / static_duration
  delay_s                     INT64,    -- duration - static_duration
  speed_kmh                   FLOAT64,  -- expected_distance_m / duration
  -- demo-only (Routes API)
  demo_distance_m             INT64,
  demo_polyline               GEOGRAPHY,
  demo_rerouted               BOOL,     -- demo_distance_m deviates >10% from expected, or the polyline leaves a 30 m buffer around expected_polyline
  demo_routing_preference     STRING,
  -- raw
  raw                         JSON,
  fetched_at                  TIMESTAMP
)
PARTITION BY DATE(record_time)
CLUSTER BY route_id;
```

## weather_slots
```sql
CREATE TABLE traffic.weather_slots (
  -- core (WeatherNext-compatible)
  site_id            STRING NOT NULL,
  slot_time          TIMESTAMP NOT NULL,
  temperature_c      FLOAT64,
  precipitation_mm   FLOAT64,
  rain_flag          BOOL,           -- precipitation_mm > 0.1
  relative_humidity  FLOAT64,
  wind_speed_kmh     FLOAT64,
  wind_direction_deg INT64,
  pressure_hpa       FLOAT64,
  source             STRING,         -- "google_weather" now, "weathernext" later
  -- demo-only (Google Weather currentConditions)
  demo_condition_type     STRING,    -- e.g. LIGHT_RAIN
  demo_condition_text     STRING,    -- localized description
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
Not ingested yet: the test fetch waits until the environment is set up and the 10 SPBU are confirmed. Under Places ToS only `place_id` is stored long-term (in `sites`). Ratings and reviews are fetched live by the frontend.
