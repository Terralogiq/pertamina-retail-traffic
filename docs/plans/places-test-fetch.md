# Places test fetch

Run date: 2026-10-06. Script: `scripts/places_test_fetch.py`. Anchor: `place_id` from `data/sites.csv` only.
Raw responses are in gitignored `out/places_test/<date>/`; this file holds derived aggregates only (no review text, authors, ratings, photos or coordinates).

## Calls

| API | Calls this run |
|---|---|
| Place Details | 10 |
| Nearby Search (1 km, 3 km) | 20 |
| Places Aggregate (type x radius) | 450 |
| Retries on 429/5xx/network | 0 |
| Calls ending in non-200 | 0 |

## Place Details fill rate (sites with non-empty field, of 10)

| Field | Fill |
|---|---|
| id | 10/10 |
| displayName | 10/10 |
| formattedAddress | 10/10 |
| shortFormattedAddress | 10/10 |
| addressComponents | 10/10 |
| location | 10/10 |
| plusCode | 9/10 |
| businessStatus | 10/10 |
| types | 10/10 |
| primaryType | 10/10 |
| rating | 10/10 |
| userRatingCount | 10/10 |
| reviews | 10/10 |
| googleMapsUri | 10/10 |
| regularOpeningHours | 10/10 |
| currentOpeningHours | 10/10 |
| nationalPhoneNumber | 7/10 |
| websiteUri | 5/10 |
| fuelOptions | 0/10 |
| evChargeOptions | 0/10 |
| paymentOptions | 9/10 |
| parkingOptions | 0/10 |
| accessibilityOptions | 10/10 |
| restroom | 10/10 |
| goodForChildren | 0/10 |
| allowsDogs | 8/10 |
| servesCoffee | 0/10 |
| takeout | 0/10 |
| delivery | 0/10 |
| dineIn | 0/10 |
| priceLevel | 0/10 |
| editorialSummary | 0/10 |
| generativeSummary | 0/10 |
| reviewSummary | 0/10 |
| photos | 10/10 |
| utcOffsetMinutes | 10/10 |

A boolean `false` counts as present. Nearby Search `fuelOptions` present on 0/240 returned gas stations (all radii, all sites).

## Sites

| # | place_id | city | businessStatus | primaryType | reviews returned | review languages | road matches |
|---|---|---|---|---|---|---|---|
| 1 | `ChIJOev7BHzcQC4RkTJHeDJS8PQ` | Bandar Lampung | OPERATIONAL | gas_station | 5 | id | yes |
| 2 | `ChIJJXEjFwnbQC4RBlHwmDTzc3w` | Bandar Lampung | OPERATIONAL | gas_station | 5 | id | yes |
| 3 | `ChIJ_Yu4YvnxaS4RSq9CZVDfahU` | Jakarta Selatan | OPERATIONAL | gas_station | 5 | id | yes |
| 4 | `ChIJyxrzOer3aS4RroaX8C20SCk` | Jakarta Barat | OPERATIONAL | gas_station | 5 | id | yes |
| 5 | `ChIJxyd2_yF0aS4Rke2QWUFK2lQ` | Karawang | OPERATIONAL | gas_station | 5 | id | yes |
| 6 | `ChIJ1W0orWTmaC4RoY3QEG4SQhQ` | Bandung | OPERATIONAL | gas_station | 5 | id | yes |
| 7 | `ChIJdbnAi0T71y0RK8RxR-5wLqk` | Surabaya | OPERATIONAL | gas_station | 5 | id | yes |
| 8 | `ChIJnV_l7-5G8S0RR5u6DitfPus` | Balikpapan | OPERATIONAL | gas_station | 5 | id | no route |
| 9 | `ChIJawRf9Urjvi0RnmY2YouCcAA` | Makassar | OPERATIONAL | gas_station | 5 | id | yes |
| 10 | `ChIJT8-a6kVB0i0RpAsgjpVtcRQ` | Denpasar | OPERATIONAL | gas_station | 5 | id | yes |

Road check: loose token overlap between the `road` column and the `route` address component. Flags need human review.
- Site 8: sites.csv road `Jl. MT Haryono`; no route component.

## Competitors (gas_station, Nearby Search, DISTANCE rank, max 20, site excluded)

Brand derived from displayName (Pertamina incl. SPBU codes like `NN.NNN.NN`, Shell, BP, Vivo, other). `*` = result hit the 20 cap, so the count is a lower bound.

### 1 km

| # | Pertamina | Shell | BP | Vivo | other | total |
|---|---|---|---|---|---|---|
| 1 | 0 | 0 | 0 | 0 | 1 | 1 |
| 2 | 1 | 0 | 0 | 0 | 1 | 2 |
| 3 | 1 | 0 | 2 | 0 | 4 | 7 |
| 4 | 0 | 0 | 0 | 0 | 7 | 7 |
| 5 | 1 | 0 | 0 | 0 | 5 | 6 |
| 6 | 3 | 1 | 0 | 1 | 4 | 9 |
| 7 | 0 | 1 | 0 | 0 | 3 | 4 |
| 8 | 0 | 0 | 0 | 0 | 2 | 2 |
| 9 | 0 | 0 | 0 | 0 | 1 | 1 |
| 10 | 1 | 0 | 0 | 0 | 2 | 3 |

