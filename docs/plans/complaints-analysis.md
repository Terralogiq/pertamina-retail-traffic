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
- Labelling: every review with text was read and labelled by a single automated reader, multi-label against the taxonomy, no external model or API call. Labels are topics, not complaints: a clean-toilet compliment gets `toilet` and `kebersihan` with sentiment `pos`. Tables on "complaints" therefore filter on sentiment (`neg` or `mixed`), not on star rating, because several 4 to 5 star reviews carry a complaint (short change, QRIS refused, staff idling) and several 3-star reviews are neutral.
- `sentiment` (three values only): `pos` = no complaint (covers praise and also purely informational reviews with neither praise nor complaint); `mixed` = praise and complaint both; `neg` = complaint dominates. `praise_only` is true exactly when sentiment is `pos`. Bare praise ("Good", an emoji, "Ok") gets no categories and sentiment `pos`; a 3-star "Ok" is included in that (neutral, no complaint).
- Reviews that look written by the station itself are kept; there is no exclusion rule.
- Decisions applied everywhere:
  - Queues caused by too few staff (one open lane, one attendant covering the car and motorcycle lanes) get `antrian` only. `pelayanan_petugas` is added only when staff behaviour (rudeness, idling, inattention) or the slowness of a named role or shift is criticised.
  - Barcode or MyPertamina rejection and QRIS limits go to `pembayaran`. `bbm_kosong` means the fuel is actually out of stock, or the grade is not sold or served because it is unavailable (including a subsidised grade's scheduled hours, e.g. a Solar pump that only opens in the evening). Being turned away, or a lane closed before its stated time, while the station still has fuel is `pelayanan_petugas` (a staff decision), not `bbm_kosong`. Rule from Gemini prompt p3 (2026-10-14); the first-pass labels and tables below predate it.
  - Jerry-can queue-jumping or bulk buying and fuel spilled while filling go to `lainnya`.
  - Queue spill to the road, or traffic management inside the site, goes to `keamanan_lalu_lintas`.
  - `lainnya` is rare: it is not used for a general or complimentary description (location, a large site, 24-hour service, grades or LPG on sale), and not added next to other labels when nothing specific is left over. Made explicit in Gemini prompt p2 (see "Gemini labels versus manual"); the manual pass applied it implicitly.
- **Decision (reviewer, 2026-10-14)**, from the Indonesian-speaking check of the 100-review validation sample, encoded in Gemini prompt p3:
  1. `bbm_kosong` = fuel actually out of stock, or a grade not sold or served because it is unavailable, including a subsidised grade's scheduled hours. A turn-away or a lane closed before its stated time while fuel is available is `pelayanan_petugas`.
  2. Sentiment stays `pos` / `mixed` / `neg`; `pos` means "no complaint" and covers praise and purely informational reviews.
  3. Unchanged, restated: queues from too few staff are `antrian` only (add `pelayanan_petugas` only for staff behaviour or the slowness of a named role or shift); bare praise gets no categories and `pos`; reviews that look written by the station are kept.
- Masking: gists contain no personal names, plate numbers, vehicle descriptors, phone numbers or exact dates.
- Labels: `out/complaints/2026-10-09/labels.json` (`review_key`, `labels[]`, `sentiment`, `praise_only`, `gist`). An Indonesian-speaking reviewer later checked 100 of the 127 and corrected 2 (see "Validation against a human reviewer"); the other 27 are unchecked.

### Category definitions

| Category | Covers |
|---|---|
| `antrian` | Queue, waiting time, lane or staff shortage causing a queue |
| `pelayanan_petugas` | Attendant attitude, rudeness, idling, slowness of a named role or shift |
| `bbm_kosong` | Fuel out of stock, or a grade not sold or served because it is unavailable (Pertalite, Solar), including a subsidised grade's scheduled hours. Not a turn-away or early lane closure while fuel is available (that is `pelayanan_petugas`) |
| `kualitas_bbm` | Contaminated or bad fuel, engine trouble after filling |
| `takaran` | Short fill, meter not accurate, suspected manipulation |
| `pembayaran` | QRIS (including minimums), MyPertamina, barcode, EDC, cash, change |
| `harga` | Price |
| `kebersihan` | Cleanliness (site, toilet) |
| `toilet` | Toilet condition or access |
| `fasilitas` | Musholla, parking, ATM, minimarket, water and air, lighting |
| `keamanan_lalu_lintas` | Traffic or safety at entry or exit, queue spilling onto the road |
| `lainnya` | A specific remark that fits no category above (jerry-can use, spillage, a cramped or too small site). Not praise or description of location, size, opening hours or products on sale |

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
- **Tirtayasa (Bandar Lampung)**: staff attitude (7 of 9), queues (5): service slow while queues wait, a Solar queue forming on the roadside from morning because the Solar pump opens only in the evening, Pertalite lane closed before the stated time (under the 2026-10-14 rule, an early closure with fuel available counts as `pelayanan_petugas`, not `bbm_kosong`; the Solar evening-hours item stays `bbm_kosong`). One short-fill complaint. Traffic relevance: high (`antrian`, roadside queue, `bbm_kosong` as queue cause).
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
| **Solar or Pertalite lane hours and cut-offs** causing roadside queues | Tirtayasa (Solar opens late, queue from morning; lane closed early), MT Haryono (Pertalite lane closed before time), Antasari (Pertalite seemed out) | Low: 3 sites, 1 review each. Note: under the 2026-10-14 rule only the scheduled-hours and out-of-stock items are `bbm_kosong`; an early closure with fuel available is `pelayanan_petugas` |
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
- Production path: Gemini zero-shot on Vertex AI with the fixed taxonomy, JSON schema output, temperature 0 and a pinned model version (as in the feasibility doc), with sentiment as a required field. Keep these rules only as a cheap sanity check and fallback for those five clean categories. A stratified 100 has since been human-reviewed (see "Validation against a human reviewer"); re-scoring this baseline against that set is bead `.10.23`.

## Gemini labels versus manual (2026-10-14, bead `.10.5.7`)

Caveat first: the `manual` labels are one reader's first draft (Method, Limitations), not gold. Agreement with them measures how close Gemini is to that reader, not accuracy; the human-reviewed comparison is in "Validation against a human reviewer" below. Aggregates only; the per-review comparison and raw text stay in `out/complaints/2026-10-14/` (git-ignored).

Set: the 127 reviews that have a `manual` label and text; Gemini `gemini-3.8-flash`, prompt p1 (`gemini-3.8-flash/p1`, first run 2026-10-10) and prompt p2 (`/p2`, run 2026-10-14 offline, same 127 plus 12 newer reviews; the stored rows come from a separate live run, see below). "Neg/mixed" is by the manual sentiment (71 reviews). Cells: reviews carrying the label.

| Category | All 127: manual | p1 | p2 | Neg/mixed 71: manual | p1 | p2 |
|---|---|---|---|---|---|---|
| `antrian` | 40 | 42 | 40 | 30 | 33 | 31 |
| `pelayanan_petugas` | 53 | 56 | 57 | 33 | 36 | 36 |
| `bbm_kosong` | 6 | 8 | 7 | 5 | 5 | 6 |
| `kualitas_bbm` | 3 | 2 | 2 | 2 | 1 | 1 |
| `takaran` | 5 | 5 | 5 | 4 | 4 | 4 |
| `pembayaran` | 21 | 22 | 21 | 14 | 15 | 14 |
| `harga` | 0 | 0 | 0 | 0 | 0 | 0 |
| `kebersihan` | 15 | 16 | 16 | 5 | 5 | 5 |
| `toilet` | 19 | 20 | 20 | 5 | 6 | 6 |
| `fasilitas` | 26 | 27 | 26 | 4 | 5 | 5 |
| `keamanan_lalu_lintas` | 7 | 10 | 10 | 7 | 8 | 8 |
| `lainnya` | 7 | **29** | **7** | 6 | 12 | 7 |

| Agreement with manual (127 reviews) | p1 | p2 |
|---|---|---|
| Sentiment exact (neg / mixed / pos) | 125 | 124 |
| Positive versus not positive | 127 | 125 |
| Exact label set, all | 93 | 106 |
| Exact label set, neg/mixed (of 71) | 55 | 58 |
| Exact label set, ignoring `lainnya` | 110 | 108 |
| Micro precision / recall of labels | 0.84 / 0.98 | 0.92 / 0.97 |
| `lainnya` on positive reviews (manual: 1) | 17 | 0 |
| `lainnya` on neg/mixed reviews (manual: 6) | 12 | 7 |

Why p1 overused `lainnya`: the p1 category row listed "site size, operating hours" as `lainnya` and "labels are topics, not complaints" told the model to tag any remark, so descriptive or complimentary remarks (strategic location, a large site, 24-hour opening, grades or LPG on sale) got `lainnya`, often next to labels that already covered the review. The manual pass used it only for jerry-can use, spillage, a cramped site and one prayer-time remark. p2 restricts `lainnya` to a specific problem or remark no other category fits, bars it for general description, and says sentiment is unchanged by that rule. A first p2 draft without that sentiment sentence dropped sentiment agreement to 121 of 127 (positive versus not 123): reviews that complain about a small or narrow site read as pos. The sentence was added and the set relabelled; the table is that final p2.

What p2 does not fix: 6 of the 7 manual `lainnya` reviews are matched; `keamanan_lalu_lintas` stays at 10 against 7; ignoring `lainnya`, p2's exact label-set agreement is 2 reviews lower than p1's, and temperature 0 does not make reruns identical (2 of 127 sentiments differ between p1 and p2). No category other than `lainnya` moved by more than 3 reviews between p1 and p2. Against a single-reader draft, differences of 1 to 3 reviews per category are not meaningful; the `lainnya` gap (22 reviews) is.

State of the table: the counts above come from the offline p2 run (`gemini.label_reviews`, no BigQuery write). On 2026-10-14 the `reviews-poller` job was redeployed with p2 and a live label run replaced all 139 `gemini` rows with `gemini-3.8-flash/p2` (8 carry `lainnya`). Later the same day p3 was deployed and a label run replaced them again with 139 `gemini-3.8-flash/p3` rows (9 carry `lainnya`, 5 `bbm_kosong`); because reruns at temperature 0 are not identical, the stored rows can differ slightly from this table. The labeller MERGEs on `(review_key, method)`, so a new prompt version replaces the old rows rather than adding beside them; the Review themes panel reads one row per review (`gemini` over `manual`, latest `labeled_at`), so there is no double count either way. The p1 rows and their review text are kept in `out/complaints/2026-10-14/labels_before.json`.

## Validation against a human reviewer (2026-10-14, bead `.10.5.5`)

An Indonesian-speaking reviewer checked all 100 reviews of the stratified validation sample (`out/complaints/2026-10-10/validation_sample.csv`, 71 neg/mixed by the draft) and corrected 2 rows: an early closure with fuel available moved from `bbm_kosong` to `pelayanan_petugas`, and a toilet complaint that praised the other facilities gained `fasilitas` and became `mixed`. The reviewer's rule (Decision, reviewer, 2026-10-14) was then applied to one more row with the same situation. The result is the reference set (`validation_sample_reviewed.csv`, git-ignored): 57 neg, 14 mixed, 29 pos.

The reviewer saw the draft labels while checking, so agreement with the draft is inflated by anchoring: read the `manual` column as "the reviewer accepted the draft", not as an independent accuracy. Gemini was not shown to the reviewer, so its column is the fairer test, but it is not a holdout: the p3 rule for `bbm_kosong` versus `pelayanan_petugas` came from the corrections on these same 100 reviews. A clean accuracy figure needs a fresh sample of new reviews. Gemini is `gemini-3.8-flash/p3`, run after the rule change.

| Agreement with the reviewer (100 reviews) | `manual` draft | Gemini p3 |
|---|---|---|
| Sentiment exact | 99 | 96 |
| Positive versus not positive | 100 | 97 |
| Exact label set | 97 | 83 |
| Micro precision / recall of labels | 0.99 / 0.99 | 0.92 / 0.96 |

Gemini p3 per category against the reviewer (reviews carrying the label in the reference / Gemini extra / Gemini missed): `antrian` 34 / 2 / 2, `pelayanan_petugas` 44 / 4 / 1, `bbm_kosong` 4 / 2 / 1, `kualitas_bbm` 2 / 0 / 1, `takaran` 4 / 0 / 0, `pembayaran` 20 / 0 / 0, `kebersihan` 9 / 0 / 0, `toilet` 11 / 1 / 0, `fasilitas` 17 / 0 / 2, `keamanan_lalu_lintas` 7 / 2 / 0, `lainnya` 6 / 2 / 0, `harga` 0 / 0 / 0.

What this supports: Gemini p3 is good enough for the counts-only Review themes panel. Sentiment, which decides what counts as a complaint, matches in 96 of 100; payment, toilet, cleanliness and short-fill labels match almost exactly. Its errors are extra labels (13) more than missed ones (7); no category has more than 4 extra or 2 missed labels, and no category's count is off by more than 3 net. What it does not support: per-category rates at a single site, where n is a handful of reviews.

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
- One labeller, one pass; an Indonesian-speaking reviewer checked 100 of the 127 but saw the draft labels while doing so, so the check is anchored and the 27 unchecked reviews may still misread slang, regional words or sarcasm. The keyword baseline agrees with them by construction of the same reading, so agreement is not accuracy.
- Reviews are self-selected (customers with a complaint or a compliment) and fuel type, shift and date are often missing; claims such as short-filling or fuel contamination are unverified single-reviewer reports.
- 22 rating-only reviews and the bare "Ok" style reviews carry no topic; one 2014 review reads like an owner or staff post, so treat it as praise-only noise.
- Dates: 96 of 100 Indonesian reviews fall in the last 12 months, but no site has more than about 10 recent text reviews, so no trend, seasonal or shift-level claim is supported.
- What more data would change:
  - **GBP API** (full history, owner replies, about 3,500 to 5,500 reviews a year across the 10 sites per the feasibility doc): replaces the biased windows, allows real per-site rates, monthly counts and a 12-month comparison. Needs listing ownership; storage under the GBP 30-day rule likely means keeping labels and counts only.
  - **Contact Center 135 export**: SPBU-level complaint categories with resolution, a different (direct-complainant) population that can validate the taxonomy and the subsidised-fuel and staffing patterns.
  - **Months of daily polling** (`reviews-poller`): newest-5 daily builds a time series for new complaints; the snapshot table gives the review rate; mixed daily polling does not remove the relevance-window bias but dilutes it as `place_reviews` grows.
  - **Fresh human validation** on new reviews, labelled blind (no draft labels shown), for a non-anchored precision and recall that the p3 prompt was not tuned on.
