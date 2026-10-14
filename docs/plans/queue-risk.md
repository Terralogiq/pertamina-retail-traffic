# Queue risk on the approach: proxy, ranking, validation, screen

Bead `pertamina-retail-traffic-907.10.1`. Analysis date 2026-10-14. Read-only queries on `gcp-coe-sandbox.traffic`. Band rule, delay gate, busy-hour rule and weekend rule are the signed-off ones in [traffic-presentation.md](traffic-presentation.md); columns are in [data-schema.md](data-schema.md); screens are in [dashboard.md](dashboard.md). Review themes come from [complaints-analysis.md](complaints-analysis.md).

## In brief

We do not measure forecourt queues. We measure main-road travel time on two legs per site: Approach (Entry → Front) and Departure (Front → Exit). The proxy is an **approach-led slowdown**: a half-hour slot in which the approach is Moderate or worse under the band rule while the departure, fetched in the same call, is not. A station queue that spills into the kerb lane slows the road before the turn-in and leaves the road after it free. Ordinary corridor congestion slows both legs, or the departure first.

On 8 days of data, Pemogan (Denpasar) has the strongest and most repeatable signal: weekday mornings 07:00–12:00 WITA, the approach is usually 1–3 minutes slower than usual while the departure flows. That puts it first, with medium confidence. MT Haryono (Balikpapan), Makassar and Lingkar Selatan (Jakarta Selatan) follow, each with low confidence: the signal recurs daily, but the delays are about half a minute. Gayungan (Surabaya) shows almost no slowdown on either leg. At Bandung and Daan Mogot the road after the station is jammed more often than the road before it, so this proxy cannot see a station queue there. That is not evidence that these two sites have no queue.

No site is rated high confidence. Nothing here has been checked against a queue on the ground, and a traffic signal, U-turn gap or bus stop just before the Front point would produce the same pattern.

## What the data is

| Fact | Value |
|---|---|
| Window | Slots 2026-10-06 17:30 UTC to 2026-10-14 08:00 UTC: 366 slots per leg, no gaps, no null delay |
| Local dates | 8 per site: 7 full (7–13 Oct) plus a partial 14 Oct. Weekend days: Sat 10 and Sun 11 Oct. No national holiday falls in the window |
| Readings per hour | Weekday 10–12, weekend 4 (the typical-day fade threshold) |
| Baseline | `v_leg_baseline` is full on all 20 legs (336 samples, threshold 302). Usual time is the trailing-7-day p10 of `duration_in_seconds`, recomputed at query time, so a rerun shifts the numbers slightly |
| Legs | About 500 m urban and about 1 km at KM57A (toll; delay gate 30 s, all other sites 20 s) |
| Source | Routes API `computeRoutes`, TRAFFIC_AWARE, one call per site per slot, standing in for RMI |

## Proxy definition

All inputs are core columns: `v_traffic.delay_s` and `congestion_index`, `routes.leg`, `sites.timezone`, `sites.road_type`. The same query runs unchanged on RMI `historical_travel_time` once the legs are registered as SelectedRoutes.

| Term | Definition | New or existing |
|---|---|---|
| Slow reading | Moderate or worse: `congestion_index >= 1.5` and `delay_s >= 20 s` (urban) or `30 s` (toll) | Existing band rule |
| Busy hour | A local hour where at least half the readings are slow and the median `delay_s` is at least 30 s | Existing, applied per leg |
| **Approach-led slowdown (ALS)** | A slot where the approach reading is slow and the departure reading in the same slot is not | **New** |
| ALS share | ALS slots ÷ all slots, overall and by weekday/weekend and local hour | New, from ALS |
| Recurrence | Full local dates (≥ 40 slots) with at least 4 ALS slots (2 hours) | New, from ALS |
| Severity | Median approach `delay_s` in ALS slots | Existing column, ALS filter |
| Persistence | Longest run of consecutive ALS slots, in hours | New, from ALS |

Why ALS is needed: approach delay on its own ranks corridor congestion. Bandung has the second-highest approach p90 delay (145 s), but only because its departure is worse (p90 274 s); the queue at the front of its approach is the tail of a downstream jam. ALS reuses the signed-off band rule on both legs and adds no threshold of its own. The only new parameter is the 2-hour recurrence bar.

