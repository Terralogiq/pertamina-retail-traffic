# Chart research: showing SPBU traffic so operators understand it

Bead `.10.3` (2026-10-08). It feeds `.10.1` (queue risk), `.10.2` (Places analysis) and the next round of dashboard changes. Method: the `dataviz` skill (form → colour → validate → marks → hover → accessibility), web research (sources at the end), and read-only queries on `gcp-coe-sandbox.traffic` covering 67 slots (2026-10-06 17:30 → 2026-10-08 02:30 UTC, about 1.5 days).

**Audience:** Pertamina retail and network-operations managers and site managers. They aren't analysts, and they decide where to intervene (approach queues, staffing, promotions). They use desktop and phone; the UI is in English for now.

## Executive summary

1. **Lead with minutes, not ratios.** People judge absolute numbers better than relative ones (Gigerenzer; INRIX's "hours lost"). The headline unit is "N min slower than usual" (`delay_s`). `congestion_index` stays as the band driver and as a secondary "× usual time".
2. **Bands must be relative to each leg's own free-flow speed, the way Google's traffic colours are.** The fixed urban km/h fallback is wrong:
   - **Lampung:** free-flow speed on site 24.351.97's approach is 26 km/h, so it can never read "Free flow" (≥ 35 km/h).
   - **Toll:** 98% of readings on the toll (KM57A, free-flow 78 km/h) read "Free flow" even when it slows by a quarter.
3. **The current congestion bands are too sensitive for 500 m legs.** With bands at 1.2 / 1.6 / 2.2, 57% of urban readings come out Moderate or worse. Bands aligned with HCM speed shares (1.5 / 2.0 / 3.0), plus a minimum-delay gate, put 75% at Free flow and keep Heavy/Jammed for the real spikes (9%).
4. **Adopt Google-familiar colours for bands: green / orange / red / dark red.** The validated hex values are below. The red–green risk for colour-blind users is covered by the shape and text label that every band already carries.
5. **Use a typical-day profile before a heatmap.** A 24-hour linear chart is the most accurate and most preferred form for daily patterns (Waldner et al.). A 7 × 24 heatmap holds only about 2 readings per cell per week, so it waits for 4 weeks of data; until then, show weekday/weekend × hour.
6. **Show uncertainty as a band plus a count, in words.** Use a median line, a shaded middle-50% band, and "based on N days". Lay readers misread error bars (Padilla, Kay & Hullman). Fade any hour with fewer than 4 readings.
7. **Every chart gets an action headline** ("Approach is slowest 07:00–09:00, about 3 min slower than usual"), a short busy-hours list, and a table view for accessibility.

## What the data looks like now (1.5 days)

| Fact | Value | Consequence |
|---|---|---|
| Leg free-flow times | 33–68 s over ~500 m (free-flow 26–55 km/h); toll 46 s over 1 km (78 km/h) | Free-flow speed differs per leg, so no fixed km/h band fits |
| Typical delay (median per leg) | 4–27 s | Most of the time, "slower than usual" amounts to seconds |
| Tail (95th percentile of delay) | 11 s (Karawang) to 4.4 min (Bandung departure); maximum 16.7 min | The story is in the spikes: show peaks and how often they happen, not averages |
| `congestion_index` median | 1.24 overall, 1.09–1.79 per leg | Because legs are short, +20 s already gives 1.6×; ratios inflate |
| Readings per site, leg and local hour | 2–4 | Hour-of-day statistics are anecdotes until about 7 days |
| `baseline_samples` | 67 of 302 | The baseline itself is provisional until about 2026-10-13 |
| `delay_s` < 0 | Common at night (down to −2 s) | Display it as "no delay"; never show negative minutes |
| Example (Bandung approach, local time) | Median delay ~15 s from 07:00–21:00, spikes of 5–10 min at 07–08 and 17:00 | Peaks are short and sharp, so use a line with a band; bars would hide the spikes |

## Principles (with sources)

- **Position beats colour.** Accuracy ranks: position on a common scale > length > angle > area > colour saturation > hue (Cleveland & McGill 1984). Put the numbers people compare on a common axis (line or dot), and use colour for state only.
- **Linear 24-hour charts beat radial ones and are preferred** for daily patterns (Waldner et al., 92 non-experts). Heatmaps are good for spotting a two-way pattern (day × hour) at a glance, but weak for reading values.
- **Small multiples answer "compared to what?"** (Tufte). Compare sites on the same scale side by side, not as 10 overlaid lines.
- **One axis, never two** (dataviz rule). Rain stays its own strip under the traffic series, sharing the time axis, as it does now.
- **Dashboards are for monitoring at a glance:** one screen, few chart types, sparklines and bullet-like comparisons (Few).
- **Titles state the takeaway, not the contents** (Knaflic). Annotate the one point that matters; don't label every point.
- **Uncertainty for lay readers.** Intervals and error bars are commonly misread. Frequency framing and intuitive bands do better (Padilla, Kay & Hullman; HOPs research). Disclose sample size in words.
- **"Usual" framing works.** Google Popular Times draws "usual" bars with the live value highlighted, and labels them "Usually not too busy" / "Usually as busy as it gets". It is relative to the place's own busiest hour. Operators already know this pattern from Google Maps.
- **Relative congestion is standard.** TomTom expresses congestion as "% extra travel time vs free flow". FHWA uses the Travel Time Index (TTI = time ÷ free-flow time), the Planning Time Index (95th percentile ÷ free flow) and Congested Hours (speed below 90% of free flow). Our `congestion_index` is a TTI per slot.

## Metric vocabulary for users (core columns only)

| Say this | Compute | Column(s) | Notes |
|---|---|---|---|
| **"N min slower than usual"** | `max(delay_s, 0)`, shown as seconds under 90 s, else minutes to 0.5 | `delay_s` (`v_traffic`) | Primary number everywhere |
| "× usual time" (secondary) | `congestion_index` to 1 decimal, e.g. "2.3× usual time" | `congestion_index` | Only next to the minutes, never alone |
| "Usual time" / "free flow" | 7-day p10 of duration | `baseline_s` | Explain it once: "the time it takes on a quiet day" |
| **Traffic band** | Banding rule below | `congestion_index`, `delay_s`, `speed_kmh` | Shape + label + colour |
| **Busy hour** | A local hour of a typical day where ≥ 50% of readings are Moderate or worse *and* the median delay is ≥ 30 s | as above + `slot_time`, `sites.timezone` | ≥ 7 days. List consecutive busy hours as "peak windows" ("Weekdays 07:00–09:00") |
| "Worst case to plan for" | 95th-percentile delay per leg and hour (planning-time idea) | `delay_s` | "On a bad day, allow +X min" (≥ 14 days) |
| "Congested hours per day" | Count of hours per day in Heavy or Jammed | bands | FHWA congested-hours analogue, used for site ranking |

Volume-based measures (HCM peak hour factor, PKJI degree of saturation DJ = Q/C) need vehicle counts. Neither the Routes API nor RMI gives counts, so we don't use them.

## Traffic bands: definitions

**What the references use:**
- **Google Maps:** green "no traffic delays", orange "medium amount of traffic", red "traffic delays"; the darker the red, the slower. Google doesn't publish thresholds, but the scale is speed relative to the road's normal speed, not absolute km/h. The Routes API's `speedReadingIntervals` uses the same three classes: NORMAL, SLOW, TRAFFIC_JAM.
- **HCM urban street LOS** uses travel speed as a share of base free-flow speed: A > 85%, B 67–85%, C 50–67%, D 40–50%, E 30–40%, F ≤ 30%.
- **TomTom and INRIX** use extra time relative to free flow.
- **Indonesian PKJI 2023** (successor to MKJI 1997) rates service from degree of saturation, with DJ ≤ 0.85 acceptable. That needs volumes, so it isn't applicable here; it supports using relative speed rather than fixed km/h.

**Proposal: one relative scale on every road type, plus a delay gate for short legs.** A slot is above Free flow only if it is both ≥ 1.5× the usual time and at least 20 s (urban) or 30 s (toll) slower than usual. Both values are tunable after 7 days.

| Band | Rule (`congestion_index`) | Share of free-flow speed (HCM) | One sentence for users | Example: Bandung approach, free-flow 53 km/h |
|---|---|---|---|---|
| Free flow | < 1.5, or under the delay gate | ≥ 67% (LOS A–B) | "Moving close to normal: under 1.5× the usual time." | ≥ 35 km/h |
| Moderate | 1.5–2.0 | 50–67% (C) | "Slower than normal: 1.5–2× the usual time." | 27–35 km/h |
| Heavy | 2.0–3.0 | 33–50% (D–E) | "Heavy: 2–3× the usual time, about half the normal speed." | 18–27 km/h |
| Jammed | ≥ 3.0 | < 33% (F) | "Stop-and-go: more than 3× the usual time." | < 18 km/h |
| No reading | null | — | "No reading for this slot." | — |

The km/h in each sentence is per leg: free-flow speed = `routes.expected_distance_m / baseline_s`. The same Heavy band is 18–27 km/h in Bandung, 9–13 km/h on the Lampung leg (free-flow 26 km/h), and 26–39 km/h on the toll (78 km/h).

**While the baseline builds** (below 302 samples), use the same shares against a provisional free-flow speed for the road type: urban 45 km/h, toll 80 km/h. That gives urban Free ≥ 30, Moderate 22.5–30, Heavy 15–22.5, Jammed < 15 km/h, and toll Free ≥ 53, Moderate 40–53, Heavy 27–40, Jammed < 27 km/h. A road-type column for `sites`/`routes` is a small schema addition, a core column also needed for RMI. Label this state "provisional".

**Measured shares** (1,206 urban and 134 toll readings):

| | Free | Moderate | Heavy | Jammed |
|---|---|---|---|---|
| Current bands, urban | 43% | 40% | 10% | 7% |
| Proposed, urban (before the delay gate) | 75% | 16% | 4% | 5% |
| Current speed fallback, toll | 98% "free" | | | |
| Proposed, toll | 96% | 2% | 0% | 2% |

**"Traffic bands explained" (UI copy for the legend tooltip or help panel):**

> **How we colour the road.** Each road segment is compared with its own usual time: the time it takes on a quiet day, measured over the last 7 days. So a busy city street and a toll road are judged fairly.
> - **Free flow** ▲ green: close to normal, under 1.5× the usual time.
> - **Moderate** ▬ orange: slower than normal, 1.5–2× the usual time.
> - **Heavy** ▲ red: 2–3× the usual time, about half the normal speed.
> - **Jammed** ⬢ dark red: stop-and-go, more than 3× the usual time.
>
> Small slowdowns of under 20 seconds count as normal. Until 7 days of data exist, the colours use a typical speed for the road type and are marked "provisional". Times are local (WIB/WITA).

(Use the shapes the code already draws for each band; the glyphs above are placeholders.)

## Band colours: Google-familiar vs the current palette

| Option | Hex (free, moderate, heavy, jam) | Validator, light mode, all pairs | Pros | Cons |
|---|---|---|---|---|
| Current | `#1a9e8f` `#e9a400` `#e0602a` `#a51d2d` | PASS; worst CVD ΔE 12.5; amber 2.09:1 contrast WARN | Most CVD margin; teal avoids red–green | Teal isn't Google's green, so "green = OK" has to be learned; orange and red sit close |
| **Google-familiar (recommended)** | `#1e8e3e` `#f29900` `#e8452c` `#9a1a1a` | PASS adjacent and all pairs; worst CVD ΔE 8.2 (green↔red, protan); amber 2.19:1 WARN | Same mental model as the Google Maps traffic layer users see daily; order follows lightness | Thinner CVD margin, so shape + label stay mandatory (they already are) |
| Failed candidate | `#188038` `#f29900` `#e2412a` `#9e1b1b` | All-pairs CVD FAIL (ΔE 5.1) | — | Don't use |

Notes:
- **Brand red:** the logo's `#E1232B` stays in the logo. `#e8452c` is an orange-red data colour, not chrome.
- **Basemap:** with `DEMO_MAP_ID` the Google traffic layer isn't drawn, so our legs never compete with Google's own colours. The planned muted Map ID (`.9.10`) helps further.
- **Amber contrast:** amber is below 3:1 on white, so every amber leg keeps the dark casing line and the label.
- **Heatmap:** keeps its own single-hue sequential ramp. Bands are status, the heatmap is magnitude.

## Recommended chart per question

| Question | Form | Why | Not this |
|---|---|---|---|
| **When is this site usually busy?** | **Typical-day profile:** 24 h line of median delay by local hour, middle-50% band shaded, busy hours highlighted, one line per leg (≤ 2 series, direct-labelled), n disclosed | Most accurate form for daily patterns; spikes stay visible | 7 × 24 heatmap before 4 weeks; radial clock charts |
| **What are the busy hours?** | **Peak-windows list** ("Weekdays 07:00–09:00 · usually 2–4 min slower") plus a busy-hour strip (24 cells, filled = busy) | A list is the answer, not a chart; it works on a phone | Asking users to read a heatmap |
| **Is it busier than usual right now?** | **Popular-Times style:** today's bars for the past hours over a faint "usual" profile, the current slot highlighted, a sentence ("Now: 3 min slower than usual") | Familiar from Google Maps; one comparison | Raw congestion-index number |
| **Day × hour pattern** (≥ 4 weeks) | Heatmap, weekday rows × 24 h, single-hue ramp, n in the tooltip, empty = "no data" | Two-way pattern at a glance | Before the data supports it |
| **This week vs last week** (≥ 14 days) | Two lines on one axis (last week grey, this week accent) or a dumbbell per busy window | Emphasis form: one story | Two y-axes |
| **Which sites need attention?** (`.10.1`) | Ranked dot plot of approach delay in busy hours: dot = median, whisker = p25–p75, n label, small sample in hollow dots; sorted worst first; "Approach 2× slower than departure" flag | Position on a common scale; works for 10 sites | A choropleth, or a bar per site with colour as the only cue |
| **Compare site profiles** | Small multiples: 10 typical-day sparklines on one shared y-scale | Tufte's "compared to what?" | 10 overlaid lines |
| **Does rain slow traffic?** | Current rain-vs-dry dot rows with n (keep); add "+X s when raining" as the headline | Already clear | Scatter as the main view |
| **Do nearby POIs relate to traffic?** (`.10.2`) | Labelled scatter, one dot per site (n = 10): POI count vs busy-hour delay; Spearman ρ in words ("weak / none"); no fitted line; facet by POI group | Honest about n = 10 and correlation, not cause | Regression lines, bubble charts, R² headlines |
| **One number for the overview** | Stat tile: "4 of 10 sites slowed now", with the worst site and delay | Not a chart | A single-bar chart |

**Mockup: typical-day profile (desktop)**
```
Approach is slowest 07:00–09:00 and around 17:00 — usually 2–4 min slower      [Weekdays | Weekends]
 min ┤                 ▲ busy                     ▲ busy
  4  ┤        ╭╮                              ╭╮
  2  ┤ ░░░░░░╭╯╰╮░░░░░░░░░░░░░░░░░░░░░░░░░░░░╭╯╰╮░░░░    — Approach   ░ middle half of days
  0  ┼━━━━━━━╯━━╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯━━╰━━━━    — Departure
     00   03   06   09   12   15   18   21  (WIB)       Based on 6 weekdays · faded hours have < 4 readings
```

## Uncertainty and small samples

- Show the **median line, a shaded middle-50% band and "Based on N days"** under every profile. Leave error bars out of user views.
- **Fade or hatch hours with fewer than 4 readings.** Hide rankings or comparisons below 3 days per weekday group, with the copy "Not enough data yet: ready around 13 Oct".
- **Use frequency framing in tooltips:** "Slower than 2 min on 3 of 5 weekdays at 08:00".
- **Badge every baseline-dependent number** ("provisional") until 302 samples. This replaces the current "baseline building (n/302)" chip with a plainer sentence.

## Headlines and annotation

- Pattern: **[where/what] is [state] [when], [how much]**. "Approach is slowest 07:00–09:00, about 3 min slower than usual." "4 of 10 sites are slowed now; worst: Bandung departure +6 min."
- Write the headline in code from the same numbers as the chart (it feeds the `.10.4` AI summaries later).
- Annotate only the peak and the current slot. Use direct labels for the two legs, plus a legend (dataviz rule for 2 series).

## Mobile (390 px)

- **Order:** stat tile → peak-windows list → typical-day chart (full width, 200 px) → rain → Places.
- **Heatmap:** replace it with the busy-hour strip and list. Never pan a 24-column grid sideways.
- **Ranking:** a vertical list of sites with an inline dot strip; tap for detail.
- **Touch:** targets ≥ 24 px, and tooltips open on tap.

## Accessibility

- **Never colour alone:** every band has a shape and a text label.
- **A table view for every chart** (dataviz non-negotiable; the dashboard has none today). Add a "Show as table" toggle on each card.
- **Contrast:** text uses ink tokens, never series colours. Amber marks get a dark casing.
- **Motion and keyboard:** respect reduced motion (done in `.9.7`). Keyboard focus shows the same content as hover.

## Gaps in the current dashboard

| Current | Keep or change | Bead |
|---|---|---|
| Three charts (congestion ×, delay, speed) per leg | Change: one primary delay chart; speed and × usual time in the tooltip or a toggle | new: typical-day redesign |
| Day × hour heatmap on a 1.0–2.0 × scale | Change: replace with the typical-day profile + busy-hour strip until 4 weeks; then a heatmap in minutes | new: typical-day redesign |
| Bands 1.2 / 1.6 / 2.2, no delay gate | Change to 1.5 / 2.0 / 3.0 + delay gate | new: recalibrate bands |
| Fixed urban km/h fallback (applied to toll too) | Change: road-type provisional free-flow speeds | new: recalibrate bands (+ road-type column) |
| Teal / amber / orange / red bands | Change to Google-familiar hexes (validated), if the user agrees | new: band colours |
| "Baseline building (n/302)" chip | Change to a plain "Provisional until about 13 Oct" | new: recalibrate bands |
| Rain strip on a shared axis; rain-vs-dry dot rows with n | Keep; add a headline | — |
| Overview "N of 10 sites slowed" summary | Keep; switch to the new bands | — |
| Negative delays possible in tooltips | Change: clamp to "no delay" | new: metric vocabulary |
| No chart headlines | Change: action headlines | new: headlines |
| No table views | Change: table toggle per chart | new: table views |
| No busy-hours answer | Add the peak-windows list (≥ 7 days) | new: busy hours |

## Proposed beads

1. **Recalibrate traffic bands:** relative 1.5 / 2.0 / 3.0 bands, a delay gate, road-type provisional free-flow speeds (adds a road-type column), and the "Traffic bands explained" help.
2. **Google-familiar band colours:** `#1e8e3e` / `#f29900` / `#e8452c` / `#9a1a1a`, keeping shapes, labels and amber casing. Needs user sign-off.
3. **Typical-day profile:** median + middle-50% band per leg in local time, n disclosed; it replaces the three per-metric charts and the heatmap until 4 weeks.
4. **Busy hours / peak windows:** a definition in SQL (core columns), a list and a strip on the site page and the overview. ≥ 7 days.
5. **Action headlines and metric vocabulary:** "N min slower than usual" everywhere, delay clamped at 0, generated headlines per card.
6. **Table view per chart** (accessibility).
7. **Later (≥ 4 weeks):** weekday × hour heatmap in minutes, week-over-week comparison, a planning "worst case" (p95).

## Open questions for the user

1. **Bands:** adopt the HCM-aligned bands (1.5 / 2.0 / 3.0 + 20 s gate)? Pertamina may prefer stricter thresholds for queue risk.
2. **Colours:** switch to the Google-familiar colours, or keep the current teal-based palette, which has more colour-blind margin?
3. **Time windows:** should busy hours count all 24 h, or only the SPBU's operating hours? Do Indonesian public holidays count as weekend days?
4. **Language:** Indonesian copy ("lebih lambat dari biasanya", "jam sibuk") now, or later?
5. **Minimum data:** OK to hide rankings and peak windows until 7 days, and the heatmap until 4 weeks?

## Sources

- Google Maps, busy areas and Popular Times: https://support.google.com/maps/answer/11323117 · https://blog.google/products/maps/maps101-popular-times-and-live-busyness-information/
- Google Maps traffic colours: https://support.google.com/maps/answer/3092439 · https://support.google.com/maps/answer/61454
- Routes API `SpeedReadingInterval` (NORMAL / SLOW / TRAFFIC_JAM): https://developers.google.com/maps/documentation/routes/reference/rest/v2/SpeedReadingInterval
- TomTom Traffic Index methodology: https://www.tomtom.com/traffic-index/about/
- INRIX Global Traffic Scorecard ("hours lost"): https://inrix.com/blog/2023-global-traffic-scorecard/
- Waze for Cities tools: https://support.google.com/waze/partners/answer/10618047
- FHWA travel time reliability (TTI, buffer index, PTI): https://ops.fhwa.dot.gov/publications/tt_reliability/TTR_Report.htm
- FHWA Urban Congestion Report (congested hours): https://ops.fhwa.dot.gov/perf_measurement/ucr/reports/fy2021_q1.htm
- HCM urban street LOS thresholds (share of base free-flow speed): https://www.txdot.gov/manuals/des/tsp/chapter-9-segment-analysis--freeways--multi-lane-h/9-3-hcm-based--mesoscopic--analysis/9-3-4-measures-of-effectiveness--moes-/9-3-4-4-arterials--or-urban-streets-.html
- Peak hour factor (HCM): https://www.webpages.uidaho.edu/niatt_labmanual/Chapters/signaltimingdesign/professionalpractice/PeakHourVolumeDesignFlowPHF.htm
- PKJI 2023 (degree of saturation, DJ ≤ 0.85): https://journal.umg.ac.id/index.php/jtsl/article/view/9529
- Cleveland & McGill graphical perception: https://flowingdata.com/2010/03/20/graphical-perception-learn-the-fundamentals-first
- Waldner et al. 2019, radial vs linear charts for daily traffic patterns: https://www.cg.tuwien.ac.at/research/publications/2019/waldner-2019-rld/waldner-2019-rld-paper.pdf
- Padilla, Kay & Hullman 2020, uncertainty visualisation: https://moodle2.units.it/pluginfile.php/466375/mod_resource/content/0/Uncertainty_Visualization_Padilla_Kay_Hullman_2020.pdf · HOPs: https://mucollective.northwestern.edu/project/hops · Wilke, Visualizing uncertainty: https://clauswilke.com/dataviz/visualizing-uncertainty.html
- Tufte, small multiples: https://www.r-bloggers.com/2018/04/why-you-should-master-the-small-multiple-chart/
- Few, Information Dashboard Design: https://www.theinformationlab.co.uk/community/blog/information-dashboard-design-stephen
- Knaflic, Storytelling with Data (action titles): https://www.think-cell.com/en/resources/content-hub/how-to-tell-a-better-data-story-one-slide-at-a-time
- Gigerenzer, absolute vs relative framing and natural frequencies: https://www.thieme-connect.com/products/ejournals/html/10.1055/s-2005-918154

## Decision (user sign-off, 2026-10-08)

Implementation plan: `docs/plans/traffic-presentation.md` (beads `pertamina-retail-traffic-907.11` and children).

- **Bands:** 1.5 / 2.0 / 3.0 × the leg's free-flow time, with a delay gate (Heavy/Jammed only when also ≥ 20 s slower urban, ≥ 30 s toll). Provisional free-flow while the baseline builds: urban 45 km/h, toll 80 km/h.
- **Colours:** Google-familiar `#1e8e3e` / `#f29900` / `#e8452c` / `#9a1a1a`; band shape and label stay mandatory, amber keeps a dark casing.
- **Busy hours:** all 24 h; Indonesian public holidays count as weekend days.
- **Language and data rules:** English now; rankings and the busy-hours list hidden until 7 days of data, the weekday × hour heatmap until 4 weeks, each with a "needs N more days" note.
