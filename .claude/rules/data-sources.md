# Data sources — demo vs production

The demo uses stand-in sources for licensed production ones. Decided 2026-10-06.

| Layer | Demo source | Production source |
|---|---|---|
| Traffic | Routes API `computeRoutes` (TRAFFIC_AWARE), every 30 min, cached in BigQuery as a "pretend RMI" feed | Roads Management Insights (pending Google approval; includes the license to cache traffic data) |
| Weather | Google Weather API `currentConditions`, cached per 30-min slot | WeatherNext (Earth Engine) |
| Places | Places API (New) + Places Aggregate, fetched and stored for quality measurement | Same |

Rules:

- Every ingested table has three column groups (spec: `docs/plans/data-schema.md`):
  - **core**: RMI- or WeatherNext-compatible. Metrics and any widget meant for production build only on core columns.
  - **`demo_*`**: only available from the demo source. Widgets that use them carry a visible "demo-only" label.
  - **`raw`**: the full API response as `JSON`.
- Maps ToS storage and caching limits are waived for the demo, for Routes, Weather **and Places** (Places waived 2026-10-07). Places responses, including ratings, reviews and locations, may be stored and cached so their quality can be measured before Places Aggregate is relied on. Places display rules (review author attribution, Google Maps link or logo) are waived too. Do not re-raise any of these as blockers.
- `place_id` remains each site's anchor in `data/sites.csv`.
- Any map view uses a Google basemap (Maps JS), never Leaflet, OSM or Mapbox.
