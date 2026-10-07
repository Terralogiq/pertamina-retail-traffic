# Dashboard UX review (bead `.9.1`)

Date: 2026-10-07. Method: `impeccable` critique + audit, **single-context** (degraded: run inside one forked agent, not two isolated assessments). Build: local `main` @ `700bc53`, vite dev + uvicorn, real BigQuery data (about 27 of 302 baseline samples per leg). Viewports: 1440×900 and 390×844. Screenshots: `out/ux-review/` (git-ignored). Plan: `docs/plans/dashboard-redesign.md`.

## Summary

The dashboard works and its data is right, but it presents as an unstyled prototype. There are no type, colour or spacing decisions: browser-default Times, links in default blue, default ECharts colours. It also fails at both of its main jobs at a glance:

- **"Where is traffic bad right now?"** The national map can't show 500 m legs, and the side list buries status in 10 identical cards.
- **"What is this site like?"** The site page is one 4,500 px column with no summary at the top.

Mobile is broken on the overview (a 70 px map strip with a clipped list) and on the rain view (the chart can't be read).

| Severity | Count |
|---|---|
| P0 blocking | 0 |
| P1 major | 8 |
| P2 minor | 9 |
| P3 polish | 4 |

Scores:

- **Nielsen heuristics: 17/40 (poor).** Visibility 1, match to the real world 2, user control 2, consistency 1, error prevention 2, recognition 2, efficiency 1, aesthetic 1, error recovery 2, help 3.
- **Technical audit: 9/20 (poor).**
  - Accessibility 2: no `main`/`nav`/`h1` on the overview, and status is shown by colour alone.
  - Performance 2: cold site page and rain view take 15–35 s with only a bare "Loading…".
  - Responsive 1.
  - Theming 0: 46 inline style blocks, no tokens.
  - Integrity 4: data and labels are honest; the demo-only labels are applied correctly.

Detector:

- **CLI scan:** ran degraded (HTML parser modules missing in the skill install) and found 0, which is an undercount.
- **In-browser scan:** found tiny 10–11 px text and a clipped overflow container. Most hits are Google Maps chrome ("Terms", "Keyboard shortcuts", scale bar), so they are false positives. The 11–12 px card metadata is a real finding.

## What works

- **Honest data states.** "Baseline building (27/302)", local WIB/WITA times, `*` on capped competitor counts and the "Excludes this station" note. Keep all of them through the redesign.
- **Demo-only labelling is correct and consistent.** It just needs to be quieter (F7).
- **Site page content is rich and correct:** three traffic charts with rain bars, a day × hour heatmap, weather, and Places with real reviews. The redesign is mostly hierarchy and layout, not missing data.

## Findings

| ID | Sev | Screen | Finding | Evidence | Proposed fix | Bead |
|---|---|---|---|---|---|---|
| F1 | P1 | Overview | At national zoom the 500 m legs are invisible. Markers are identical blue pins, so the map shows no traffic state. Four Jakarta-area pins overlap | `03b-overview-1440-loaded.png` | Colour each marker by its worst leg's current band, with a status ring and a delay label. Cluster or offset the Jakarta pins. Show legs only from about zoom 14 | `.9.4` |
| F2 | P1 | Overview | No "now" summary. You have to read 10 cards to find the worst site. Cards are ordered by `site_id`, not by severity | `03b-…` | Summary strip on top: sites slowed / free-flowing, worst delay with its site. Sort the list by current delay, with sort and filter controls | `.9.4` |
| F3 | P1 | Overview 390 | The map shrinks to a ~70 px strip next to the list. The legend wraps word by word. The list is clipped inside its own scroll | `04-overview-390.png` | Below ~768 px stack the map (≈45 vh) over the list, or use a map/list toggle. Put the legend in one line or a sheet | `.9.4` |
| F4 | P1 | Site detail | The page title is "Site 24.351.34", an ID. The SPBU name, city and road first appear deep inside the Places panel. No current-status summary at the top | `05b-site-wib-1440-loaded.png` | Header with name, SPBU code, city · road, local time and status chips (current delay per leg, weather now, rating). Keep the ID secondary | `.9.5` |
| F5 | P1 | Site detail | One 4,559 px column: map, 3 charts, 2 heatmaps, 4 weather cards, 4 Places cards. No sections or navigation, and no use of width at 1440 px | `05b-…` | Two-column grid at ≥1200 px (traffic left, weather and Places right), with section anchors or tabs: Traffic · Pattern · Weather · Places | `.9.5` |
| F6 | P1 | Rain view | All-sites bar chart with 20 groups and rotated full names that overlap. Sample sizes appear as a paragraph under the chart. Rain/dry bars with n = 2 look as solid as n = 27 | `09b-rain-1440-loaded.png`, `10-rain-390.png` | Horizontal bars or a small-multiples list sorted by rain − dry difference. Show n inline. Grey out or hatch bars below a minimum n (e.g. 6 rain slots) with an "insufficient rain data" note | `.9.6` |
| F7 | P1 | Overview cards | Every card repeats "baseline building (27/302)" and "DEMO-ONLY" (×10 each). The real signal, the delay, is the smallest text. The demo badge sits next to the temperature, which reads as if the temperature were demo-only (it's core; only the icon is demo) | `03b-…` | Show baseline status once at page level until it's ready. Pin the demo marker to the icon only (small corner tag or info dot), or drop the condition icon from the list. Make the delay the largest element on the card | `.9.2`, `.9.4` |
| F8 | P1 | All | Congestion bands are shown by colour alone (2 px squares by "Approach +18 s"). Red/orange/amber/green neighbours don't survive common colour-vision deficiencies | `03b-…`, `05b-…` | Band text label or icon next to the colour ("Slow", "Heavy"). Validated band palette with lightness steps. Also encode severity in line width on the map | `.9.2` |
| F9 | P2 | Site / rain | Cold loads take 15–35 s and show only plain "Loading…" lines. The layout jumps when content arrives. A blank 400 px map box sits there before tiles load | `05-site-wib-1440.png`, `09-rain-1440.png` | Skeletons at final size, one page-level progress indicator, and the map container's background set to the basemap colour. Backend latency is separate (BigQuery cold start); consider a warm-up on login | `.9.7` |
| F10 | P2 | Site charts | Default ECharts palette: approach blue / departure lime. The same lime marks "Dry" on the rain view and "Precipitation" in the weather chart, while traffic rain bars are light blue. One colour means three things | `05b-…`, `09b-…` | One chart theme: approach/departure as two tones of one hue, rain always the same blue, dry neutral grey | `.9.2`, `.9.5` |
| F11 | P2 | Site heatmap | The visual-map legend (1–2) overlaps x-axis hours 10–12. Empty cells look like low values (striped grey). The scale has no units and no meaning ("1 = free flow") | `06-site-heatmap-1440.png` | Move the legend to the right or top with "1.0 free flow → 2.0 twice as slow". Empty cells transparent, with a "no data yet" note. One shared scale for both legs | `.9.5` |
| F12 | P2 | Site charts 390 | The legend "Rain (mm)" collides with the right-axis "mm" label. The second axis shows 0–1 mm even when there was no rain (Makassar). The "WITA" label floats beside the axis | `08-site-charts-390.png` | Legend below the chart on narrow screens. Hide the rain axis when all values are 0. Put the time-zone label in the chart subtitle | `.9.5` |
| F13 | P2 | Site / rain 390 | Horizontal overflow (412 px content in a 390 px viewport) from the POI table | `07b-site-wita-390-loaded.png` | Scrollable table container with a sticky first column, or a card list on mobile | `.9.5` |
| F14 | P2 | Login | Browser-default form: no product name or logo, no label (placeholder only), an error message with no styling and no `aria-live`, a disabled grey button | `01-login-1440.png`, `02-login-error-1440.png` | Branded card with a visible label, an error in an `role=alert` region, and the button enabled while there's input | `.9.3` |
| F15 | P2 | Overview / shell | No `<main>`, `<nav>` or `<h1>`. The title is bold text. Navigation is an inline link row that changes per page (the overview lacks a self link; the rain page lacks a site list) | snapshot, `03b-…` | App shell: header with logo, persistent nav (Overview · Traffic vs rain · site picker), `main` landmark, one `h1` per page | `.9.3` |
| F16 | P2 | Rain view | Raw field names in the UI: "rain_flag (precipitation above 0.1 mm)", "demo_rain_flag (rain condition type)" | `09b-…` | "Measured rain (> 0.1 mm)" vs "Google weather condition (demo-only)". Keep field names in a tooltip | `.9.6` |
| F17 | P2 | Places | POI types shown raw ("car_repair", "electric_vehicle_charging_station"). Opening hours take 7 lines for "Buka 24 jam" every day | `05b-…` | Human labels for types, grouped (Food, Retail, Services…). Collapse identical hours to "Open 24 hours, every day" | `.9.5` |
| F18 | P3 | Traffic toggle | The selected range ("24 h") renders as a disabled button, so selected reads as unavailable | `08-site-charts-390.png` | Segmented control with `aria-pressed` and a selected style | `.9.5` |
| F19 | P3 | Overview | No favicon (404). The tab title is generic | console | Logo favicon; title "<page> · Pertamina Retail traffic" | `.9.2`, `.9.3` |
| F20 | P3 | Site detail | Card metadata at 11–12 px ("slot 13:30 WIB", city), below a comfortable reading size for secondary data | in-page detector, `03b-…` | Minimum 12–13 px with a tabular-number style for times and values | `.9.2` |
| F21 | P3 | Places | Reviews are shown in full, with no truncation; some run to 6 lines on mobile | `07b-…` | Clamp to 3 lines with "more", plus the review date relative ("3 weeks ago") | `.9.5` |

## Quick wins (no brand inputs needed)

- F15 landmarks plus one `h1` per page, and F14 login label and `role=alert`.
- F16 and F17 copy: human labels for flags and POI types; collapsed opening hours.
- F11 heatmap legend position and empty-cell styling; F12 hide the rain axis at 0 mm.
- F13 scrollable POI table; F18 segmented range control.
- F7 page-level baseline notice instead of 10 repeats.
- F2 sort the side list by current delay.

## Needs brand inputs (`.9.2`)

- Logo (SVG) for the header, login and favicon (F14, F15, F19).
- Brand palette: chrome only. The data palette (bands, series, rain) must be validated separately (F8, F10), and brand red must not double as "heavy traffic" without testing.
- Typeface (F20): brand font if licensed for web, otherwise a close Google Font. Pick a tabular-number face for values.
- Map style (F1): a cloud Map ID with a muted style, so brand-coloured markers and bands stand out.

## Notes

- Not covered: dark mode (no decision yet), screen-reader walkthrough beyond landmark and heading checks, and keyboard operation of map markers (10 markers are focusable; the tab order wasn't walked).
- Local review setup: uvicorn has to bind `::` (`--host ::`) for the vite proxy, because Node resolves `localhost` to IPv6. The Secure session cookie worked on `http://localhost` in Chromium.
