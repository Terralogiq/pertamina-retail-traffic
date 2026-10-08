# Reviews feasibility: 12 months of Google reviews and complaint types

Bead pertamina-retail-traffic-907.10.5. Research date 2026-10-08. Documentation research only: no Places call was made; one read-only `gcloud services list` on `gcp-coe-sandbox`. What the Place Details call returns today is in [places-test-fetch.md](places-test-fetch.md) and `places_job/places.py` (not repeated here).

## Bottom line

- Places API (New) returns at most 5 reviews per site, sorted by relevance, no sort option, no paging. It cannot give a 12-month set, ever. Today's data is about 50 reviews in total (5 x 10 sites), spread over 2023 to 2026.
- The only Google-sanctioned complete source is the Business Profile (GBP) API `reviews.list`. It needs a GBP owner or manager role on each of the 10 listings, and the listings may belong to SPBU dealers, not Pertamina. Ownership is the real gate, not the API approval.
- The only true 12-month, SPBU-level complaint source available without Google is a Pertamina Contact Center 135 export filtered by the 10 SPBU codes.
- Scraping Google Maps and third-party scraper APIs are out of scope.

## 1. Places API (New) Place Details

- Max 5 reviews, "sorted by relevance" ([Place resource reference](https://developers.google.com/maps/documentation/places/web-service/reference/rest/v1/places)). No sort parameter and no paging token in New. The migration guide's parameter table maps only `place_id`, `language`, `region` ([migrate details](https://developers.google.com/maps/documentation/places/web-service/legacy/migrate-details)); `reviews_sort` has no New equivalent.
- Review fields: `name` (stable review id, `places/<id>/reviews/<id>`, seen in our raw JSON), `publishTime` (RFC 3339), `relativePublishTimeDescription`, `rating`, `text`, `originalText`, `authorAttribution`, `visitDate`. So a 12-month filter is possible per review, but the 5-review window is the limit.
- Billing: `reviews` triggers Place Details Enterprise + Atmosphere ([data fields](https://developers.google.com/maps/documentation/places/web-service/data-fields)); the pricing page shows $40 per 1,000 events with 1,000 free per month ([pricing](https://developers.google.com/maps/billing-and-pricing/pricing)). The page text was read through a summarizer; confirm the figure in the Cloud console price list before budgeting.
- `reviewSummary` and `generativeSummary` were empty on 10/10 sites (places-test-fetch), so no Google-generated summary to lean on.

## 2. Legacy Place Details, `reviews_sort=newest`

- Legacy still documents `reviews_sort` = `most_relevant` (default) or `newest`, up to 5 reviews ([legacy details](https://developers.google.com/maps/documentation/places/web-service/legacy/details)).
- Status: "As of October 2026, Places API (Legacy) can no longer be enabled for new Google Cloud projects. Existing projects remain fully supported" ([choose-api](https://developers.google.com/maps/documentation/places/web-service/choose-api)). No discontinuation date found ([deprecations](https://developers.google.com/maps/deprecations) names none).
- Our project: `gcloud services list --enabled` on `gcp-coe-sandbox` shows `places.googleapis.com` and `areainsights.googleapis.com`, not `places-backend.googleapis.com` (legacy). `--available` lists legacy as DISABLED, so it is listed, but whether enabling still succeeds after the October 2026 cutoff is unverified. Enabling is a mutating call and was not attempted. Treat the newest-sort poll as unavailable until the orchestrator decides to test enabling.
- Billing assumption: use the New-API price ($40 per 1,000) as the upper bound. The legacy SKU list (Atmosphere Data $5 per 1,000) "only applies to customers that have a signed order form" ([legacy SKU pricing](https://developers.google.com/maps/billing-and-pricing/legacy-sku-pricing)), which we do not have.

## 3. Google Business Profile API

- `accounts.locations.reviews.list` (v4): `GET https://mybusiness.googleapis.com/v4/{accounts/*/locations/*}/reviews`; `pageSize` max 50, `pageToken`, `orderBy` (`updateTime desc` default); returns `reviews[]`, `averageRating`, `totalReviewCount`, `nextPageToken` ([reference](https://developers.google.com/my-business/reference/rest/v4/accounts.locations.reviews/list)). `batchGetReviews` covers several locations per call ([review data guide](https://developers.google.com/my-business/content/review-data)).
- Review resource: `reviewId`, `starRating`, `comment`, `createTime`, `updateTime`, `reviewer.displayName` (real name only if not anonymous), `reviewReply` with comment and state ([resource](https://developers.google.com/my-business/reference/rest/v4/accounts.locations.reviews)). Complete history per location, so 12 months is one paged read (about 1 to 250 calls for the whole set).
- Scopes: `https://www.googleapis.com/auth/business.manage`. Only valid for verified locations.
- Access ([prerequisites](https://developers.google.com/my-business/content/prereqs)): Cloud project, access request via the GBP API contact form ("Application for Basic API Access"), applicant manages a GBP verified and active for 60+ days with a website, project number supplied. Quota shows 0 QPM until approved, then 300 QPM ([limits](https://developers.google.com/my-business/content/limits)). Third-party reports put approval at days to a few weeks (not an official figure). No sandbox.
- Policy ([policies](https://developers.google.com/my-business/content/policies)): use only to "create, manage, and report on business listings that you either own or are authorized to manage"; agencies follow third-party rules (notify client of changes, 7-business-day disassociation); no sharing of one approved project with third parties to avoid their own application.
- **Storage rule, separate from the Maps waiver**: content "must be stored temporarily for no more than 30 calendar days" and "you cannot pre-fetch, cache, index, or store" API content. The waiver in `.claude/rules/data-sources.md` covers Maps Platform ToS for Routes, Weather and Places; it does not mention GBP. Because `reviews.list` returns the full history on demand, the design can re-fetch and keep only derived labels and aggregates (section 8). Whether stored per-review labels count as "content" is a question for Google or Pertamina legal.
- Locations: `accounts.locations.list` supports filtering by place id and store code; a wildcard account (`-`) includes locations managed indirectly through a group ([location data](https://developers.google.com/my-business/content/location-data)). A location group or organization account can hold the 10 SPBU.
- Ownership: SPBU are largely dealer-operated, so the 10 listings may be owned by individual dealers, by Pertamina Patra Niaga centrally, or unclaimed. Not verified from docs; ask (section 7). A manual check per listing is legitimate: open it in Google Maps signed in as the candidate owner and look for "Manage this profile" versus "Claim this business".

## 4. Volume, polling coverage and cost (assumption-based)

- Lifetime `userRatingCount` from the 2026-10-06 fetch (local raw files): 446, 1,168, 1,655, 2,875, 12,107, 3,391, 2,175, 2,369, 2,263, 526; total about 29,000. The brief assumed "100s to 1,600"; actual range is 446 to 12,107 (site 5, toll rest area).
- Listing age is unknown, so the monthly rate cannot be derived. As an assumption only: if listings average 8 to 10 years on Maps, about 5 per month at site 1 and 100+ per month at site 5, roughly 300 to 450 per month over the 10, so 3,500 to 5,500 reviews in 12 months. Measure instead: poll for two weeks and count new review `name` ids.
- Polling coverage is capped at 5 reviews per poll. Daily polling of the newest 5 covers up to about 150 per month per site: enough for most sites, likely not for site 5. Weekly covers about 22 per month per site: only the quietest sites.
- Cost (New API upper bound, $40 per 1,000, 1,000 free per month): 10 sites x 30 daily polls = 300 calls per month, inside the free cap, about $0. Four polls per day = 1,200 calls, about $8 per month. Cost is not the constraint; coverage is.
- Going forward a daily poll via New API is not possible (relevance sort, same 5 returned); only legacy `newest` or GBP gives a newest-first view.

## 5. Other sources

- Pertamina Contact Center 135 (also pcc135@pertamina.com, Instagram DM @pertamina.135 per [Metro TV](https://www.metrotvnews.com/read/bw6Cgmm0-pertamina-patra-niaga-masif-siagakan-layanan-dan-kualitas-bbm-pastikan-penanganan-terukur-dan-sesuai-prosedur)) logs complaints by SPBU. An export is the best 12-month complaint set, with category, SPBU code, date, resolution. Needs Pertamina to release it; personal data must be stripped on their side.
- MyPertamina app-store reviews: about the app (payment, subsidy registration), not station service. Low value; at most a payment-complaint cross-check.
- Third-party Google-review APIs (SerpApi, Outscraper, Bright Data and similar) extract from Google Maps. Google Maps Platform terms bar scraping reviews, and Google filed suit against SerpApi in December 2025 ([Proxyway](https://proxyway.com/news/google-sues-serpapi)). Out of scope; do not use. Reputation platforms (Birdeye, Yext and similar) read reviews through the GBP API, so they need the same listing authorisation; if Pertamina or a dealer already uses one, ask for an export from it.

## 6. Comparison

| Option | 12-month coverage | Cost | Access needed | Effort | Risk |
|---|---|---|---|---|---|
| Places New, today | No: 5 relevance-sorted per site, about 50 total, 2023 to 2026 | $40 per 1,000 calls; 10 calls inside free cap | None, already working | Done | Anecdotal only; keep as a sample |
| Legacy Details `newest`, polled | Forward only; 5 per poll, overflows at big sites | About $0 to $8 per month | Legacy API enabled in project (DISABLED now; may be blocked after Oct 2026) | Low if enabling works | Platform in legacy status; unverified |
| GBP API `reviews.list` | Yes, full history, with replies | Free | Owner or manager on each listing; approved GBP project (60+ day verified profile, website); Pertamina or dealer grant | Medium: approval wait plus OAuth, small client | Ownership may sit with dealers; 30-day storage rule, store derived labels only |
| Pertamina 135 export | Yes if they provide 12 months, by SPBU | Free | Pertamina data release | Low for us, unknown for them | Different population (direct complainants); personal data |
| Third-party scraper APIs | Technically yes | Per-call fees | None | Low | Violates Maps ToS; litigation; excluded |

## 7. Recommendation and asks for Pertamina

1. Ask Pertamina for the Contact Center 135 export and for GBP access in parallel.
2. If listings are owned or manageable by Pertamina: get manager role for the 10 listings (location group), Terralogiq applies for its own GBP API access (own project, own verified profile; do not reuse a client project), then one-off `reviews.list` backfill plus a daily newest poll. Keep per-review text under 30 days, retain labels and aggregates.
3. If not: ask the dealers/Pertamina for a one-off review export from the owner UI or from an existing reputation tool; fall back to Places New 5-review samples as illustrative only. Optionally ask the orchestrator to test enabling legacy Places in `gcp-coe-sandbox` for a newest-sort forward poll.

Asks:
- Per SPBU (the 10 in `data/sites.csv`): ownership model (Pertamina-operated or dealer), and who holds the GBP owner role today.
- A manager invitation on each listing (or on a location group) to a Terralogiq-controlled Google account, in writing, with their legal view on the GBP storage and reporting rules.
- Contact Center 135 export, 12 months, those 10 SPBU codes: date, category, sub-category, free-text complaint, status. No names or phone numbers.
- Whether Pertamina or a dealer already uses a reputation-management tool and can export from it.
- Pertamina's own complaint taxonomy, to align labels with their reporting.

## 8. Analysis design

- Input table: site id, review id (GBP `reviewId` or Places `name`), rating, publish time, language, text. Drop author name, profile photo, review URL before analysis; `places.py::_review` currently carries `author_name`, so the analysis view should omit it. Mask phone numbers, plate numbers and personal names in text with regex before any model call.
- Filter: 12 months by publish time; rating of 1 to 3 as the primary complaint population, but classify all reviews, since 4 to 5 star text often carries a complaint.
- Taxonomy (multi-label, Indonesian; a draft to validate on a sample): `antrian` (queue, wait), `pelayanan_petugas` (staff attitude, speed), `bbm_kosong` (fuel out, grade unavailable), `kualitas_bbm` (water, "oplosan", engine trouble), `takaran` (short measure, pump not reset to zero), `pembayaran` (QRIS, EDC, card, cash only, change), `harga`, `kebersihan`, `toilet`, `fasilitas` (musholla, ATM, minimarket, parking, access), `keamanan_lalu_lintas`, `lainnya`, plus a `praise_only` flag.
- Method: LLM zero-shot with the fixed taxonomy and a JSON schema output (Gemini on Vertex AI keeps data in-project), temperature 0, pinned model version, definitions plus 2 to 3 Indonesian examples per label. Volume is small (3,500 to 5,500 reviews, short texts), so cost is trivial. Compare against a keyword rule baseline (stemmed Indonesian terms per label) as a sanity check and cheap fallback.
- Evaluation: hand-label a stratified 100-review sample (by site and star) with an Indonesian speaker; report per-label precision and recall for LLM and keyword methods, and agreement between the two. Re-check after any prompt or model change.
- Output: per-site, per-month counts per label and share of reviews, and rating trend. Store labels and counts, not text, beyond 30 days if sourced from GBP; Places-sourced text falls under the Places waiver.

## Open questions

- Who owns the 10 listings? Can the GBP route work without dealer consent?
- Does storing per-review labels from GBP content breach the 30-day rule? Needs Google or Pertamina legal.
- Can legacy Places still be enabled on `gcp-coe-sandbox`? Orchestrator decision; not tested.
- Real monthly review rate per site (unmeasured; two-week poll or GBP `totalReviewCount` over time would settle it).
- Will Pertamina release a 135 export, and at what granularity?
