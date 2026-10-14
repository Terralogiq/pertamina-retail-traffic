# AI summaries per SPBU: design and prototype

Bead `.10.4` (Track F of `docs/plans/remaining-2026-10-14.md`). Design only plus one prototype; nothing is built into the dashboard, no BigQuery table exists, nothing is deployed. Prototype: `scripts/ai_summary_prototype.py` (tests: `tests/test_ai_summary_prototype.py`). Outputs of the runs below: `out/ai_summaries/final/` (git-ignored).

## Recommendation

| Topic | Choice | Why |
|---|---|---|
| Model and hosting | Gemini 3.8 Flash on the **Gemini API** now (same key, model and request shape as `reviews_job/gemini.py`); move to **Vertex AI Gemini, global endpoint, same price** for a production build | Cheapest option measured, 3–5 s per call, and the labeller already runs on it. No option can process in Jakarta (see Residency), so Vertex buys IAM and billing control, not residency. |
| Cadence | **Decision (user, 2026-10-14): on demand**, generated the first time a site page is opened in a 30-minute slot and stored in BigQuery for the rest of that slot; up to 1,500 summaries a month at about 50 views a day | Cost follows use (up to about $4 a month now, $8 from 1 January 2027) and the text is never more than one slot old. The first view per slot waits for facts and generation. The earlier recommendation was an hourly batch (about $13 / $26); see "Cadence and storage". |
| Display | **Decision (user, 2026-10-14): one card at the top of each of four site-page sections**, Traffic, Weather, Places and Review themes, instead of one block | One Gemini call per site and slot still writes all the sentences; each sentence's topic decides its card, so cost does not change. Each card sits next to the chart that backs it. |
| Grounding | SQL builds a facts JSON, Gemini only phrases it, and a pure-function validator rejects any number, time, weekday or direction word that is not in the facts | The model never queries data and never sees review text. |

The alternatives to the cadence decision and their cost are in the table below.

## What the prototype does

1. **Facts.** Eight read-only BigQuery queries per site (project `gcp-coe-sandbox`, location `asia-southeast2`) produce about 3,100 characters of JSON: traffic today and this week per leg, busy windows, weather, and the site profile. Bands, the delay gate and busy windows come from `dashboard/api/busy.py`, imported by path, so the summary and the dashboard cannot drift apart. The delay format matches `formatDelay` in `dashboard/web/src/map/bands.ts` (whole seconds under a minute, else minutes with one decimal).
2. **Phrasing.** The facts and a system prompt go to `gemini-3.8-flash` with a JSON schema: 3–5 sentences, each tagged `traffic`, `weather` or `site_profile`. Temperature 0, thinking level LOW (accepted by the API; not compared with the default level).
3. **Validation.** `validate_summary(sentences, facts)` is a pure function. Per sentence it checks that every number equals a fact or is the fact rounded to the number's own decimals (and reports which), that every `HH:MM` time is in the facts, that weekday names match the facts, that no date word, spelled-out number or quote appears, and that "slower" or "faster" only appears when a fact carries that direction. Sign is never the model's job: facts carry a direction word and an absolute value. It also requires 3–5 sentences.

What goes into the facts for each section:

| Section | Facts |
|---|---|
| Traffic | Per leg: today's slow slots (moderate or worse), peak delay and its time, median delay today against the median of the same hours on earlier days of the same kind (weekday or weekend), 7-day median and slow share, busiest hour, and the typical busy windows of today's day kind (empty until 7 local dates, with the days still needed). Worst leg only when the legs differ by 5 s or more. |
| Weather | Rain slots today, temperature range, and a rain effect per leg: the delay in a rain slot minus the median dry delay of the same local hour, so an afternoon shower that lands on the afternoon peak does not read as an effect of rain. Reported only from 8 compared slots. Rain means the core `rain_flag` only; `demo_rain_flag` is demo-only and stays out of the facts (it also catches light rain that `rain_flag` misses, bead `.7.13`, so light rain counts as dry here). |
| Site profile | Google rating and rating count, gas stations within 1 km and 3 km (site excluded, with a "list capped" flag because Nearby returns at most 20), counts of six place types within 500 m, and complaint-theme counts from `place_review_labels` (method `gemini`, `neg` and `mixed`). Review text, gists and author names are never queried. |