**Night check.** At nine sites, the median approach-minus-departure delay is within about 3 s of zero between 00:00 and 05:00 local, then opens at the busy hours (Pemogan +52 to +166 s at 07:00–10:00). The exception is Tirtayasa, where the gap is +11 to +18 s at night and negative by day. At the other nine, the asymmetry follows demand, so it is not a fixed difference between the two legs. That rules out a constant leg artefact, but not a junction that only saturates at peak hours.

**Ranking rule.** Sort by recurrence, then by severity. Sites where departure-only slowdowns are as common as approach-only ones, and both-legs-slow dominates, are marked **masked** and listed last. The proxy does not rank them.

## Results

Percentages are shares of the 366 slots per site.

| Site | Approach slow | Both slow | Departure only | ALS (weekday / weekend) | Days ≥ 2 h ALS (of 7) | Median approach delay in ALS | ALS slots ≥ 1 min | Longest ALS run |
|---|---|---|---|---|---|---|---|---|
| 54.801.17 Pemogan, Denpasar | 40.4% | 10.7% | 2.2% | 29.8% (36.3 / 11.5) | 7 | 75 s | 63 | 11.0 h |
| 61.761.03 MT Haryono, Balikpapan | 36.9% | 11.2% | 2.2% | 25.7% (28.1 / 18.8) | 7 | 30 s | 2 | 5.5 h |
| 74.902.22 Makassar | 59.0% | 32.8% | 0.3% | 26.2% (27.0 / 24.0) | 7 | 28 s | 0 | 3.5 h |
| 34.121.03 Lingkar Selatan, Jakarta Selatan | 22.7% | 3.0% | 0.0% | 19.7% (25.2 / 4.2) | 6 | 25 s | 4 | 4.5 h |
| 24.351.97 Tirtayasa, Bandar Lampung | 9.6% | 3.6% | 10.7% | 6.0% (7.8 / 1.0) | 3 | 36 s | 2 | 2.0 h |
| 24.351.34 Antasari, Bandar Lampung | 14.2% | 8.2% | 16.1% | 6.0% (7.4 / 2.1) | 3 | 26 s | 1 | 1.0 h |
| KM57A rest area, Karawang (toll) | 3.3% | 0.0% | 0.3% | 3.3% (4.4 / 0.0) | 2 | 77 s | 7 | 2.0 h |
| 54.601.80 Gayungan, Surabaya | 0.3% | 0.0% | 0.8% | 0.3% | 0 | 42 s (1 slot) | 0 | 0.5 h |
| 34.117.12 Daan Mogot, Jakarta Barat | 24.3% | 22.4% | 16.9% | 1.9% | 0 | 30 s | 2 | 1.0 h |
| 34.401.16 Bandung | 33.6% | 33.6% | 27.3% | 0.0% | 0 | — | 0 | — |

Busy windows that are busy on the approach only, under the existing busy-hour rule (local time; weekend hours have n = 4):

| Site | Approach-only busy hours | Approach median delay | Departure median delay |
|---|---|---|---|
| Pemogan | Weekdays 07:00–12:00, 15:00–17:00 and 19:00–21:00 WITA. 17:00–19:00 is busy on both legs. Weekends: none | 31–179 s (08:00: 179 s) | 10–29 s |
| MT Haryono | Weekdays 07:00, 19:00, 22:00 WITA. Weekends 13:00 and 17:00–23:00 | 30–34 s weekdays, 31–68 s weekends | 11–27 s |
| Makassar | Weekdays 13:00 and 15:00–23:00 WITA (17:00 busy on both legs). Weekends 12:00 and 17:00–23:00 (18:00 busy on both) | 30–48 s | 17–27 s |
| Lingkar Selatan | Weekdays 17:00–19:00 WIB | 32–35 s | 16 s |

At Makassar the evening approach is slow, but the departure is often just over the gate as well, so most evening slots are "both slow", not ALS. Its ALS slots cluster at 07:00 and 09:00–13:00 (42–75% of weekday readings in those hours).

## Ranking with confidence

Confidence means how far we trust that the signal reflects a station queue, not how strong the signal is.

