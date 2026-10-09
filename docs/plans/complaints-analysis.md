# Complaint analysis of Google reviews: first pass

Bead pertamina-retail-traffic-907.10.5. Analysis date 2026-10-09. Input: `traffic.v_place_reviews` (no author fields) joined to `traffic.sites`, read-only. Taxonomy and design: [reviews-feasibility.md](reviews-feasibility.md) section 8; tables: [data-schema.md](data-schema.md) "Reviews tables". This file holds aggregates, definitions and paraphrased gists only. Review text, author names and review ids stay in `out/complaints/` (git-ignored).

## Read this first: what the sample is

> Each site has at most 15 reviews, drawn from three Place Details windows: newest-5 (Indonesian), most-relevant-5 (Indonesian) and most-relevant-5 (English). Relevance sorting over-selects 1-star complaints in Indonesian and 4 to 5 star praise in English; "newest" covers roughly the last month at urban sites and about two days at KM57A. Counts below describe this sample, not the station: a category appearing in 8 of 15 reviews is not a rate, and sites cannot be ranked against each other on these numbers.

Consequences for every table below:

- Counts are numbers of sampled reviews, never shares of a station's customers or complaints. Do not quote them as "X% of visitors".
- Per-site n is 4 to 10 negative or mixed reviews. A 1-review difference between sites is noise.
- KM57A looks clean partly because 14 of its 15 sampled reviews are five-star; its newest-5 spans two days.
- The recent/older split (cut at 2025-10-09) is almost the same as the window split: 96 of the 100 Indonesian reviews are recent, 44 of the 50 English ones are older. A difference between "recent" and "older" is mostly a difference between the Indonesian and English windows, not a trend.

## Method

- Rows: 149 distinct reviews over 10 SPBU, published 2014-12 to 2026-10. 127 have text; 22 are rating-only and are not labelled (they count in the site and window tables only).
- Window counts use `seen_in` membership: 150 window appearances for 149 reviews, because one Pemogan review was returned by both the newest and most-relevant (Indonesian) windows.
- Labelling: every review with text was read and labelled by a single automated reader, with no Indonesian-speaking human review, multi-label against the taxonomy, no external model or API call. Labels are topics, not complaints: a clean-toilet compliment gets `toilet` and `kebersihan` with sentiment `pos`. Tables on "complaints" therefore filter on sentiment (`neg` or `mixed`), not on star rating, because several 4 to 5 star reviews carry a complaint (short change, QRIS refused, staff idling) and several 3-star reviews are neutral.
- `sentiment`: `pos` = no complaint; `mixed` = praise and complaint both; `neg` = complaint dominates. `praise_only` is true exactly when sentiment is `pos`. Bare "Ok", "Good" or emoji reviews get no categories and sentiment `pos`; a 3-star "Ok" is included in that (neutral, no complaint).
- Decisions applied everywhere:
  - Understaffing queues (one open lane, one attendant covering the car and motorcycle lanes) get `antrian` only. `pelayanan_petugas` is added only when staff behaviour is attacked (rudeness, idling, inattention).
  - Barcode or MyPertamina rejection and QRIS limits go to `pembayaran`. A subsidised grade not served, or a lane closed before the stated time, goes to `bbm_kosong`.
  - Jerry-can queue-jumping or bulk buying and fuel spilled while filling go to `lainnya`.
  - Queue spill to the road, or traffic management inside the site, goes to `keamanan_lalu_lintas`.
- Masking: gists contain no personal names, plate numbers, vehicle descriptors, phone numbers or exact dates.
- Labels: `out/complaints/2026-10-09/labels.json` (`review_key`, `labels[]`, `sentiment`, `praise_only`, `gist`). Nothing was cross-checked by a human, so these are a first draft, not gold labels (see Limitations).

### Category definitions

