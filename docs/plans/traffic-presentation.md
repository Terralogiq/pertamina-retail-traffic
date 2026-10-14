# Traffic presentation: minutes, bands, typical day

Beads: `pertamina-retail-traffic-907.11` (feature) and `.11.1`–`.11.7`. Parent epic: `pertamina-retail-traffic-907`. Signed off in `docs/plans/chart-research.md` (Decision, 2026-10-08). This plan is that decision, broken into beads. Schema: `docs/plans/data-schema.md`. The screens it changes are the ones in `docs/plans/dashboard.md`.

## Goal

Operators read delay in minutes, against each leg's own usual time. The map, the site page and the overview use one band rule and the Google-familiar colours. The day × hour heatmap and the three per-metric charts give way to a typical-day profile until four weeks of data exist. Busy hours are a list, not a chart, and they stay hidden until seven days.

## Where the tracker stands

The shared beads database on `refs/dolt/data` has the epic through `.8`. Later work (dashboard `.4.2`–`.4.7`, redesign `.9`, reviews `.10`) is in git and in `docs/plans/`, and those bead ids were never pushed. This plan does not recreate them. It adds the next feature, `.11`, and leaves the still-open tracker rows below alone.

| Bead | Tracker status | What to do with it |
|---|---|---|
| `.7.8` | in progress | Health-check the collector, then close it. Acceptance is a full day of slots; the job has been running since 2026-10-06. |
| `.7.13` | blocked by `.7.8` | Compare `rain_flag` and `demo_rain_flag` once `.7.8` closes. |
| `.7.6` | open | `demo_rerouted`, collector phase 2. Spec stays in `docs/plans/collector.md`. |
| `.7.12` | blocked by `.7.8` | Dedicated service accounts. |
| `.4.1` | open | The stack decision is already made (custom app, `docs/plans/dashboard.md`). Close it together with `.4.2`–`.4.5` after a check that those screens match their acceptance. Closing `.4.1` alone would mark the built screens as ready work. |
| `.4` and children `.4.2`–`.4.5` | open, blocked by `.4.1` | Built. Do not rebuild them from this plan. |
| `.5` | open | Recheck Weather and Places prices. Unrelated. |
| `.8` | open | Its children are closed. Places profiling for the demo is done. |

## Decisions (already signed off)

| Topic | Rule |
|---|---|
| Unit | Delay in minutes. `congestion_index` is the band driver and a secondary "× usual time". Displayed delay is `max(delay_s, 0)`. |
| Bands | Free flow below 1.5×, or under the delay gate. Moderate 1.5–2.0. Heavy 2.0–3.0. Jammed at 3.0 and over. |
| Delay gate | A reading stays Free flow unless it is both at least 1.5× usual and at least 20 s slower (urban) or 30 s slower (toll). The same gate is what keeps a short spike out of Heavy and Jammed. |
| Road class | `toll` when `lower(road_type)` contains `toll`, otherwise `urban`. Site 5 (`toll rest area`) is the only toll site. The CSV column already exists; BigQuery `sites` does not have it yet. |
| Provisional free flow | While `baseline_samples < 302`, usual speed is 45 km/h urban and 80 km/h toll. Provisional delay is `duration_s - expected_distance_m / that speed`. The same band thresholds and delay gate apply to that delay. |
| Colours | `#1e8e3e` / `#f29900` / `#e8452c` / `#9a1a1a`. Shape and text label stay on every band. Amber keeps the dark casing it already has. |
| Typical day | Median delay by local hour, shaded p25–p75, one line per leg, weekday and weekend apart. Fade an hour with fewer than 4 readings. Disclose n. |
| Busy hour | A local hour where at least half the readings are Moderate or worse and the median delay is at least 30 s. Consecutive busy hours are one peak window. All 24 hours. |
| Weekend | Saturday, Sunday, and hari libur nasional from SKB 3 Menteri No. 1497/2/5 of 2025. Cuti bersama stays a weekday. |
| Hidden until ready | Busy-hours list and any ranking: until 7 distinct local dates, with "needs N more days". Weekday × hour heatmap in minutes: until 4 weeks (bead `.11.7`, deferred to 2026-11-03). |
| Language | English. |
| Scope | No new metric. Core columns only. Demo-only badges stay where `dashboard.md` put them. |

### Band examples the tests pin

Urban gate 20 s, toll gate 30 s. Index is `congestion_index` once the baseline is full.

| Index | Delay | Class | Band |
|---|---|---|---|
| 1.4 | 40 s | urban | Free flow |
| 1.6 | 15 s | urban | Free flow |
| 1.6 | 25 s | urban | Moderate |
| 2.2 | 25 s | urban | Heavy |
| 3.1 | 40 s | urban | Jammed |
| 2.5 | 15 s | urban | Free flow |
| 1.8 | 25 s | toll | Free flow |
| 1.8 | 35 s | toll | Moderate |

### 2026 national holidays (weekend for this feature)

1 Jan, 16 Jan, 17 Feb, 19 Mar, 21 Mar, 22 Mar, 3 Apr, 5 Apr, 1 May, 14 May, 27 May, 31 May, 1 Jun, 16 Jun, 17 Aug, 25 Aug, 25 Dec. A Monday holiday (17 Aug 2026) is a weekend day. A cuti bersama Monday (16 Feb 2026) is a weekday.

## API

`GET /api/traffic/typical-day?site_id=` reads `v_traffic` joined to `routes` and `sites`, `slot_time` filtered, at most 28 days. Local hour and local date use `sites.timezone`.

Each leg × `day_kind` (`weekday` or `weekend`) × hour 0–23 returns `median_delay_s`, `p25_delay_s`, `p75_delay_s` and `n`. The response includes `days` (distinct local dates) and `ready` (`days >= 7`).