| Rank | Site | Signal | Confidence |
|---|---|---|---|
| 1 | Pemogan, Denpasar | Strong | Medium |
| 2 | MT Haryono, Balikpapan | Moderate, mild delays | Low |
| 3 | Makassar | Moderate, mild delays, corridor-wide | Low |
| 4 | Lingkar Selatan, Jakarta Selatan | Moderate, weekday evenings only | Low |
| 5 | Tirtayasa, Bandar Lampung | Weak | Very low |
| 6 | Antasari, Bandar Lampung | Weak | Very low |
| 7 | KM57A rest area | Weak, three nights | Very low |
| 8 | Gayungan, Surabaya | None on the road | Medium (that the road is not slowed) |
| — | Daan Mogot, Jakarta Barat | Masked | None |
| — | Bandung | Masked | None |

Reasons:

1. **Pemogan, medium.** ALS appears on all 7 full days and grows from the first half of the week (24% of slots, 7–10 Oct) to the second (36%, 11–14 Oct). Delays are well above the gate: the median ALS slot is 75 s, and 63 ALS slots are a minute or more. The departure meanwhile stays near 10 s. On Tue 13 Oct, from 08:00 to 15:00 WITA, the approach ran 3.5–8 min slower for seven hours while the departure stayed free. The Routes distance stayed at 500–509 m (the `demo_distance_m` sanity check), so this was not a detour. Without that day, ALS is still 26% of slots. It is not high confidence because the pattern is weekday-heavy (weekend ALS is 11.5%) and commute-shaped, which a junction or merge near the Front point on Jl. By Pass Ngurah Rai would produce just as well. Only one reviewer (two days of Solar queues on the bypass) corroborates it.
2. **MT Haryono, low.** The signal recurs on 7 of 7 days in both halves of the week (27% and 24%) and is specific: 70% of approach slowdowns have a free departure. Its late-evening timing (ALS in all 10 weekday readings at 22:00 WITA, and weekends 17:00–23:00) fits fuel demand better than commuting. The delays, though, are about 30 s, which a pedestrian crossing or an angkot stop could also cause. The only corroboration is an old review of a queue blocking the road, plus one review of a Pertalite lane closing early.
3. **Makassar, low.** This is the most stable site (26% in both halves; weekday 27%, weekend 24%), but the delays are the mildest of the four: no ALS slot reaches a minute. The approach is slow in 59% of slots and both legs in 33%, so most of the signal is a corridor that runs about 1.6× its night-time p10 all afternoon. Reviews mention understaffing queues twice.
4. **Lingkar Selatan, low.** ALS covers 70–100% of weekday readings from 16:00 to 20:00 WIB and almost nothing at weekends (4%). That is the shape of the evening commute on TB Simatupang, not of fuel demand. Delays are about 25–35 s. Reviews mention mild "hectic evenings" only.
5. **Tirtayasa, very low.** It has 22 ALS slots, scattered across hours; in the daytime the departure is slower than the approach. Its approach usual time (61 s for 500 m, about 30 km/h) is the slowest of the ten, which points to a fixed feature on the leg. The roadside Solar queue in the reviews would be a morning event, and the data does not show one.
6. **Antasari, very low.** It has 22 ALS slots of about 26 s, clustered at 07:00 on weekdays (67% of those readings). Departure-only slowdowns are more common (16%).
7. **KM57A, very low.** 11 of its 12 ALS slots fall on 7–9 Oct, ten of them between 21:00 and 01:00 WIB, at up to 2.5 min on the 1 km toll approach. Since then there has been one 33 s slot. This may be traffic queuing into the rest area, but three nights is too little to say.
8. **Gayungan, medium that the road is not slowed.** Only one approach slot in 366 is slow, and the p90 approach delay is 8.5 s. This contradicts the three reviews of a Pertalite motorcycle queue reaching Jl. Ahmad Yani. Three explanations fit: the spill is shorter than the 30-minute sampling interval, it sits on the shoulder without slowing through traffic in Google's speeds, or it happens on days outside this window. This site is a good validation target because the two sources disagree.
- **Daan Mogot and Bandung, masked.** Both legs are slow together in 22–34% of slots, and departure-only slowdowns (17% and 27%) outnumber approach-only ones (2% and 0%). The departure is a busy hour for 11 (Daan Mogot) and 14 (Bandung) of the 24 weekday hours. Any spill from the station would be hidden inside that jam. These are the two sites with the most understaffing-queue reviews, so the risk there is unknown, not low.

