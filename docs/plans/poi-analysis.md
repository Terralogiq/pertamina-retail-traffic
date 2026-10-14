# Places analysis: does proximity to POIs relate to traffic?

Bead `.10.2`. Analysis run 2026-10-14 on live data. Sources: `docs/plans/data-schema.md` (Places and traffic tables), `docs/plans/traffic-presentation.md` (delay, bands, busy hours), `dashboard/api/busy.py`. Places is a core source (same API in production), so nothing here carries a demo-only badge.

## Caveat first

There are 10 sites and 8 days of traffic. Everything below is descriptive. It cannot show that a POI causes traffic, and with this sample it cannot rule a relationship out either. With n = 10, a Spearman correlation needs |ρ| of about 0.65 to reach p < 0.05 on a single test. Smaller real effects are invisible.

## Result in short

- **No POI group has a relationship with traffic that survives correction for the number of comparisons.** The strongest, shopping malls within 500 m to 1 km vs mean delay, has ρ = +0.66 (exact p = 0.045, bootstrap 95% interval −0.04 to +0.93). Across all 47 POI measures searched, the chance that the best one looks this good under pure noise is 56%.
- Of 141 tests (47 POI measures × 3 traffic metrics), 2 reach p < 0.05 and both are the same signal (malls, mean delay). Chance alone predicts about 7. The median |ρ| is 0.19.
- The overall "urban density" of a site's surroundings (average rank across 13 non-fuel POI types) is unrelated to traffic: ρ = +0.08 to +0.38 across the three radii and metrics, all p > 0.27, intervals spanning −0.8 to +0.9.
- Competition is weak and positive but not distinguishable from zero: other fuel stations within 500 m, ρ = +0.37 (p = 0.29); within 1 km, +0.20; within 3 km, +0.12.
- The main confounder is **which city and road the site is on**, not POIs. Delay differs by 19× between sites (Bandung 135 s/km, Surabaya 10 s/km, KM57A 7 s/km), and the POI counts do not track it.

## Data and definitions

Traffic window: slots 2026-10-06 17:30 UTC to 2026-10-14 08:00 UTC, SPBU side, 366 readings per leg (7.6 days). `baseline_samples` is 336 on every leg, so `v_traffic` is out of its provisional state. Baseline = 10th percentile over the trailing 7 days, as in `v_leg_baseline`. No leg is flagged `demo_rerouted`. The first ~30 slots precede the baseline window and are compared with a baseline built from later days; the delay is clamped at 0 as in the dashboard.

| Item | Definition |
|---|---|
| Mean delay | Mean of `max(delay_s, 0)` over all readings, divided by the leg length in km (s/km). Per kilometre because KM57A legs are 1 km and the rest are 500 m; the ranks differ only for KM57A and Surabaya. |
| Peak congestion | 95th percentile of `congestion_index` (× usual time): the worst 1 in 20 slots. Length-free. |
| Busy-hour share | Busy local hours ÷ 24, weekdays only (6 local dates, 10 to 12 readings per hour and leg). A busy hour is the `busy.py` rule: at least half the readings Moderate or worse (≥ 1.5× and ≥ 20 s urban / 30 s toll) and median delay ≥ 30 s. Weekends are left out: 2 days is too thin per hour. |
| Legs | Computed per leg, then averaged for the main test. Approach and departure agree across sites on delay (ρ = 0.87) and peak (0.90), less on busy share (0.63): at Bandung and Jakarta Barat the departure leg is much worse, at Denpasar and Makassar the approach leg. Averaging is justified for the first two metrics. For busy share it blurs a real asymmetry, so the screen offers a leg switch. Every headline feature has the same sign on both legs. |
| Metric overlap | The three traffic metrics are one measurement: ρ between them is 0.98. Agreement across them is not three independent confirmations. |
| POI counts | `places_aggregate` `INSIGHT_COUNT` (operational places), latest run `places-profiler-lzsxb` (2026-10-11 19:00 UTC). The three runs agree within about 1%, so the latest run stands in for all. |
| Competitors | Other fuel stations = aggregate `gas_station` count − 1 (the site itself is counted), at 500 m, 1 km and 3 km. Uncapped. `places_nearby` is capped at 20 results including the site, so its 3 km count is capped at 19 for 8 of 10 sites and is not used for correlations. From `places_nearby` at 1 km (never capped, max 9): rivals (non-Pertamina brand) and other Pertamina stations, used as table columns and as one extra test each. |
| Road class | `toll` when `road_type` contains "toll" (KM57A only), else `urban`. The two Bandar Lampung sites have `road_type = client-provided` and are treated as urban. |

