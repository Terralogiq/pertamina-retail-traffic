# Simplified overview: potential queues

Supersedes the screen in [overview-station-table.md](overview-station-table.md) (the "Stations at a glance" table and the live-traffic cards). Its two endpoints stay. Decisions by the user, 2026-10-15.

**Status (2026-10-15):** phases 1–4 shipped. **Group rules superseded 2026-10-21** by the risk levels below (red, yellow, green); the signals are unchanged.

## Why

The user found the table too complicated. The overview must answer, at any hour: which stations may have a queue that reaches the road, why, and what customers complain about. Checking traffic against recent queue complaints (2026-10-15, `out/queue_vs_reviews.json`) showed that most queue complaints describe queues inside the forecourt (understaffing, one open lane), which road data cannot and need not see. Only complaints that say the queue reaches the road are comparable with the traffic signal.

## Signals and groups

| Signal | Rule | Source |
|---|---|---|
| Traffic | The road is slower before the station than after it on at least 70% of days: tier `strong` or `moderate` from `GET /api/traffic/queue-risk`. `cannot_tell` (the road after the station is slower) never counts | Core columns, 28-day window |
| Reviews | At least 1 review from the last 12 months with `road_queue = true` | `place_review_labels.road_queue` (new, Gemini prompt p4) |

| Group (superseded 2026-10-21, see "Risk levels") | Rule | On 2026-10-15 |
|---|---|---|
| Potential queue | both signals | Pemogan |
| Traffic only | traffic signal, no road-queue review | MT Haryono, Makassar, Lingkar Selatan |
| Reviews only | road-queue review, no traffic signal | Gayungan, Tirtayasa, Daan Mogot (traffic cannot tell) |
| No signal | neither | Antasari, KM57A, Bandung |

"Queue" appears in the group name because the review signal is a person reporting a queue. A traffic signal on its own is still worded "slower before the station than after it".

## Risk levels (2026-10-21, user decision)

Replaces the four groups. The two signals and their rules are unchanged; the overview shows one of three levels per station.

| Level | Rule | Label | Map pill |
|---|---|---|---|
| Red | traffic signal (tier `strong` or `moderate`) and/or review signal (`road_queue_recent >= 1`); reviews win over `cannot_tell` | "Queue risk: traffic + reviews", "Queue risk: traffic", "Queue risk: reviews" | "Both", "Traffic", "Reviews" |
| Yellow | tier `cannot_tell` (both sides of the station slow together, so a queue cannot be told apart) and no review signal | "Busy road" | "Busy road" |
| Green | everything else: tier `weak` or `none`, no review signal | "Low queue risk" | "Low" |

- Desk-check confidence does not change the colour; the confidence level and reason stay in the expanded row.
- An unknown signal (endpoint failed) counts as absent and the row says it is unavailable.
- Colours reuse the traffic band tokens: red `--band-heavy`, yellow `--band-moderate`, green `--band-free` (chip and pill border, icon); label text stays `--ink-1` on `--surface-1`. Shapes: split diamond (red, left half traffic, right half reviews), bar (yellow), circle (green).
- Order: red (traffic + reviews, then traffic, then reviews), yellow, green; within a level the server's queue-risk order.
- Summary line, for example "7 queue risk · 2 busy road · 1 low", plus the fixed caption "Guidance from road traffic and sampled reviews, not a queue count." The map toggle and list heading read "Queue risk".

On 2026-10-21 (tiers: 61.761.03, 54.801.17, 74.902.22, 34.121.03 moderate; KM57A, 24.351.97 weak; 54.601.80 none; 34.117.12, 24.351.34, 34.401.16 `cannot_tell`; `road_queue_recent`: 24.351.97 = 1, 34.117.12 = 1, 54.601.80 = 2, 54.801.17 = 2, else 0):

| Level | Stations |
|---|---|
| Red, traffic + reviews | Pemogan 54.801.17 |
| Red, traffic | MT Haryono 61.761.03, Makassar 74.902.22, Lingkar Selatan 34.121.03 |
| Red, reviews | Gayungan 54.601.80, Tirtayasa 24.351.97, Daan Mogot 34.117.12 |
| Yellow | Antasari 24.351.34, Bandung 34.401.16 |
| Green | KM57A |

Pinned in `dashboard/web/src/overview/overview.test.tsx`. The sections below describe the 2026-10-15 group design; where they say "group", read "risk level".