| Category | Covers |
|---|---|
| `antrian` | Queue, waiting time, lane or staff shortage causing a queue |
| `pelayanan_petugas` | Attendant attitude, rudeness, idling, slowness of a named role or shift |
| `bbm_kosong` | Grade out of stock or not served (Pertalite, Solar), service-hour cut-offs |
| `kualitas_bbm` | Contaminated or bad fuel, engine trouble after filling |
| `takaran` | Short fill, meter not accurate, suspected manipulation |
| `pembayaran` | QRIS (including minimums), MyPertamina, barcode, EDC, cash, change |
| `harga` | Price |
| `kebersihan` | Cleanliness (site, toilet) |
| `toilet` | Toilet condition or access |
| `fasilitas` | Musholla, parking, ATM, minimarket, water and air, lighting |
| `keamanan_lalu_lintas` | Traffic or safety at entry or exit, queue spilling onto the road |
| `lainnya` | Everything else (jerry-can use, spillage, site size, operating hours) |

## Sample counts

Window columns count appearances (N newest-5 Indonesian, R most-relevant-5 Indonesian, E most-relevant-5 English). "Recent" = published on or after 2025-10-09.

| Site | Distinct | N | R | E | With text | Rating-only | Recent | Stars 1 / 2 / 3 / 4 / 5 |
|---|---|---|---|---|---|---|---|---|
| 24.351.34 Antasari, Bandar Lampung | 15 | 5 | 5 | 5 | 13 | 2 | 11 | 6 / 1 / 1 / 3 / 4 |
| 24.351.97 Tirtayasa, Bandar Lampung | 15 | 5 | 5 | 5 | 14 | 1 | 10 | 6 / 2 / 1 / 0 / 6 |
| 34.117.12 Daan Mogot, Jakarta Barat | 15 | 5 | 5 | 5 | 14 | 1 | 11 | 8 / 0 / 0 / 3 / 4 |
| 34.121.03 Lingkar Selatan, Jakarta Selatan | 15 | 5 | 5 | 5 | 12 | 3 | 10 | 3 / 0 / 2 / 6 / 4 |
| 34.401.16 Bandung | 15 | 5 | 5 | 5 | 12 | 3 | 10 | 5 / 1 / 1 / 3 / 5 |
| 54.601.80 Gayungan, Surabaya | 15 | 5 | 5 | 5 | 14 | 1 | 10 | 5 / 2 / 1 / 2 / 5 |
| 54.801.17 Pemogan, Denpasar | 14 | 5 | 5 | 5 | 12 | 2 | 10 | 3 / 0 / 1 / 2 / 8 |
| 61.761.03 MT Haryono, Balikpapan | 15 | 5 | 5 | 5 | 11 | 4 | 10 | 3 / 0 / 1 / 1 / 10 |
| 74.902.22 Makassar | 15 | 5 | 5 | 5 | 13 | 2 | 9 | 7 / 2 / 3 / 1 / 2 |
| KM57A rest area, Karawang | 15 | 5 | 5 | 5 | 12 | 3 | 10 | 0 / 0 / 1 / 0 / 14 |
| **All** | **149** | **50** | **50** | **50** | **127** | **22** | **101** | |

Stars by window (all reviews): newest 15 / 4 / 1 / 3 / 27; most-relevant Indonesian 30 / 3 / 3 / 3 / 11; most-relevant English 1 / 1 / 8 / 15 / 25. Sentiment of labelled text: 58 negative, 13 mixed, 56 positive. By window: newest 18 neg + 1 mixed of 28; most-relevant Indonesian 36 neg + 4 mixed of 50; English 4 neg + 8 mixed of 50.

## Category frequency

Counts are reviews carrying the topic. Table 1 is the sample as a whole (not a rate). Negative or mixed reviews: 71 (recent 58, older 13).