### 3 km

| # | Pertamina | Shell | BP | Vivo | other | total |
|---|---|---|---|---|---|---|
| 1 | 4 | 0 | 0 | 0 | 8 | 12 |
| 2 | 6 | 0 | 0 | 0 | 13 | 19* |
| 3 | 5 | 2 | 3 | 1 | 8 | 19* |
| 4 | 1 | 1 | 0 | 0 | 17 | 19* |
| 5 | 2 | 0 | 0 | 0 | 17 | 19* |
| 6 | 6 | 1 | 0 | 1 | 11 | 19* |
| 7 | 4 | 1 | 1 | 0 | 13 | 19* |
| 8 | 6 | 0 | 0 | 0 | 13 | 19* |
| 9 | 7 | 0 | 0 | 0 | 7 | 14 |
| 10 | 13 | 0 | 0 | 0 | 6 | 19* |

## POI counts (Places Aggregate, operational; counts at 500 m / 1 km / 3 km)

| # | restaurant | cafe | convenience_store | supermarket | shopping_mall | school | university | hospital | bank | atm | lodging | car_repair | car_wash | electric_vehicle_charging_station | gas_station |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 28/84/1030 | 4/21/245 | 3/10/100 | 2/7/76 | 7/17/149 | 4/14/152 | 0/0/10 | 0/0/6 | 1/4/21 | 1/1/31 | 6/25/430 | 9/30/287 | 1/2/26 | 0/0/1 | 1/2/13 |
| 2 | 163/468/4683 | 36/111/1209 | 18/67/532 | 6/25/221 | 16/52/556 | 12/49/514 | 1/6/63 | 0/3/90 | 19/26/154 | 18/39/228 | 63/166/1513 | 48/151/1056 | 3/8/99 | 0/0/2 | 1/3/31 |
| 3 | 156/577/6405 | 59/209/2080 | 12/41/310 | 7/17/184 | 5/22/242 | 19/48/492 | 8/13/120 | 1/11/98 | 11/29/250 | 27/54/505 | 83/339/2559 | 13/49/861 | 1/3/65 | 2/7/41 | 4/8/53 |
| 4 | 144/673/7628 | 40/244/2516 | 6/51/526 | 2/26/308 | 12/65/518 | 13/64/572 | 1/7/57 | 1/4/62 | 1/13/184 | 0/22/341 | 42/150/1836 | 33/142/1434 | 1/4/61 | 0/0/15 | 4/8/69 |
| 5 | 72/204/2163 | 24/98/680 | 7/22/138 | 4/12/137 | 2/18/246 | 2/20/221 | 0/2/10 | 0/1/12 | 3/3/45 | 4/10/62 | 4/29/358 | 20/74/479 | 2/7/61 | 3/4/5 | 2/7/56 |
| 6 | 303/1159/9167 | 79/323/2832 | 12/65/566 | 4/21/260 | 27/63/440 | 19/79/657 | 3/16/261 | 11/17/148 | 13/30/323 | 25/64/535 | 94/469/5339 | 42/152/1264 | 4/10/114 | 1/2/21 | 6/10/59 |
| 7 | 194/712/6006 | 108/309/2952 | 12/41/451 | 7/24/207 | 4/18/234 | 15/54/423 | 1/20/179 | 2/6/75 | 11/28/207 | 23/45/349 | 99/292/2132 | 35/86/1000 | 3/10/103 | 1/1/4 | 3/5/40 |
| 8 | 161/476/2761 | 61/190/1111 | 12/34/178 | 3/12/96 | 5/38/210 | 12/44/271 | 1/10/32 | 1/1/20 | 5/37/165 | 10/35/164 | 93/281/1319 | 31/88/549 | 4/16/93 | 1/3/6 | 1/3/21 |
| 9 | 144/447/2364 | 89/229/1081 | 14/32/177 | 12/20/125 | 13/29/205 | 9/26/260 | 16/66/217 | 4/48/105 | 4/11/74 | 11/32/179 | 220/588/2735 | 17/40/338 | 4/8/44 | 0/0/0 | 2/2/15 |
| 10 | 95/338/4069 | 17/74/784 | 3/17/174 | 5/9/101 | 6/24/232 | 4/22/137 | 0/0/14 | 1/2/23 | 4/9/128 | 5/11/139 | 58/196/2400 | 18/44/579 | 4/7/65 | 1/1/2 | 2/4/23 |

## Invalid fields / types

- Aggregate: none of the 15 types was rejected.
- Place Details: all 36 requested fields accepted by the field mask (HTTP 200 for every site).

## Observations