## Road-queue flag (prompt p4)

Tested offline on all 139 text reviews on 2026-10-15 (`out/complaints/2026-10-15/`): 6 reviews flagged, all describing a queue that reaches the road. The queue + traffic-safety label combination had one clear false positive (Bandung, security not directing lanes) that the flag does not.

- `place_review_labels` gains `road_queue BOOL` (nullable; `manual` rows stay NULL). `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, no backfill beyond the relabel.
- Prompt p4 = p3 plus the rule tested offline: true only when the review says vehicles waiting for this station queue out of the site onto the road or roadside; false for forecourt queues, slow or understaffed service, and jams not tied to the station's queue. Required boolean in the response schema.
- The p4 label run replaces the p3 rows (MERGE on `review_key, method`).

## API change

`GET /api/review-themes`, per site, adds:

| Field | Meaning |
|---|---|
| `queue_recent` | Negative or mixed reviews from the last 12 months labelled `antrian` |
| `road_queue_recent` | Reviews from the last 12 months with `road_queue = true` (one label row per review, gemini over manual) |

Existing fields stay. Groups are computed in the web app from the two endpoints, as a pure, tested function.

## Page

- **Summary line** above the map: counts per group, for example "1 potential queue · 3 traffic only · 3 reviews only". Replaces "N of 10 sites slowed".
- **Map** (left): markers coloured by group. A toggle, "Potential queues" (default) and "Traffic now", switches to today's live band colours and delay labels. Legend follows the mode.
- **Station list** (right), replacing the cards and the table. One row per station: name and city; group chip; one line per signal ("Slower before than after on 8 of 8 days", "1 review: queue reaches the road"); "Queue complaints: N in the last 12 months" as the service problem; top complaint; today's live approach delay only (not the departure leg), small, plus the weather cell. Ordered by group (potential queue first, then traffic only, reviews only, no signal), within a group by traffic strength. In "Traffic now" mode, ordered worst first as today. No other sort or filter controls.
- **Selection:** clicking a row or a marker selects the station: the map pans to it and highlights its marker, the list scrolls to its row, and the row expands to show the confidence level and reason, the review counts, and an "Open station" link. Opening the station page is that explicit link (or Enter on a focused row's link); clicks no longer navigate directly. Escape or clicking the selected row again clears the selection.
- **States:** queue-risk failure falls back to "Traffic now" with a notice; review failure shows the traffic signal only and marks the review line "reviews unavailable"; loading uses skeleton rows. Narrow screens: map on top, list below.
- Unchanged: visual style and tokens, station page, Traffic vs rain page.

## Phases and acceptance

| Phase | Work | Acceptance |
|---|---|---|
| 1. Labeller p4 | Column in `sql/ddl.sql` and `data-schema.md`; `review_labels` field and validation (bool or NULL); prompt rule, schema and `build_row` in `gemini.py`; `PROMPT_VERSION = "p4"`; tests incl. the pinned prompt hash | Tests green; staging rows carry `road_queue`; `manual` path writes NULL |
| 2. API | `queue_recent`, `road_queue_recent` in `/api/review-themes` | Tests: counts per site, recent cut-off, gemini over manual, NULL counts as false |
| 3. Overview | Group function, list, map colouring and toggle, selection, states; remove `StationTable` and the cards | Vitest for the group function on the 2026-10-15 numbers above, ordering in both modes, selection state, failure states; build green |
| 4. Live | Apply the column, deploy the reviews job, run `--mode label`, deploy the dashboard | 139 gemini rows at `gemini-3.8-flash/p4`; overview shows the groups above (or explain any change from the rerun) |

## File ownership

| Files | Phase | Owner |
|---|---|---|
| `sql/ddl.sql`, `docs/plans/data-schema.md`, `reviews_job/review_labels.py`, `reviews_job/gemini.py`, `scripts/load_review_labels.py` (if it builds rows), `tests/test_reviews_label.py`, `tests/test_load_review_labels.py`, `dashboard/api/routers/reviews.py`, `tests/test_dashboard_reviews.py`, `docs/plans/review-labels.md` | 1, 2 | worker A |
| `dashboard/web/src/overview/`, `dashboard/web/src/map/` (Overview, TrafficMap, severity, Legend, CSS), related tests | 3 | worker B |
| Live steps, `docs/plans/dashboard.md`, this plan | 4 | orchestrator |
