# Data sources — demo vs production

The demo uses stand-in sources for licensed production ones. Decided 2026-10-06.

| Layer | Demo source | Production source |
|---|---|---|
| Traffic | Routes API `computeRoutes` (TRAFFIC_AWARE), every 30 min, cached in BigQuery as a "pretend RMI" feed | Roads Management Insights (pending Google approval; includes the license to cache traffic data) |
| Weather | Google Weather API `currentConditions`, cached per 30-min slot | WeatherNext (Earth Engine) |
| Places | Places API (New) + Places Aggregate, fetched live | Same |

Rules:

- Every ingested table has three column groups (spec: `docs/plans/data-schema.md`):
  - **core**: RMI- or WeatherNext-compatible. Metrics and any widget meant for production build only on core columns.
  - **`demo_*`**: only available from the demo source. Widgets that use them carry a visible "demo-only" label.
  - **`raw`**: the full API response as `JSON`.
- Routes and Weather caching limits in the Maps ToS are accepted for the demo. Do not re-raise them as blockers.
- Places: store only `place_id` long-term. Ratings and reviews are fetched live. Reviews are displayed with author attribution and a Google Maps link. Places content shown without a map carries the Google Maps logo/text.
- Any map view uses a Google basemap (Maps JS), never Leaflet, OSM or Mapbox.