## Rain

Not estimable yet. Rain slots (core `rain_flag`) are few and not matched by hour: Makassar has none, Pemogan has 7 in daytime, Gayungan 6. Raw rain-versus-dry comparisons point in both directions (Daan Mogot: lower approach delay in rain; Bandung: higher). That reflects which hours it rained in, not an effect of rain. The `rain_flag` recheck (`.7.13`) is also open. Revisit at 4 weeks with an hour-matched comparison: same site, same local hour, rain versus dry, and at least 8 rain slots in the hours compared.

## Limits

- **8 days.** Seven full days and two weekend days. Each weekend hour rests on 4 readings, so weekend windows are indicative only. One unusual day can move a site (Pemogan, 13 Oct), so the ranking needs a rerun at 14 days and again at 4 weeks.
- **Two legs per site.** A slowdown somewhere in the 500 m before the Front point cannot be placed at the turn-in. Routes returns no step or speed-interval detail at the field mask we use.
- **Routes API, not RMI.** Durations are Google's traffic-aware estimate from probe data, sampled once every 30 minutes. Queues shorter than a slot are missed or caught once. A motorcycle queue on the shoulder may not slow the speeds Google reports.
- **`congestion_index` is our inference.** It is relative to each leg's own p10, so a road that is "always somewhat slow" in the day (Makassar) reads as Moderate much of the time. The 20 s gate sits close to the size of those delays.
- **No ground truth.** No queue has been observed or counted at any site.
- **Reviews are weak corroboration only.** That sample has at most 15 reviews per site, and the Indonesian windows are complaint-selected (see the complaints analysis). One or two reviews are not evidence for any one site.

## Validation plan

The proxy only points Pertamina to places to look. Each step below says what would count as confirmation.

| Step | What | Sites and windows | Confirms when |
|---|---|---|---|
| 1. Desk check (now, no cost) | Street View and the basemap along each approach leg: signals, U-turn gaps (putaran balik), bus or angkot stops, merges, crossings between Entry and Front | Pemogan, MT Haryono, Makassar, Lingkar Selatan | No signal or U-turn gap within about 150 m before the Front point. If there is one, that site drops to very low |
| 2. Transaction counts (ask Pertamina) | Transactions or litres per 30 min by product (Pertalite, Solar, Pertamax), with nozzles open and attendants on shift, for 7–14 Oct and onward | All 10; first ask Pemogan 13 Oct 08:00–15:00 WITA (Solar supply or a lane closure?) | ALS slots fall in the site's top-quartile demand slots far more often than non-ALS slots, or demand flat-tops (at capacity) during ALS windows |
| 3. CCTV (ask Pertamina) | Forecourt and entrance cameras. 10 ALS slots and 10 same-hour non-ALS slots per site, coded blind as "queue reaches the road: yes or no" | Pemogan, MT Haryono, Gayungan (the disagreement case), Daan Mogot (masked) | Yes in at least 6 of 10 ALS slots and at most 2 of 10 controls |
| 4. Site visit (if no CCTV) | One observer logs the queue length (vehicles) and kerb-lane blocking at each :00 and :30 | Pemogan weekdays 07:00–12:00 against a 13:00–15:00 control; MT Haryono 19:00–23:00 against 15:00–17:00; 2 weekdays each | Same bar as step 3 |

If steps 3 or 4 confirm at Pemogan and MT Haryono, ALS can carry the label "likely queue". If they do not, the screen keeps the neutral label "slower before the station than after it" and drops the queue language. For the masked sites, step 2 is the only route, because road data cannot see them.

## Screen proposal

**Where.** A new card, "Queue risk (approach)", on the site page (`/site/:site_id`). It sits directly under Busy hours (screen 4 in the traffic-presentation plan) and uses the same vocabulary: a 24-cell strip, a weekday/weekend control, faded hours under 4 readings, and the "Show as table" control.

