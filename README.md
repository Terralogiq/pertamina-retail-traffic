# pertamina-retail-traffic

Terralogiq demo for Pertamina: monitors traffic on the road in front of 10 SPBU (fuel stations) every 30 minutes, alongside the weather and a Places-based profile of each site (nearby POIs, competitors, reviews).

**Status (2026-10-06):** research and data design are done. No code yet. Waiting on the SPBU list and a GCP project with the Maps APIs enabled.

## Data sources

The demo uses stand-in sources until the production ones are licensed. Binding rules: [`.claude/rules/data-sources.md`](.claude/rules/data-sources.md).

| Layer | Demo source | Production source |
|---|---|---|
| Traffic | Routes API `computeRoutes` (`TRAFFIC_AWARE`), every 30 min, cached in BigQuery as a "pretend RMI" feed | Roads Management Insights (RMI), pending Google approval |
| Weather | Google Weather API `currentConditions`, cached per 30-min slot | WeatherNext (Earth Engine) |
| Places | Places API (New) + Places Aggregate, fetched live | Same |

RMI is contract-gated and aimed at road operators. It covers only the customer's managed territory and can reject routes as `LOW_ROAD_USAGE` or `OUTSIDE_JURISDICTION`. It delivers data every 2 minutes over Pub/Sub, or every 10 minutes into BigQuery.

## Architecture

```
Cloud Scheduler (*/30, Asia/Jakarta)
  → Cloud Run job
      ├─ Routes computeRoutes   (2 segments per SPBU, one per direction)
      └─ Weather currentConditions (1 call per SPBU)
  → BigQuery dataset `traffic`
  → Dashboard: Maps JS basemap + charts from BigQuery + live Places panels
```

- Times are stored in UTC, and slots are aligned to :00 and :30.
- Frontend recommendation (not final): a custom app. Looker Studio can't make live Places calls with the review attribution Google requires.
- Maps use a Google basemap only (no Leaflet, OSM or Mapbox).

## Data model

Full DDL: [`docs/plans/data-schema.md`](docs/plans/data-schema.md).

| Table | Grain | Purpose |
|---|---|---|
| `sites` | SPBU | ID, name, `place_id`, location, road, city |
| `routes` | SPBU × direction | Segment endpoints with headings, plus the expected polyline and distance. Later becomes the RMI route registration. |
| `traffic_snapshots` | route × 30-min slot | Duration, static duration and derived metrics. Partitioned by date, clustered by `route_id`. |
| `weather_slots` | SPBU × 30-min slot | Temperature, precipitation, humidity, wind and pressure. Partitioned by date, clustered by `site_id`. |

Every table has three column groups:
- **core:** compatible with RMI or WeatherNext. Production metrics build only on these.
- **`demo_*`:** available only from the demo source. Widgets that use them show a "demo-only" label.
- **`raw`:** the full API response as `JSON`.

### Traffic metrics

| Metric | Formula | Note |
|---|---|---|
| `congestion_index` | `duration / staticDuration` | Our own measure, not one Google documents. Noisy on short segments, because durations are whole seconds. |
| `delay_s` | `duration − staticDuration` | |
| `speed_kmh` | `routes.expected_distance_m / duration` | Uses the registered distance, not the per-call distance, so it also works on RMI data. |
| `demo_rerouted` | distance differs >10% from expected, or the polyline leaves a 30 m buffer around the expected route | Demo-only check that the router stayed on the intended road. |

## Key API facts

- **Routes:** must set `routingPreference: TRAFFIC_AWARE`. The default `TRAFFIC_UNAWARE` returns `duration == staticDuration`, which carries no traffic signal.
- **Routes:** use `computeRoutes`, not `computeRouteMatrix`. A matrix bills every origin × destination pair, which wastes elements on independent segments.
- **Routes:** pin each waypoint with a `heading` so the router stays on the correct carriageway.
- **Routes:** `speedReadingIntervals` (NORMAL / SLOW / TRAFFIC_JAM) needs `extraComputations: TRAFFIC_ON_POLYLINE`. That bills at the Enterprise tier and gives route- and leg-level detail only. It is optional here.
- **No backfill:** a past `departureTime` is allowed only for transit, so history starts when the scheduler starts. Start collecting early.
- **Places:**
  - Store only `place_id` long-term; fetch ratings and reviews live.
  - Show reviews with author attribution and a Google Maps link.
  - Places content shown without a map needs the Google Maps logo or text.
  - Popular times is not available in any official API.

## Cost estimate

Prices as of 2026-10-06.

| Item | Volume / month | Price | Est. |
|---|---|---|---|
| Routes, 1 segment per SPBU | 10 × 48/day ≈ 14,400 | Pro $10/1k after 5k free | ≈ $94 |
| Routes, 2 segments per SPBU (planned) | ≈ 28,800 | Pro | ≈ $238 |
| Routes with `TRAFFIC_ON_POLYLINE` | — | Enterprise $15/1k after 1k free | optional |
| Weather `currentConditions` | 10 × 48/day ≈ 14,400 | $0.15/1k after 10k free* | ≈ $0.66 |
| Nearby Search | per profiling run | $32–40/1k by tier* | — |
| Place Details with reviews | live, per view | $25/1k* | — |
| Places Aggregate | per profiling run | $10/1k after 5k free* | — |

\* Taken directly from Google's pricing pages but not double-checked like the Routes prices. Recheck in the console; the Weather price looks low.

## Roadmap

Tracked in Beads (`bd ready`, epic `pertamina-retail-traffic-907`).

1. **Inputs:** the 10 SPBU (number or coordinates, main-road name, side of road) and the GCP project ID with Routes, Weather, Places (New) and Places Aggregate enabled.
2. **Collector:** plan in `docs/plans/collector.md`, then build Scheduler → Cloud Run → BigQuery. First check the RMI BigQuery export field names and the WeatherNext variable list.
3. **Places test fetch:**
   - Text Search to find each SPBU.
   - Place Details with reviews.
   - Nearby Search for `gas_station` competitors within 1–3 km.
   - Places Aggregate POI counts at 500 m, 1 km and 3 km.
   - Output: JSON samples plus field fill-rate for Indonesia.
4. **Dashboard frontend.**

## Repo layout

```
.claude/           harness: settings, Stop hook, advisor-reviewer agent, rules
docs/plans/        plans and specs (data-schema.md)
docs/handoffs/     session handoffs
scripts/           build-and-test.sh (created with the first code slice)
```

## Workflow

`/plan` → `docs/plans/<feature>.md` → Beads → claim → implement → Stop hook runs `scripts/build-and-test.sh` → `advisor-reviewer` → human review + CI → `bd close`. Details in [`CLAUDE.md`](CLAUDE.md).

## Tooling versions

- Claude Code: 2.1.291
- bd: 1.3.1 (Homebrew)