- All 10 place_ids resolved (returned `id` equals the input) and all 10 are `businessStatus` OPERATIONAL, primaryType `gas_station`.
- Road check: 9/10 `route` components match the `road` column by loose token overlap (site 5 `Tol Jakarta-Cikampek KM 57 A` matches on the toll road name only; the KM / rest-area suffix is not in `route`). Site 8 has no `route` component at all (only admin levels, country, postal code), so its `Jl. MT Haryono` could not be verified from addressComponents. No outright mismatch found.
- `fuelOptions` is empty on 10/10 Place Details and on 0/240 Nearby Search gas stations. Fuel grades and prices cannot come from Places in Indonesia; `evChargeOptions` (0/10) and `parkingOptions` (0/10) are also empty. Treat Places as a profile source, not a fuel-price source.
- Empty on 10/10: `priceLevel`, `editorialSummary`, `generativeSummary`, `reviewSummary`, `servesCoffee`, `takeout`, `delivery`, `dineIn`, `goodForChildren`. These Atmosphere-tier fields are not worth requesting for SPBU.
- Reliably present: id, displayName, addresses, location, types, businessStatus, rating, userRatingCount, reviews, googleMapsUri, regular and current opening hours, `accessibilityOptions` (only `wheelchairAccessibleRestroom`), `restroom` (true on all 10), photos, utcOffsetMinutes. Patchy: `nationalPhoneNumber` 7/10, `websiteUri` 5/10, `paymentOptions` 9/10, `allowsDogs` 8/10, `plusCode` 9/10.
- Reviews: 5 returned per site (API maximum per call), all with `originalText.languageCode` = `id`. `languageCode=id` is therefore sufficient for review display; no translation noise seen in this sample.
- Nearby Search at 3 km hits the 20-result cap at 8/10 sites (19 competitors + the site itself), so 3 km competitor counts from Nearby are lower bounds. Use the Aggregate `gas_station` counts (13 to 69 at 3 km, includes the site itself) for density at that radius; Nearby remains useful for 1 km brand mix.
- Nearby results include non-station noise: 237/240 results have primaryType `gas_station`, but 23/240 are `Pertamini` / mini-pom informal retail units, and names such as `Pertamina Lubricants` or `Bensin eceran` also appear. Brand derivation by displayName counts `Pertamini` as other (it does not contain `pertamina`) and counts anything containing `pertamina` or an SPBU code pattern as Pertamina, so Pertamina counts include some non-SPBU entities. Names with neither brand nor code are `other`, so Pertamina is probably under-counted for unbranded SPBU names.
- Aggregate: all 15 type names were accepted (450/450 HTTP 200). Counts grow steeply with radius (restaurants 28 to 1030 at site 1) and big-city sites (3, 4, 6) have very dense 3 km POI counts, so 500 m / 1 km is the more discriminating profile radius. Aggregate `electric_vehicle_charging_station` is 0 to 3 within 500 m, up to 41 within 3 km (site 3).
- Aggregate `place` center (`places/<place_id>`) worked as documented, so no site coordinates were needed for Aggregate. Coordinates were used only at runtime for the Nearby Search circle.
- The `Calls` table is the original run (10 + 20 + 450). A later `--report-only` pass rebuilt this document from the raw files without calling the APIs.

### Site selection (Text Search, 2026-10-06)

Run in the session before this fetch: `places:searchText` with `languageCode=id`, `regionCode=ID` and `maxResultCount=6`, keeping `primaryType == gas_station`. Sites 1 and 2 were looked up by their client-provided SPBU code; sites 3–10 used the query `SPBU Pertamina <road> <city>` from `sites.md`. "Rank" is the position of the chosen place_id among the gas-station results. The choice was based on the sites.md criteria: the station sits directly on the named road, it is OPERATIONAL, and it has the most reviews among the candidates in the target city or regency.

| # | Query | Gas-station results | Rank of chosen |
|---|---|---|---|
| 1 | SPBU Pertamina 24.351.97 Bandar Lampung | 3 | 1 |
| 2 | SPBU Pertamina 24.351.34 Bandar Lampung | 1 | 1 |
| 3 | SPBU Pertamina Jl. TB Simatupang Jakarta Selatan | 6 | 3 |
| 4 | SPBU Pertamina Jl. Daan Mogot Jakarta Barat | 6 | 4 |
| 5 | SPBU Pertamina Rest Area KM 57 Tol Jakarta Cikampek | 1 | 1 |
| 6 | SPBU Pertamina Jl. Dr. Djunjunan Pasteur Bandung | 6 | 1 |
| 7 | SPBU Pertamina Jl. Ahmad Yani Surabaya | 1 | 1 |
| 8 | SPBU Pertamina Jl. MT Haryono Balikpapan | 5 | 1 |
| 9 | SPBU Pertamina Jl. Perintis Kemerdekaan Makassar | 6 | 2 |
| 10 | SPBU Pertamina Jl. By Pass Ngurah Rai Denpasar | 6 | 2 |

The user checked these on the map:
- Site 5 is on the Jakarta→Cikampek carriageway.
- Site 9 is on Jl. Perintis Kemerdekaan, opposite the UNHAS entrance.