## Per-site table

Traffic (combined legs):

| Site | City | Mean delay s/km | Peak × usual | Busy hours (approach / departure) | Busy share |
|---|---|---|---|---|---|
| 24.351.34 | Bandar Lampung | 26 | 1.7 | 0 / 0 | 0.00 |
| 24.351.97 | Bandar Lampung | 32 | 1.7 | 0 / 2 | 0.04 |
| 34.117.12 | Jakarta Barat | 94 | 5.8 | 4 / 11 | 0.31 |
| 34.121.03 | Jakarta Selatan | 27 | 1.7 | 2 / 0 | 0.04 |
| 34.401.16 | Bandung | 135 | 9.2 | 4 / 14 | 0.38 |
| 54.601.80 | Surabaya | 10 | 1.3 | 0 / 0 | 0.00 |
| 54.801.17 | Denpasar | 79 | 7.3 | 12 / 3 | 0.31 |
| 61.761.03 | Balikpapan | 38 | 1.9 | 3 / 0 | 0.06 |
| 74.902.22 | Makassar | 42 | 2.2 | 9 / 1 | 0.21 |
| KM57A | Karawang (toll) | 7 | 1.4 | 0 / 0 | 0.00 |

POIs (selected columns; all 15 types × 3 radii are in `places_aggregate`):

| Site | Other stations 500 m | 1 km | 3 km | Rivals 1 km | Restaurants 1 km | Malls 1 km | Lodging 3 km | Schools 1 km | Hospitals 500 m |
|---|---|---|---|---|---|---|---|---|---|
| 24.351.34 | 0 | 2 | 30 | 1 | 466 | 52 | 1516 | 49 | 0 |
| 24.351.97 | 0 | 1 | 12 | 1 | 85 | 17 | 430 | 14 | 0 |
| 34.117.12 | 3 | 7 | 68 | 7 | 661 | 64 | 1973 | 64 | 1 |
| 34.121.03 | 3 | 7 | 52 | 6 | 578 | 22 | 2665 | 48 | 1 |
| 34.401.16 | 5 | 9 | 58 | 6 | 1158 | 63 | 5710 | 79 | 11 |
| 54.601.80 | 2 | 4 | 39 | 4 | 711 | 18 | 2203 | 54 | 2 |
| 54.801.17 | 1 | 3 | 22 | 2 | 339 | 24 | 2425 | 22 | 1 |
| 61.761.03 | 0 | 2 | 20 | 2 | 478 | 38 | 1321 | 44 | 1 |
| 74.902.22 | 1 | 1 | 14 | 1 | 447 | 29 | 2765 | 26 | 4 |
| KM57A | 1 | 6 | 55 | 5 | 204 | 18 | 359 | 20 | 0 |

## Rank correlations

**Method.** Spearman ρ between a POI count and a traffic metric across the 10 sites (ties get average ranks). Uncertainty:

- **Exact permutation p-value, two-sided.** All 10! = 3,628,800 pairings of sites with traffic values; p is the share with |ρ| at least the observed. This is the number to trust at n = 10.
- **Bootstrap 95% interval.** 10,000 resamples of the 10 sites, percentile method. At n = 10 it is rough and too narrow if anything; read it as "the data are compatible with anything in here".
- **Leave-one-out range.** ρ with each site dropped in turn, to show whether one site carries the result.
- **Family-wise p.** For each traffic metric, the permutation distribution of the *largest* |ρ| across all 47 POI measures. It answers: if there is no relationship, how often would the best of 47 look this good? Benjamini-Hochberg gives the same story (smallest q = 0.97).

Six POI groups are shown below (the groups the screen will use, see "Which POI groups make the cut"), against mean delay. The last two columns give ρ against the other two metrics.