**What it shows.**

- One headline in plain words, for example "Before the station, traffic slows while the road past it flows: weekdays 07:00–12:00, on 7 of 7 days, usually 1–3 min."
- A 24-cell strip of the ALS share per local hour, with approach-only busy hours outlined.
- Three facts: days with 2 h or more of ALS, the median approach delay in ALS slots, and the longest run.
- A confidence chip (Medium, Low, Very low) with its reason in one line.
- A fixed caption: "Road traffic on the 500 m before the station, not a forecourt queue count."
- A masked state, for sites like Bandung and Daan Mogot: "The road past the station is slower than the road before it at these hours, so a station queue cannot be seen here." It shows no strip.
- A link to the Review themes panel's `antrian` and `keamanan_lalu_lintas` counts, labelled "sampled reviews, weak evidence".

**Overview.** No queue ranking yet. Once there are 14 days of data and at least one validation step agrees, add a "Queue risk" sort to the side list, showing rank and confidence chip with the masked sites at the end. The existing 7-day ranking gate is met, but a ranking reads as a finding, and that needs ground truth first.

**Hidden until ready.**

| Item | Until |
|---|---|
| Overview ranking | 14 days and one validation step agreeing |
| Weekend headline | 4 weekend days in the window. Until then the strip shows weekend hours faded and the headline uses weekdays |
| Rain effect | 4 weeks, `.7.13` closed, and at least 8 hour-matched rain slots |
| "Likely queue" wording | Validation steps 3 or 4 confirm |

**API.** One endpoint, `GET /api/traffic/queue-risk?site_id=`, over the same 28-day window as typical-day. It reuses `busy.py`'s gates and `holidays.py`, so the band rule stays in one place. ALS needs both legs from the same slot, so it cannot be computed from the per-leg typical-day aggregates. Core columns only, no demo-only badge.

## Follow-ups for the orchestrator

- Rerun this analysis at 14 days (2026-10-21) and at 4 weeks (2026-11-03, alongside `.11.7`).
- Desk check of the four approach legs (validation step 1).
- Ask Pertamina for per-30-minute transaction counts and CCTV access (validation steps 2 and 3).
- With RMI: register a short third SelectedRoute covering the last 100–150 m before each turn-in, so a slowdown can be placed at the station. This changes `routes` and needs a decision.
- Build the card and endpoint above, after validation step 1.

## Reproduce

Both queries share the same CTEs. Run with `bq query --project_id=gcp-coe-sandbox --use_legacy_sql=false < file.sql`. Change the two timestamps to move the window. Because the baseline view uses the trailing 7 days from now, a later rerun of the same window gives slightly different delays.

Per-site metrics (the Results table):