| Category | Negative or mixed (71) | Recent (58) | Older (13) | All text (127) |
|---|---|---|---|---|
| `pelayanan_petugas` | 33 | 31 | 2 | 53 |
| `antrian` | 30 | 23 | 7 | 40 |
| `pembayaran` | 14 | 14 | 0 | 21 |
| `keamanan_lalu_lintas` | 7 | 6 | 1 | 7 |
| `lainnya` | 6 | 5 | 1 | 7 |
| `bbm_kosong` | 5 | 5 | 0 | 6 |
| `kebersihan` | 5 | 0 | 5 | 15 |
| `toilet` | 5 | 1 | 4 | 19 |
| `takaran` | 4 | 4 | 0 | 5 |
| `fasilitas` | 4 | 1 | 3 | 26 |
| `kualitas_bbm` | 2 | 2 | 0 | 3 |
| `harga` | 0 | 0 | 0 | 0 |

Reading it: staff attitude, queues and payment dominate the sampled complaints. All 5 cleanliness items date from 2017 to 2023 (4 from the English window, 1 from most-relevant Indonesian) and 4 of the 5 toilet items do too; the one 2026 toilet item is a staff-conduct complaint at Lingkar Selatan. KM57A supplies the largest share of facilities and toilet mentions (8 of 22 positive `fasilitas` mentions), nearly all praise. None of this says much about 2026 service quality. No review in the sample mentions price. All counts above apply to this sample only.

Negative or mixed reviews per site. Column legend: n = negative or mixed reviews, ant = `antrian`, pel = `pelayanan_petugas`, bbm = `bbm_kosong`, kual = `kualitas_bbm`, tak = `takaran`, pem = `pembayaran`, keb = `kebersihan`, toi = `toilet`, fas = `fasilitas`, lal = `keamanan_lalu_lintas`, lain = `lainnya` (`harga` omitted: 0 everywhere).

| Site | n | ant | pel | bbm | kual | tak | pem | keb | toi | fas | lal | lain |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 24.351.34 Antasari | 8 | 1 | 6 | 1 | 1 | 0 | 3 | 0 | 0 | 0 | 0 | 3 |
| 24.351.97 Tirtayasa | 9 | 5 | 7 | 3 | 0 | 1 | 0 | 0 | 0 | 0 | 1 | 0 |
| 34.117.12 Daan Mogot | 10 | 6 | 3 | 0 | 0 | 2 | 3 | 0 | 0 | 1 | 1 | 0 |
| 34.121.03 Lingkar Selatan | 7 | 2 | 3 | 0 | 0 | 0 | 2 | 0 | 1 | 0 | 0 | 1 |
| 34.401.16 Bandung | 7 | 5 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 |
| 54.601.80 Gayungan | 9 | 4 | 3 | 0 | 1 | 0 | 2 | 1 | 0 | 0 | 3 | 0 |
| 54.801.17 Pemogan | 4 | 1 | 2 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 1 | 1 |
| 61.761.03 MT Haryono | 5 | 3 | 1 | 1 | 0 | 0 | 2 | 0 | 0 | 0 | 1 | 0 |
| 74.902.22 Makassar | 10 | 2 | 7 | 0 | 0 | 0 | 2 | 2 | 2 | 0 | 0 | 0 |
| KM57A rest area | 2 | 1 | 0 | 0 | 0 | 0 | 0 | 2 | 2 | 2 | 0 | 0 |

Recent (last 12 months) versus older: 58 of the 71 negative or mixed reviews are recent (38 most-relevant Indonesian, 19 newest, 1 English) and 13 are older (11 English, 2 most-relevant Indonesian). The older ones sit at Makassar (3), Daan Mogot (2), Gayungan (2), MT Haryono (2), KM57A (2), Lingkar Selatan (1) and Bandung (1); Antasari, Tirtayasa and Pemogan have none. Per-site recent counts are the table above minus these.

## Per-site top issues

Traffic flag: relevant to .10.1 means `antrian`, `keamanan_lalu_lintas` or `bbm_kosong` causing a queue. All statements are about sampled reviews.