| Group | Radius | ρ | 95% bootstrap | Exact p | Family-wise p | ρ peak | ρ busy |
|---|---|---|---|---|---|---|---|
| Other fuel stations | 500 m | +0.37 | −0.39, +0.92 | 0.29 | 1.00 | +0.31 | +0.44 |
| | 1 km | +0.20 | −0.67, +0.81 | 0.57 | 1.00 | +0.17 | +0.27 |
| | 3 km | +0.12 | −0.81, +0.68 | 0.76 | 1.00 | +0.07 | +0.15 |
| Restaurants | 500 m | +0.13 | −0.81, +0.77 | 0.73 | 1.00 | +0.03 | +0.09 |
| | 1 km | +0.31 | −0.58, +0.89 | 0.39 | 1.00 | +0.16 | +0.28 |
| | 3 km | +0.42 | −0.41, +0.92 | 0.23 | 0.99 | +0.31 | +0.40 |
| Shopping malls | 500 m | +0.65 | −0.13, +1.00 | 0.05 | 0.57 | +0.61 | +0.54 |
| | 1 km | +0.66 | −0.04, +0.93 | 0.04 | 0.56 | +0.60 | +0.59 |
| | 3 km | −0.02 | −0.74, +0.66 | 0.97 | 1.00 | −0.05 | −0.06 |
| Lodging | 500 m | +0.20 | −0.61, +0.85 | 0.58 | 1.00 | +0.12 | +0.19 |
| | 1 km | +0.35 | −0.42, +0.83 | 0.32 | 1.00 | +0.30 | +0.39 |
| | 3 km | +0.56 | −0.15, +0.95 | 0.10 | 0.80 | +0.53 | +0.59 |
| Schools | 500 m | +0.25 | −0.61, +0.88 | 0.48 | 1.00 | +0.11 | +0.21 |
| | 1 km | +0.35 | −0.64, +0.89 | 0.33 | 1.00 | +0.20 | +0.28 |
| | 3 km | +0.26 | −0.71, +0.87 | 0.47 | 1.00 | +0.13 | +0.19 |
| Hospitals | 500 m | +0.54 | −0.21, +0.94 | 0.11 | 0.84 | +0.47 | +0.58 |
| | 1 km | +0.33 | −0.36, +0.81 | 0.35 | 1.00 | +0.25 | +0.33 |
| | 3 km | +0.33 | −0.40, +0.90 | 0.35 | 1.00 | +0.27 | +0.31 |

**Strongest.** Shopping malls at 500 m and 1 km (ρ +0.65 / +0.66). Dropping any one site keeps ρ between +0.54 and +0.81, and both legs agree (leg-level ρ +0.38 to +0.74 across the three metrics), so it is not a one-site artefact. But it vanishes at 3 km (ρ = −0.02), the interval touches zero, and the family-wise p is 0.56. It is also driven by Bandung and Jakarta Barat (both 63 to 64 malls, both slow) against Surabaya, Jakarta Selatan and KM57A (18 to 22 malls, fast), while Bandar Lampung site 1 has 52 malls and little delay. Google's `shopping_mall` type in Indonesia covers small retail blocks, so a count is not footfall. Next: lodging within 3 km (+0.56) and hospitals within 500 m (+0.54), both p > 0.10.

**Weakest.** Car wash at 1 km and 3 km (ρ −0.02 to +0.02 on all three metrics; +0.21 to +0.27 at 500 m), ATMs and convenience stores at 1 km (ρ +0.01 to +0.13), and the density index at 500 m and 1 km (ρ +0.08 to +0.21, p 0.56 to 0.84).

**Competitors.** Positive but small and shrinking with radius (see table). Rivals within 1 km: ρ +0.23 (p 0.52); other Pertamina stations within 1 km: +0.06 (p 0.87). Nothing suggests competition raises or lowers traffic in front of a station. Sites with no neighbour within 500 m (Bandar Lampung × 2, Balikpapan) are all in the low-to-mid delay range.