```sql
-- Queue-risk proxy per site. Core columns only: v_traffic (delay_s, congestion_index), routes (leg), sites (timezone, road_type).
WITH legs AS (
  SELECT
    r.site_id, r.leg, t.slot_time,
    DATE(t.slot_time, s.timezone) AS local_date,
    EXTRACT(HOUR FROM t.slot_time AT TIME ZONE s.timezone) AS hour,
    IF(EXTRACT(DAYOFWEEK FROM t.slot_time AT TIME ZONE s.timezone) IN (1, 7)
       OR DATE(t.slot_time, s.timezone) IN ('2026-01-01','2026-01-16','2026-02-17','2026-03-19','2026-03-21',
         '2026-03-22','2026-04-03','2026-04-05','2026-05-01','2026-05-14','2026-05-27','2026-05-31','2026-06-01',
         '2026-06-16','2026-08-17','2026-08-25','2026-12-25'),
       'weekend', 'weekday') AS day_kind,
    t.delay_s,
    -- Moderate or worse under the signed-off band rule (baseline is full on all legs: 336 samples >= 302).
    t.congestion_index >= 1.5 AND t.delay_s >= IF(LOWER(s.road_type) LIKE '%toll%', 30, 20) AS slow
  FROM traffic.v_traffic AS t
  JOIN traffic.routes AS r ON r.selected_route_id = t.selected_route_id AND r.active
  JOIN traffic.sites AS s ON s.site_id = r.site_id
  WHERE t.slot_time >= TIMESTAMP('2026-10-06 17:30:00') AND t.slot_time < TIMESTAMP('2026-10-14 08:30:00')
    AND t.delay_s IS NOT NULL
),
paired AS (  -- one row per site and slot: both legs come from the same computeRoutes call
  SELECT a.site_id, a.slot_time, a.local_date, a.hour, a.day_kind,
    a.delay_s AS app_delay_s, d.delay_s AS dep_delay_s, a.slow AS app_slow, d.slow AS dep_slow,
    a.slow AND NOT d.slow AS als  -- approach-led slowdown
  FROM legs AS a
  JOIN legs AS d ON d.site_id = a.site_id AND d.slot_time = a.slot_time AND d.leg = 'departure'
  WHERE a.leg = 'approach'
),
runs AS (  -- consecutive ALS slots
  SELECT site_id, grp, COUNT(*) AS len
  FROM (SELECT *, COUNTIF(NOT als) OVER (PARTITION BY site_id ORDER BY slot_time) AS grp FROM paired)
  WHERE als GROUP BY 1, 2
),
daily AS (
  SELECT site_id, local_date, COUNT(*) AS n, COUNTIF(als) AS als_n FROM paired GROUP BY 1, 2
)
SELECT
  p.site_id,
  COUNT(*) AS slots,
  ROUND(100 * AVG(IF(p.app_slow, 1, 0)), 1) AS approach_slow_pct,
  ROUND(100 * AVG(IF(p.app_slow AND p.dep_slow, 1, 0)), 1) AS both_slow_pct,
  ROUND(100 * AVG(IF(p.dep_slow AND NOT p.app_slow, 1, 0)), 1) AS departure_only_pct,
  ROUND(100 * AVG(IF(p.als, 1, 0)), 1) AS als_pct,
  ROUND(100 * AVG(IF(p.day_kind = 'weekday', IF(p.als, 1, 0), NULL)), 1) AS als_weekday_pct,
  ROUND(100 * AVG(IF(p.day_kind = 'weekend', IF(p.als, 1, 0), NULL)), 1) AS als_weekend_pct,
  APPROX_QUANTILES(IF(p.als, p.app_delay_s, NULL), 100)[OFFSET(50)] AS als_median_delay_s,
  COUNTIF(p.als AND p.app_delay_s >= 60) AS als_slots_over_1min,
  ANY_VALUE(d.days_als_2h) AS days_with_2h_als,
  ANY_VALUE(d.full_days) AS full_days,
  ANY_VALUE(r.longest_run_h) AS longest_als_run_h
FROM paired AS p
LEFT JOIN (SELECT site_id, COUNTIF(n >= 40 AND als_n >= 4) AS days_als_2h, COUNTIF(n >= 40) AS full_days
           FROM daily GROUP BY 1) AS d USING (site_id)
LEFT JOIN (SELECT site_id, MAX(len) / 2 AS longest_run_h FROM runs GROUP BY 1) AS r USING (site_id)
GROUP BY p.site_id
ORDER BY days_with_2h_als DESC, als_median_delay_s DESC
```

Busy hours per leg (the busy-window table): the same `legs` and `paired` CTEs, then:

```sql
SELECT site_id, day_kind, hour, n, app_median_s, dep_median_s, als_n,
  app_slow_n * 2 >= n AND app_median_s >= 30 AS approach_busy,
  dep_slow_n * 2 >= n AND dep_median_s >= 30 AS departure_busy
FROM (
  SELECT site_id, day_kind, hour, COUNT(*) AS n, COUNTIF(als) AS als_n,
    COUNTIF(app_slow) AS app_slow_n, COUNTIF(dep_slow) AS dep_slow_n,
    APPROX_QUANTILES(app_delay_s, 100)[OFFSET(50)] AS app_median_s,
    APPROX_QUANTILES(dep_delay_s, 100)[OFFSET(50)] AS dep_median_s
  FROM paired GROUP BY 1, 2, 3
)
ORDER BY site_id, day_kind, hour
```

The night check is the median of `app_delay_s - dep_delay_s` by site and weekday hour over the same `paired` CTE.