`.11.4` adds, on the same payload, `busy` per hour and `windows` (start hour, end hour, median delay) per leg and day kind. When `ready` is false, `windows` is empty.

`GET /api/sites` gains `road_type` and `road_class` (`urban` or `toll`).

## Screens

1. **Map and overview.** Legs use the new bands. The provisional state says the usual travel time is not ready yet and shows `n of 302`, not a calendar date. The overview keeps "N of 10 sites slowed", counted with the new bands.
2. **Site, traffic.** One delay chart for the recent series (24 h / 7 d). Speed and × usual time stay in the tooltip. Displayed delay is never negative.
3. **Site, typical day.** Replaces the three per-metric charts and the day × hour heatmap. Headline, weekday/weekend control, median line, middle-50% band, n, faded thin hours.
4. **Busy hours.** A list ("Weekdays 07:00–09:00 · usually 2–4 min slower") and a 24-cell strip. Hidden, with the "needs N more days" note, until `ready`.
5. **Table.** "Show as table" on the delay chart and the typical-day chart. Same numbers as the chart.

## Phases

### `.11.1` Recalibrate bands

`legBand` takes the latest row plus `road_class` and `expected_distance_m`. Thresholds, delay gate and provisional speeds are the tables above. Legend copy matches. The baseline notice counts readings and drops the fixed date.

Acceptance: the band examples pass in `bands.test.ts`. `sites.road_type` is loaded. `/api/sites` returns `road_class: "toll"` for KM57A and `"urban"` for the other nine. Build & test is green.

### `.11.2` Band colours

`BANDS` colours become `#1e8e3e`, `#f29900`, `#e8452c`, `#9a1a1a`. Shapes and labels stay. Amber keeps its dark edge.

Acceptance: the palette test reads the new hex values. No other series or sequential colour changes.

### `.11.3` Typical-day profile

New endpoint and `dashboard/api/holidays.py` with the 2026 list. The site page shows the profile and drops the heatmap and the extra metric charts. The recent delay chart remains, one chart, tooltip for speed and × usual time.

Acceptance: 17 Aug 2026 classifies as weekend and 16 Feb 2026 as weekday, in a test that does not call BigQuery. An hour with `n < 4` is marked faded. `days` and `ready` are on the payload.

### `.11.4` Busy hours

Busy flag and windows on the typical-day payload, using the same band rule as `.11.1`. List and strip on the site page. The overview does not rank sites by busy hour until `ready`.

Acceptance: a fixture hour with 3 of 4 readings at 1.6× and 25 s, median delay 40 s, is busy; the same hour with median delay 20 s is not. `windows` is empty when `days < 7`.

### `.11.5` Headlines and vocabulary

Each traffic card gets one generated headline in minutes ("Approach is slowest 07:00–09:00, about 3 min slower than usual"). `formatDelay` never returns a negative duration.

Acceptance: a delay of −2 s renders as no delay. The headline uses the busiest window when `ready`, and a neutral "not enough days yet" line when it is not.

### `.11.6` Table view

A "Show as table" control on the delay chart and the typical-day chart. The table is the chart's data, with the band label as text.

Acceptance: both cards expose the control, and the table has one row per plotted point.

### `.11.7` Later (deferred until 2026-11-03)

Weekday × hour heatmap in minutes, week-over-week, and a p95 "worst case". Not started before four weeks of slots.

## File ownership

| Path | Owner | Notes |
|---|---|---|
| `dashboard/web/src/map/bands.ts`, `bands.test.ts`, `Legend.tsx` | `.11.1` | Band rule and legend copy |
| `dashboard/web/src/map/api.ts` (`Site.road_class`), `map/Overview.tsx`, `site/SiteDetail.tsx` baseline notice | `.11.1` | `.11.3` edits other parts of `SiteDetail.tsx` after `.11.1` |
| `map/severity.ts`, `map/LegPopup.tsx`, `map/TrafficMap.tsx` and their tests | `.11.1` | Call sites of `legBand` / `legColor`. They pass `road_class` and the leg distance. No other change. |
| `sql/ddl.sql` (`sites.road_type`), `docs/plans/data-schema.md` sites section, `scripts/load_reference.py`, `tests/test_load_reference.py` | `.11.1` | Column only. Do not edit the Places or reviews sections |
| `dashboard/api/routers/sites.py`, `tests/test_dashboard_sites.py` | `.11.1` | |
| `dashboard/web/src/theme/palette.ts`, `palette.test.ts` | `.11.2` | `BANDS` colours only |
| `dashboard/api/holidays.py`, `dashboard/api/routers/traffic.py` typical-day, `tests/test_dashboard_traffic.py` | `.11.3` | `.11.4` adds the busy fields to this endpoint after `.11.3` |
| `dashboard/web/src/traffic/` profile, delay chart, heatmap removal | `.11.3` | |
| `dashboard/web/src/site/SiteDetail.tsx` traffic and pattern sections | `.11.3` | After `.11.1` |
| Busy-hour SQL and fields, `dashboard/web/src/traffic/BusyHours.tsx`, overview ranking guard | `.11.4` | After `.11.3` |
| `dashboard/web/src/traffic/headlines.ts`, `formatDelay` clamp | `.11.5` | After `.11.4`, so the headline can name a window |
| Table toggle | `.11.6` | After `.11.5` |
| `README.md`, this file | orchestrator | |

Order:

1. `.11.1` in parallel with `.11.2`.
2. `.11.3`.
3. `.11.4`, then `.11.5`, then `.11.6`.
4. `.11.7` stays deferred until 2026-11-03.

`scripts/build-and-test.sh` stays the gate. No new runtime dependency.