**Multiple comparisons.** The full search is 14 non-fuel types × 3 radii + 3 fuel-station radii + 2 brand counts at 1 km = 47 POI measures, × 3 traffic metrics = 141 tests. At 5% we expect about 7 false positives and found 2, which are one signal. The 3 metrics are one measurement (ρ ≈ 0.98) and the POI types are collinear (median pairwise ρ across types at 1 km is 0.60; restaurants vs cafés 0.92, restaurants vs ATMs 0.84), so the effective number of independent tests is lower than 141, but not by enough to change the conclusion. The screen therefore shows a short pre-chosen list, labels the number of comparisons, and does not use words like "significant" unless the family-wise p is below 0.05.

## Confounders

| Confounder | Why it matters here |
|---|---|
| Road type (urban vs toll) | KM57A is the only toll site: 1 km legs, 70 km/h mean speed, no busy hour, few POIs reachable from the toll road (its 204 restaurants within 1 km are mostly outside the toll fence). Dropping it leaves the picture unchanged (malls vs delay +0.60, density index −0.08 to +0.22), so it is not creating or hiding the result, but it is the extreme point in many plots. |
| City and road | Nine cities for ten sites (two in Bandar Lampung, both low delay), so the sites are not independent draws. Delay follows the road (Bandung's Pasteur, Jakarta's Daan Mogot, Denpasar's bypass) more than the surroundings. |
| Relative delay | Delay is measured against each leg's own 10th-percentile time. A leg that is slow all day has a slow baseline and looks "free" (Bandar Lampung site 2 averages 24.6 km/h with a delay of 32 s/km). Mean `speed_kmh` per site correlates with mean delay at ρ = −0.56 only, so the two are not the same thing. A speed-based metric is a better test of "absolute slowness" and should be added if the screen survives. |
| Places coverage and city size | Counts reflect how well Google has mapped each place as much as how many exist. Bigger metros (Jakarta, Bandung, Surabaya) have both more POIs and more complete Google data. |
| Circles, not catchments | A 500 m circle takes in places across a river, a median or a toll fence. Drive-time catchments would be better. |
| Short window | 8 days, one weekend, no holiday, no rain filter. Busy-hour share has ties at 0 for four sites. |

## Which POI groups make the cut

Rule: a group needs a plausible mechanism for traffic or station use, enough variation across the 10 sites (not mostly zeros), and must not duplicate another group. The list was set on those grounds and not by ranking correlations.

| Group | In? | Reason |
|---|---|---|
| Other fuel stations (500 m, 1 km, 3 km) | Yes | The retail question: do nearby stations share the road. Uncapped from aggregate; brand split at 1 km shown in the table. |
| Restaurants | Yes | Stops and parking. Stands in for cafés (ρ 0.92), ATMs (0.84), banks and convenience stores, which are dropped as near-duplicates. |
| Shopping malls | Yes | Destination traffic. Supermarkets are dropped (small counts, opposite sign, no extra signal). |
| Lodging | Yes | Tourism and intercity stops (Denpasar, Bandung, KM57A). |
| Schools | Yes | Peak-hour trips. Universities are dropped (0 at 2 of 10 sites at 1 km, ρ 0.57 with schools). |
| Hospitals | Yes | Continuous trips and emergency access. Low counts at 500 m, so shown with the counts. |
| Banks, ATMs, cafés, convenience stores, supermarkets, universities | Table only | Collinear with the above. Available under "All types" with the comparison count. |
| Car repair, car wash | No | Not trip generators; the only link to an SPBU is competition for the same drivers. Car wash is near-zero everywhere. |
| EV charging | No | 0 at 500 m for four sites and at most 3 elsewhere: mostly ties. |

Six groups × 3 radii = 18 tests per traffic metric.

## Screen proposal

New route `/places`, nav label **Places vs traffic**, next to "Traffic vs rain". It is separate from the Places panel on the site page, which stays the per-site profile. English copy; no demo-only badge.

**Layout (top to bottom).**

1. **Caveat banner, always visible.** "10 sites, 8 days. These are descriptive patterns, not causes. With this few sites only large effects can be detected. 18 comparisons are shown; about 1 would look 'significant' by chance." Footer line carries Places run date and traffic window.
2. **Controls row:** traffic metric (Mean delay / Peak congestion / Busy hours), leg (Both / Approach / Departure), radius (500 m / 1 km / 3 km), "Exclude toll site (KM57A)" checkbox.
3. **Summary plot: one row per POI group** showing ρ as a dot with its bootstrap interval, one dot per radius (radius encoded by marker shape plus label, not colour alone), a vertical zero line, and the exact p as text at the end of the row. Every interval crosses zero today, which is the honest picture. Rows are in fixed order, not sorted by ρ, so the plot does not advertise the best of the list.
4. **Scatter for the selected group, radius and metric** (selected by clicking a summary row or by the controls): x = POI count (log scale), y = traffic metric. Each point is labelled with the city short name; KM57A is a hollow diamond marked "toll". A "show ranks" switch draws rank vs rank, which is what Spearman measures. Below it: ρ, interval, exact p, leave-one-out range, n, and a plain sentence ("No clear relationship: ρ +0.31, compatible with −0.58 to +0.89").
5. **Small multiples:** a 6 × 3 grid of mini-scatters (groups × radii), same y metric, shared y axis, ρ in each corner, current selection outlined. This is the "see every pairing at once" view and the overfit guard: the eye sees that nothing lines up across radii (malls: +0.65, +0.66, −0.02).
6. **Per-site profile table:** the two tables above merged: city, road class, traffic metrics, POI counts at the selected radius, in-cell bars. Sortable. Clicking a site opens its detail page.

**Interactions.**

- Hovering a site anywhere (scatter, grid, table) highlights it in all of them.
- Switching metric, leg, radius or the toll checkbox recomputes every ρ, interval and p on the page. The checkbox makes n = 9 visible in the stats line.
- Hovering a scatter point shows that site's leave-one-out ρ.
- "Show as table" on the scatter and the summary plot, as in `traffic-presentation.md` `.11.6`.
- "All types" toggle expands the summary plot to all 15 types and adds the line "N comparisons, about N/20 expected by chance".
- Hidden until ready: the same gate as busy hours, 7 distinct local dates ("needs N more days"). Busy-hour share is not offered until then.

**Labelling and wording.**

- Colour: neutral; no red/green, no stars. Strength words by |ρ| only describe size ("weak", "moderate", "strong"); "significant" appears only when the family-wise p < 0.05, which is no row today.
- Always print n, the interval and the exact p next to a ρ. Never ρ alone.
- Counts are "places Google lists within N m", not footfall. Tooltip says so.
- Confounder note under the scatter: "Cities and roads differ more than surroundings do. KM57A is a toll rest area."

**Data and API.** `GET /api/places/analysis?metric&leg&radius&exclude_toll` returns the per-site table and, per (group, radius), `rho`, `ci_low`, `ci_high`, `p`, `loo_min`, `loo_max`, `n`. It joins `places_aggregate` (latest run) and `places_nearby` with `v_traffic`, reusing `busy.py` for the busy rule, over the same traffic window the series endpoints use (at most 28 days). The doc's p-values are exact over 10! pairings; the endpoint can use a seeded 20,000-permutation estimate in pure Python (error about ±0.003) to avoid a numpy dependency, with 2,000 bootstrap resamples, cached per (traffic slot, Places run). Both are cheap for 18 tests.

**Acceptance.**

- The caveat banner renders on every state of the page, and the stats line shows n, interval and p for any selection.
- The toll checkbox changes n to 9 and recomputes the numbers.
- The page is hidden with a "needs N more days" note when fewer than 7 local dates exist.
- A test pins the Spearman code against the values in this doc (mall 1 km vs mean delay: ρ +0.657, exact p 0.045).
- No row uses the word "significant" while the family-wise p is ≥ 0.05.

## Not done (for beads)

- Re-run at four weeks of data with a weekday/weekend split (due about 2026-11-03).
- A speed-based metric for absolute slowness, to address relative-delay bias.
- Drive-time catchments instead of circles; road attributes (lanes, signals, flyovers) as covariates.
- More sites. n = 10 is the limit; a production run on the real station network is the real answer to this question.

## Reproduce

Run with `--project_id=gcp-coe-sandbox`. Traffic window is fixed so results do not drift; `v_traffic` itself uses a trailing-7-day baseline, so the baseline will move as time passes.

```sql
-- Traffic readings (SPBU side), local hour and date from sites.timezone
SELECT s.site_id, r.leg,
  IF(LOWER(s.road_type) LIKE '%toll%', 'toll', 'urban') AS road_class,
  EXTRACT(HOUR FROM t.slot_time AT TIME ZONE s.timezone) AS local_hour,
  DATE(t.slot_time, s.timezone) AS local_date,
  EXTRACT(DAYOFWEEK FROM DATE(t.slot_time, s.timezone)) AS dow,   -- 1 = Sunday; weekdays are 2..6
  r.expected_distance_m, t.duration_in_seconds, t.baseline_samples,
  t.congestion_index, GREATEST(t.delay_s, 0) AS delay_s, t.speed_kmh
FROM traffic.v_traffic t
JOIN traffic.routes r USING (selected_route_id)
JOIN traffic.sites s ON s.site_id = r.site_id
WHERE r.side = 'spbu_side'
  AND t.slot_time BETWEEN TIMESTAMP '2026-10-06 17:30:00' AND TIMESTAMP '2026-10-14 08:00:00'
  AND t.duration_in_seconds IS NOT NULL;
```

```sql
-- POI counts, latest Places run (see data-schema.md: take run_id of the greatest fetched_at)
WITH latest AS (
  SELECT run_id FROM traffic.places_aggregate
  WHERE DATE(fetched_at) >= '2026-10-01'
  QUALIFY ROW_NUMBER() OVER (ORDER BY fetched_at DESC) = 1
)
SELECT site_id, place_type, radius_m,
  IF(place_type = 'gas_station', count - 1, count) AS count   -- minus the site itself
FROM traffic.places_aggregate
WHERE DATE(fetched_at) >= '2026-10-01' AND run_id = (SELECT run_id FROM latest);
```

```sql
-- Competitor brands at 1 km from places_nearby (never capped at 1 km); the site itself excluded
WITH latest AS (
  SELECT run_id FROM traffic.places_nearby
  WHERE DATE(fetched_at) >= '2026-10-01'
  QUALIFY ROW_NUMBER() OVER (ORDER BY fetched_at DESC) = 1
), n AS (
  SELECT * FROM traffic.places_nearby
  WHERE DATE(fetched_at) >= '2026-10-01' AND run_id = (SELECT run_id FROM latest) AND radius_m = 1000
  QUALIFY fetched_at = MAX(fetched_at) OVER (PARTITION BY site_id, radius_m)
)
SELECT n.site_id, COUNTIF(n.brand = 'Pertamina') AS pertamina_other,
       COUNTIF(n.brand != 'Pertamina') AS rivals
FROM n JOIN traffic.sites s ON s.site_id = n.site_id
WHERE n.place_id != s.place_id
GROUP BY 1;
```

Per leg: mean delay = `AVG(delay_s) / (expected_distance_m / 1000)`; peak = 95th percentile of `congestion_index`; busy hours per `busy.py` (`counts_are_busy`) on the weekday readings, grouped by `local_hour`. Combined = mean of the two legs. Statistics (numpy and scipy):

```python
import itertools, numpy as np
from scipy.stats import rankdata
perms = np.array(list(itertools.permutations(range(10))), dtype=np.int8)   # 10! rows

def spearman(x, y):
    return np.corrcoef(rankdata(x), rankdata(y))[0, 1]

def exact_p(x, y):                       # two-sided, ties get average ranks
    rx, ry = rankdata(x) - rankdata(x).mean(), rankdata(y) - rankdata(y).mean()
    null = (rx[perms] * ry).sum(axis=1) / np.sqrt((rx**2).sum() * (ry**2).sum())
    return (np.abs(null) >= abs(spearman(x, y)) - 1e-9).mean()

def bootstrap_ci(x, y, b=10_000, seed=1):
    rng, x, y, v = np.random.default_rng(seed), np.array(x), np.array(y), []
    for _ in range(b):
        i = rng.integers(0, 10, 10)
        if len(set(x[i])) > 1 and len(set(y[i])) > 1:
            v.append(spearman(x[i], y[i]))
    return np.percentile(v, [2.5, 97.5])
```

Family-wise p: for each traffic metric, take the maximum of `|null|` over all 47 POI measures for every one of the 10! pairings, and report the share of pairings whose maximum is at least the observed |ρ|.