- **Antasari (Bandar Lampung)**: staff attitude (6 of 8 negative or mixed reviews, night shift and female attendants named by role); payment (QRIS and MyPertamina unavailable, barcode "disturbance" while the grade seemed out, change dispute); jerry-can queue-jumping and bulk buying, plus fuel spilled while filling. Traffic relevance: low in this sample (1 queue mention); the jerry-can items touch queue fairness.
- **Tirtayasa (Bandar Lampung)**: staff attitude (7 of 9), queues (5): service slow while queues wait, a Solar queue forming on the roadside from morning because the Solar pump opens only in the evening, Pertalite lane closed before the stated time. One short-fill complaint. Traffic relevance: high (`antrian`, roadside queue, `bbm_kosong` as queue cause).
- **Daan Mogot (Jakarta Barat)**: queues (6 of 10), almost all about one lane or one attendant open while others idle, Pertalite worse than Pertamax, queue reaching the entrance or the road; QRIS minimum purchase (3 reviews, 25k and 50k thresholds, not displayed); two short-fill or meter complaints. Traffic relevance: high.
- **Lingkar Selatan (Jakarta Selatan)**: staff attitude (3), QRIS or change disputes (2), one complaint about staff using the public toilet; positives are facilities and parking. Traffic relevance: low (queue mentions are mild: motorcycle queues in general, small site, hectic evenings).
- **Bandung 3440116**: queues (5 of 7), all one pattern: one attendant covering both the car and motorcycle lanes, shared Pertalite and Pertamax queue, 20 to 30 minute waits at rush hour. Facilities praised. Traffic relevance: high, but queue cause is staffing.
- **Gayungan (Surabaya)**: queues (4) and queue spill onto the arterial road (3 reviews: Pertalite motorcycle queue reaching the main road, danger to passers-by, buses blocking flow), no QRIS (2), staff attitude (3), one report of contaminated fuel causing engine stalls (single review). Traffic relevance: highest in the sample for road spill.
- **Pemogan (Denpasar)**: only 4 negative or mixed reviews, so thin: Solar queues spilling into the bypass for two consecutive days (reported as causing jams), staff attitude (2), spilled Solar, one meter or no-receipt complaint. Traffic relevance: high but one reviewer.
- **MT Haryono (Balikpapan)**: mostly positive (10 of 15 are 5 stars). Complaints: QRIS unavailable at shift change or limited to some banks (2), Pertalite lane announced as closing early (1), an older complaint about queues blocking the road and a narrow inner area. Traffic relevance: moderate.
- **Makassar**: staff attitude (7 of 10, concentrated on late shifts and the motorcycle or car side by role), subsidised-fuel barcode and MyPertamina refusals (2), understaffing queue (2), two older English reviews on dirty toilets. Traffic relevance: moderate.
- **KM57A rest area (Karawang)**: 14 of 15 reviews are 5 stars. Queue mentions are a self-service fuel queue (2023) and holiday crowding; the two flagged mixed reviews are an old note that the toilet needed cleaning and a request to keep the toilets and mosque clean. No complaint about queues in the newest-5 (two days of data). Traffic relevance: low in this sample, but the sample is the least informative of the ten.

## Notable patterns

Confidence reflects both n and the sampling bias. "Sites" = how many of the 10.