## Options compared

Prices are USD per 1M tokens, read from the pages linked in the table on 2026-10-14. One summary at the final prompt measured 1,842–1,930 input and 285–304 output tokens (2 calls); 14 live calls over the session are the latency sample.

| | Gemini API | Vertex AI Gemini | Claude Sonnet 5.5 on Vertex |
|---|---|---|---|
| Model | `gemini-3.8-flash` | `gemini-3.8-flash` | `claude-sonnet-5-5` |
| Price in / out | 0.75 / 3.75 to 31 Dec 2026, then 1.50 / 7.50 ([pricing](https://ai.google.dev/gemini-api/docs/pricing)) | Global: same as the API. Non-global (multi-region): +10%, 0.825 / 4.125 then 1.65 / 8.25 ([pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing)) | 2.00 / 10.00 global; 2.20 / 11.00 multi-region ([Anthropic list prices](https://assets.claude.com/1ef7a4a8e373004bc89d710b0a6f3f219323344f.pdf), [pricing page](https://platform.claude.com/docs/en/about-claude/pricing)) |
| Cost per summary | $0.0025 now, $0.0050 from 2027-01-01 | Same on the global endpoint | About $0.0067 (assumes the same token counts; Claude's tokenizer may count differently, unverified) |
| Batch discount | 50% (0.375 / 1.875 now) | 50% | 50% (global 1.00 / 5.00) |
| Where it processes | Not selectable in the pages I read | Global, or the US or EU multi-region. **No Jakarta endpoint** ([model page](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-8-flash), [locations](https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/locations): no `asia-southeast2` in the table) | Global, or US or EU multi-region. Regional endpoints stop at Sonnet 4.6 ([Claude on Vertex](https://platform.claude.com/docs/en/build-with-claude/claude-on-vertex-ai)), so there is no Jakarta endpoint either |
| Latency observed | 3.3–5.3 s, median about 3.9 s (14 calls) | Not measured. One trivial call to the `asia-southeast2` endpoint with ADC returned HTTP 400 `FAILED_PRECONDITION` in 0.3 s; I did not establish whether the region or the API enablement is the cause | Not measured |
| Prompt caching | Cached input 0.075 now. The static system prompt is about half the input (about 900 tokens, estimated from 2,814 characters), probably under any minimum cacheable size (unverified); saves at most about a quarter of the cost | Same | Cache reads 0.10 global; same size limit applies (unverified) |
| Setup | Exists: key in Secret Manager `gemini-api-key`, `gcp-coe-492507` | New: enable Vertex AI, grant the job's service account `roles/aiplatform.user` | New: enable the Claude model for the project (steps not checked) |
| Fit | Best for the demo | Best for production: IAM instead of a key, no key rotation | Only if Gemini quality fails the spot-check; about 2.7 times the cost |

**Residency.** Stored summaries and facts stay in BigQuery in `asia-southeast2`. The text sent to the model is aggregated counts and delays: no personal data, no review text. Processing location is the open point: none of the three options runs in Jakarta, so if a customer requires in-country processing, none of these satisfies it and the fallback is templated text with no model. Whether the Singapore region serves Gemini 3.8 Flash I could not read from the locations page extract (unverified).

**Free tier.** On the Gemini API free tier the content is used to improve Google's products; the paid tier is not ([pricing](https://ai.google.dev/gemini-api/docs/pricing)). I did not confirm that the key in `gcp-coe-492507` is on a paid project. Check before putting anything beyond demo facts through it.

### Monthly cost at 10 sites

Gemini API or Vertex global, from the measured tokens. Claude at the assumed token counts.

| Cadence | Summaries a month | Gemini now | Gemini from 2027-01-01 | Claude Sonnet 5.5 |
|---|---|---|---|---|
| Daily batch | 300 | $0.75 | $1.50 | $2.00 |
| On demand, cached per slot, about 50 views a day | up to 1,500 | $3.80 | $7.50 | $10 |
| **Hourly, 06:00–22:00 WIB** | 5,100 | **$12.80** | **$25.60** | $34 |
| Every 30-minute slot, all day | 14,400 | $36 | $72 | $97 |

For scale, the collector costs about $95 a month (`README.md`).

## Cadence and storage

| Option | For | Against |
|---|---|---|
| Per 30-minute slot, batch | Always current | $36–72 a month for text that rarely changes between slots |
| **Hourly daytime batch, stored** | Instant to display, validated before display, audit trail, one place for the key | Up to an hour stale; a text with `as of 15:00` is honest about it |
| Daily batch | Cheapest | A 06:30 summary describes yesterday; "today" is empty |
| On demand | Cost follows use | 10–12 s facts plus 4 s generation on the first view per slot, a key in the dashboard service, a failure state in the UI |

Proposal only, no DDL changed. Table `traffic.ai_summaries`, partitioned by `DATE(as_of)`, clustered by `site_id`, MERGE key `(site_id, as_of, prompt_version)` so a retry overwrites its own row:

| Column | Type | Note |
|---|---|---|
| `site_id` | STRING | |
| `as_of` | TIMESTAMP | The latest slot the facts include, UTC |
| `generated_at` | TIMESTAMP | |
| `model`, `prompt_version` | STRING | e.g. `gemini-3.8-flash`, `s4`. The API aliases model ids forward (see `reviews_job/gemini.py`), so also store the response's `modelVersion` |
| `facts` | JSON | The exact facts the model saw; makes every summary re-checkable |
| `sentences` | ARRAY<STRUCT<topic STRING, text STRING, ok BOOL, problems ARRAY<STRING>>> | |
| `validation_ok` | BOOL | |
| `input_tokens`, `output_tokens`, `latency_ms` | INT64 | Cost is derived |

The dashboard shows the latest row with `validation_ok`. When validation fails the job retries once, then keeps the previous summary and the dashboard shows its older `as_of`.

## Grounding and evaluation

- **Numbers come from SQL.** The model gets no tool and no table access. The prompt forbids arithmetic, unit conversion, dates and causal wording, and each rule has a validator check where one is mechanical.
- **Automatic gate on every summary:** the validator above. Its reject rate is a running metric.
- **Offline spot-check:** a frozen set of facts snapshots (10 sites at 3 times of day) re-run when the model id or `prompt_version` changes; a human checks 10 sentences a week against `facts` in the table. Target: zero invented figures and zero direction errors, which is also what a release is judged on.
- **What the validator cannot catch.** It checks that a value exists in the facts, not that the sentence uses it correctly. Examples: pairing a peak time with the wrong leg, writing "rain slowed traffic" instead of "coincided with" (prompt-only), stating a capped competitor count without "at least" (prompt-only), mis-translating a theme key, and combining two true facts into a claim neither makes. Rounding makes small integers easy to match by accident (a stated "3" matches a fact of 2.6). Every number's match kind (`exact` or `rounded`) is stored in the validation result so reviewers can see it.

## UI labelling

Every summary card shows:

- A badge **AI-generated**, with the model name.
- **Data up to 15:00 WIB** (the `as_of` slot in the site's timezone) and the time it was generated.
- The **demo-only** badge only when a `demo_*` field feeds the summary (`.claude/rules/data-sources.md`). None does today: the facts use core columns (`v_traffic` is RMI-compatible, `rain_flag` is WeatherNext-compatible) and Places, which is the same source in production. Add the badge if a `demo_*` column is ever added to the facts.
- A "Source data" disclosure that lists the facts (the `facts` JSON, formatted) and the tables they came from.
- A note that review themes come from a small sample.
- Sentences that failed validation are never shown; the card falls back to the previous summary with its older timestamp.

## Samples

Run: `.venv/bin/python scripts/ai_summary_prototype.py --site 34.121.03 --site KM57A`, 2026-10-14 15:35 WIB (prompt `s4`, rain from the core `rain_flag` only). Both pass validation (every number `exact`). Site 34.121.03 is TB Simatupang, Jakarta Selatan, an urban site with a 17:00–19:00 busy window; KM57A is the Jakarta–Cikampek toll rest area, a quiet site this week.

**34.121.03** (5.3 s model call, 1,922 in, 391 out):

1. As of 15:30 on Wednesday, the approach leg had 4 slow slots with a peak delay of 25 s at 08:00 and a typical weekday busy window from 17:00 to 19:00 with 38 s median delay, while today showed no clear difference versus usual.
2. The departure leg flowed freely today across all 32 slots with no clear difference compared to usual, and on typical weekdays it has no usual busy window.
3. There was no rain today with temperatures ranging from 26 to 35 C, and historical comparison across 73 rain slots over 8 days of data shows no clear difference in delay associated with rain for either the approach or departure legs.
4. The station has a 4.4 Google rating from 1656 ratings, with 7 competitor gas stations within 1000 m and at least 19 within 3000 m.
5. Within a 500 m radius there are 83 lodging places, 156 restaurants, 12 convenience stores, 19 schools, 5 shopping malls, and 59 cafes, while a small sample of 12 reviews with text noted complaints about staff service in 3 reviews, payment in 2, and other in 1.

**KM57A** (4.9 s, 1,834 in, 287 out):

1. As of 15:30 on Wednesday, the approach leg had 1 slow slot today with a peak delay of 33 s at 02:00, while the departure leg flowed freely today across 32 slots; both legs show no clear difference compared to usual and have no usual busy window on typical weekdays.
2. It was not raining at 15:30 with temperatures between 25 and 36, and across 8 days of data with 62 rain slots compared, delays showed no clear difference associated with rain on either the approach or departure leg.
3. The station has a 4.5 Google rating from 12119 ratings, with 6 competitor gas stations within 1000 m and at least 19 within 3000 m.
4. Within 500 m there are 72 restaurants, 24 cafes, 7 convenience stores, 4 lodgings, 2 schools, and 2 shopping malls, while a small sample of 16 reviews with text raised complaints about cleanliness in 3 reviews, toilets in 3 reviews, and facilities in 2 reviews.

Two small wording faults remain that the validator cannot see: sentence 2 of KM57A writes "temperatures between 25 and 36" without a unit, and sentence 1 of 34.121.03 joins the busy window to "today" in one clause, which reads as if the window were today's. Neither misstates a fact.

### Spot-check against the data

I checked every sentence against the saved `facts` and, for the figures that BigQuery can answer on its own, against separate `bq` queries that do not use the script's code. All 9 sentences hold.

| Claim | Independent check |
|---|---|
| 34.121.03 approach: 4 slow slots today, peak 25 s at 08:00 | The four slots at 07:00, 07:30, 08:00 and 15:30 have delays 24, 22, 25 and 23 s at index 1.63, 1.58, 1.66 and 1.61; no other slot qualifies. The 15:30 slot is new since the earlier run (3 slow slots at 15:00) |
| 34.121.03 departure 0 slow slots across 32 slots; KM57A approach 1 slow slot, 33 s at 02:00; KM57A departure 0 across 32 slots | Counts of 0, 1 and 0 out of 32 slots each; the largest delays are 18.5, 33.0 and 16.0 s |
| Busy window 17:00–19:00, median 38 s | In the facts (the hour rule is imported from `busy.py`); not recomputed independently |
| 73 and 62 rain slots compared | Not comparable to a plain count: 87 and 76 slots had `rain_flag` set in 28 days, and the comparison keeps only rain slots whose local hour has at least 3 dry slots. Consistent with that. Before this change, with the demo flag included, the counts were 77 and 74 of 105 and 88 |
| 7 and 6 gas stations within 1 km; 19 within 3 km at both sites | Same counts from `places_nearby`, latest run, site excluded. 19 is the cap, hence "at least" |
| Rating 4.4 from 1656; 4.5 from 12119; 83 lodging, 156 restaurants, 12 convenience stores, 19 schools, 5 malls, 59 cafes at 34.121.03 | Same values in `places_details` and `places_aggregate` (500 m) |
| 12 and 16 reviews with text; themes 3 / 2 / 1 and 3 / 3 / 2 | Same counts from `v_place_reviews` and `place_review_labels` (`gemini`, `neg` and `mixed`), checked in the earlier run; Track C relabelled with prompt `p2` meanwhile and the counts are the same in this run's facts |
| "No rain today", 32 slots, 26–35 C and 25–36 C | 0 `rain_flag` slots among 32 weather slots today at both sites; temperature range from the facts |

Observations from earlier runs of the same pipeline:

- Run 1 flagged 2 of 10 sentences, run 2 flagged 1 of 9, run 3 none. The 3 flags were my gaps, not invented figures: the radii (1000 m, 500 m) were in key names, not values, and the site name "KM 57 A" carries a number. I fixed both. In 14 live calls the validator has not yet caught a figure the model made up; its behaviour on bad input rests on the 14 unit tests.
- Early drafts presented delays of 0.1–0.6 min as peaks. Two changes fixed that: the facts use seconds under a minute, and the prompt says a leg with 0 slow slots "flowed freely".
- Without a rule, the model dropped the busy window and omitted "at least" on the capped count. Both are now prompt rules.
- Dropping `demo_rain_flag` changed no conclusion: the rain effect is still 0 s at both sites, and rain-slot counts fell because light rain now counts as dry.

## Risks

| Risk | Mitigation |
|---|---|
| A plausible but wrong sentence passes the validator (see the list above) | Weekly human spot-check; facts stored with every summary; prompt rules for known failures |
| Every delay in the demo is under a minute at 500 m legs, so the "minutes-first" vocabulary does not apply to most sites today | Summaries use seconds under a minute, like the map. Decision for you: keep that, or hold summaries until delays are large enough to read in minutes |
| Model id aliases forward silently | Pin the id, store `modelVersion` from each response, re-run the frozen set when it changes |
| Free-tier key means the content may be used for training | Confirm the project is on the paid tier, or move to Vertex before production |
| No Jakarta processing for any model | Disclose it; BigQuery storage stays in Jakarta; a no-model template is the fallback |
| Price doubles on 1 January 2027 | Already in the cost table; the cost is small either way |
| Review themes are a sample of at most 5 reviews per poll | The prompt states the sample size; no ranking or percentages in the text |
| Facts take 10–12 s per site because the eight queries run one after another | Run them in parallel or read the dashboard's cached payloads; a build item |

## What a build would take

About 2–3 days.

| Item | Note |
|---|---|
| `traffic.ai_summaries` DDL in `sql/ddl.sql`, `data-schema.md` section | Schema above |
| On-demand generation in the dashboard API: when no valid row exists for the site's current slot, build facts, call Gemini, validate, MERGE, return; concurrent first views share one generation (single-flight, as in `dashboard/api/cache.py`) | Replaces the job and Scheduler entry of the hourly design. The `traffic-dashboard` service needs the `gemini-api-key` secret mounted (or the Vertex service account). While generating, each card shows the previous valid summary with its older time, or a skeleton if there is none; on failure it keeps the previous one |
| Prompt and schema: split topic `site_profile` into `places` and `review_themes`, and require at least one sentence per topic | One card per section: `traffic` on Traffic (covers Typical day), `weather`, `places`, `review_themes`. The validator's 3–5 sentence rule becomes 4–6 |
| Facts builder inside the job image | The job image cannot import `dashboard/` or `scripts/` (same constraint as `review_labels.py`). Move the busy-hour rules to a shared module, or copy them with a test that pins both to the same fixtures |
| Parallel or cached fact queries | Cuts 10–12 s to about 3 s |
| `GET /api/sites/{site_id}/summary` and a summary card at the top of the four sections, with the labels above | Returns the current slot's valid row, generating it if missing |
| Tests | Port the prototype tests; add a frozen-facts set with expected validation results |
| Decisions needed first | Seconds-under-a-minute wording, and whether the free-tier key is acceptable (cadence and display are decided) |

## Not done

The Vertex AI path was not run end to end and Claude was not called; their latency and token counts are unmeasured. Nothing was written to BigQuery. The facts SQL reads `v_traffic` for 28 days per site, which is cheap at the current size but has not been profiled.