| Pattern | Evidence in sample | Confidence |
|---|---|---|
| **Understaffing leads to queues**: one lane open or one attendant covering car and motorcycle lanes, Pertalite lane thinner than Pertamax | About 13 reviews at 4 sites (Daan Mogot 5, Bandung 5, Makassar 2, Gayungan 1); consistent explanation across independent reviewers, almost all in 2026 | Medium: consistent, but 2 sites supply 10 of the 13 and the Indonesian windows are complaint-selected |
| **Queue spill onto the road** | 7 reviews at 5 sites (Gayungan 3, Tirtayasa, Daan Mogot, Pemogan, plus one 2019 review at MT Haryono) | Medium for Gayungan, low for the rest (1 review each) |
| **Solar or Pertalite lane hours and cut-offs** causing roadside queues | Tirtayasa (Solar opens late, queue from morning; lane closed early), MT Haryono (Pertalite lane closed before time), Antasari (Pertalite seemed out) | Low: 3 sites, 1 review each |
| **QRIS availability and limits** | 9 reviews at 5 sites (with barcode, MyPertamina and change disputes, `pembayaran` is 14 reviews at 6 sites, Makassar being the sixth): unavailable (Gayungan, Antasari, Lingkar Selatan, MT Haryono at shift change), unaccepted bank (MT Haryono), minimum purchase 25k to 50k (Daan Mogot, 3 reviews) | Medium: recurring, same causes |
| **Subsidised-fuel barcode / MyPertamina rejection** | 3 reviews at 2 sites (Antasari, Makassar): barcode "disturbance", vehicle colour mismatch with registration, MyPertamina refused for Pertamax. The brief's expected "barcode queue" pattern is not visible as queues here, only as rejections | Low |
| **Staff attitude by shift** | 33 negative or mixed reviews, spread over 9 sites; night shift, female attendants and motorcycle side named by role at several sites | Medium on prevalence in this sample; low on the shift detail |
| **Short fill or meter suspicion** | 4 reviews at 3 sites (Tirtayasa, Daan Mogot 2, Pemogan); a serious allegation, no verification possible | Low |
| **Toilet complaints at the toll rest area**: not supported | KM57A toilet mentions are positive except one 2017 note; dirty-toilet complaints are at Makassar (2, English window, 2022 and 2023) and one at Lingkar Selatan (staff using it to bathe) | Low (n 1 to 2) |
| **Fuel quality** | One review at Gayungan (contaminated fuel, repeated stalling), one doubt at Antasari | Very low: needs corroboration before any statement |
| **Jerry-can and subsidised-fuel diversion** | 2 reviews at Antasari | Low, Pertamina-relevant |

## Keyword baseline versus labels

Script `out/complaints/baseline.py` (not in the repo): one regex per category, Indonesian and English keywords, no stemmer. It was written once after reading the reviews and not tuned afterwards, but the reviews are the same 127 that were labelled, so there is no holdout and the numbers are optimistic. Labels are treated as truth.

| Category | n true | TP | FP | FN | Precision | Recall |
|---|---|---|---|---|---|---|
| `antrian` | 40 | 36 | 5 | 4 | 0.88 | 0.90 |
| `pelayanan_petugas` | 53 | 51 | 18 | 2 | 0.74 | 0.96 |
| `bbm_kosong` | 6 | 4 | 15 | 2 | 0.21 | 0.67 |
| `kualitas_bbm` | 3 | 2 | 1 | 1 | 0.67 | 0.67 |
| `takaran` | 5 | 4 | 7 | 1 | 0.36 | 0.80 |
| `pembayaran` | 21 | 21 | 8 | 0 | 0.72 | 1.00 |
| `harga` | 0 | 0 | 3 | 0 | 0.00 | n/a |
| `kebersihan` | 15 | 15 | 1 | 0 | 0.94 | 1.00 |
| `toilet` | 19 | 19 | 1 | 0 | 0.95 | 1.00 |
| `fasilitas` | 26 | 22 | 3 | 4 | 0.88 | 0.85 |
| `keamanan_lalu_lintas` | 7 | 6 | 15 | 1 | 0.29 | 0.86 |
| `lainnya` | 7 | 5 | 16 | 2 | 0.24 | 0.71 |

Micro precision 0.67, micro recall 0.92; the exact label-set matches in 57 of 127 reviews. Categories with a single-digit true count (`bbm_kosong`, `kualitas_bbm`, `takaran`, `keamanan_lalu_lintas`, `lainnya`, `harga`) carry no percentage meaning beyond "the rule is noisy".

What this implies:

- Rules work on concrete, rarely ambiguous vocabulary: `toilet`, `kebersihan`, `fasilitas`, `antrian`, `pembayaran` (high recall; the false positives are praise or generic "uang"/"bayar"). They fail where meaning depends on context: `bbm_kosong` (the word "solar" or "tutup" appears in unrelated sentences), `keamanan_lalu_lintas` ("jalan"), `lainnya`.
- Rules cannot see sentiment: "ramah" (friendly) counts as `pelayanan_petugas` in a compliment. Every table that matters here filters on complaint, so a sentiment-aware method is needed.
- Production path: Gemini zero-shot on Vertex AI with the fixed taxonomy, JSON schema output, temperature 0 and a pinned model version (as in the feasibility doc), with sentiment as a required field. Keep these rules only as a cheap sanity check and fallback for those five clean categories. Before relying on either, hand-label a stratified 100 with an Indonesian speaker; with the present 127 that would be most of the sample, so the validation should wait for the larger set (GBP or polled data). Re-run this baseline against those labels, not against the first-pass labels above.

## Proposed table `place_review_labels` (proposal only, no DDL written)

| Column | Type | Notes |
|---|---|---|
| `review_key` | STRING | key into `place_reviews`; MERGE key together with `method` |
| `site_id` | STRING | cluster column, as in `place_reviews` |
| `labels` | ARRAY<STRING> | taxonomy values above |
| `sentiment` | STRING | `neg`, `mixed`, `pos` |
| `praise_only` | BOOL | true when sentiment is `pos` |
| `gist` | STRING | one-line English gist, masked; optional to store, drop for GBP-sourced reviews if the 30-day rule is read to cover it |
| `method` | STRING | `manual`, `gemini_zero_shot`, `keyword_v1` |
| `model_version` | STRING | pinned Gemini version or rule-set version |
| `labeled_at` | TIMESTAMP | when labelled |

Clustered by `site_id`, not partitioned (a few thousand rows a year, same reasoning as `place_reviews`). Labels are re-derivable, so a taxonomy or prompt change can be re-run and replace rows by key. A labelling job would read `v_place_reviews` rows without a label for the current `method` and `model_version`. This is a schema decision; it needs an orchestrator OK before DDL.

## Dashboard panel idea

A "Review themes" panel per site with a "demo-only, sampled n<=15" badge (data comes from Places windows, not core RMI-compatible columns): stacked bars of negative or mixed topics, split into recent and older, and a small list of paraphrased gists with no author. Add a link-through to the traffic-risk view for `antrian`, `keamanan_lalu_lintas` and `bbm_kosong` counts. Show counts and n only, never percentages or cross-site rankings, until the sample is a full export.

## Limitations, and what more data changes

- Non-random sample, at most 15 per site, see the caveat at the top. Counts are not rates and sites are not comparable.
- One labeller, one pass, no Indonesian-speaking human check; slang, regional words and sarcasm may be misread. Treat labels as a draft. The keyword baseline agrees with them by construction of the same reading, so agreement is not accuracy.
- Reviews are self-selected (customers with a complaint or a compliment) and fuel type, shift and date are often missing; claims such as short-filling or fuel contamination are unverified single-reviewer reports.
- 22 rating-only reviews and the bare "Ok" style reviews carry no topic; one 2014 review reads like an owner or staff post, so treat it as praise-only noise.
- Dates: 96 of 100 Indonesian reviews fall in the last 12 months, but no site has more than about 10 recent text reviews, so no trend, seasonal or shift-level claim is supported.
- What more data would change:
  - **GBP API** (full history, owner replies, about 3,500 to 5,500 reviews a year across the 10 sites per the feasibility doc): replaces the biased windows, allows real per-site rates, monthly counts and a 12-month comparison. Needs listing ownership; storage under the GBP 30-day rule likely means keeping labels and counts only.
  - **Contact Center 135 export**: SPBU-level complaint categories with resolution, a different (direct-complainant) population that can validate the taxonomy and the subsidised-fuel and staffing patterns.
  - **Months of daily polling** (`reviews-poller`): newest-5 daily builds a time series for new complaints; the snapshot table gives the review rate; mixed daily polling does not remove the relevance-window bias but dilutes it as `place_reviews` grows.
  - **Human validation** of at least 100 labels by an Indonesian speaker, then precision and recall for Gemini and rules on that set.
