# Demo sites: 10 SPBU

Decided 2026-10-06. The client provided 2 sites; Terralogiq chose the other 8 to cover different city sizes and road types, so the dashboard can contrast traffic patterns (urban commute, weekend tourism, intercity, toll).

## Provided by the client

| # | SPBU | City | Coordinates | Maps |
|---|---|---|---|---|
| 1 | 24.351.97 | Bandar Lampung | -5.4103747, 105.3194629 | https://maps.app.goo.gl/uswuDgiNCqMQsjYW9 |
| 2 | 24.351.34 | Bandar Lampung | -5.4032507, 105.2818032 | https://maps.app.goo.gl/aKrvEk5Xtw7uBkuH6 |

The two are about 4 km apart in the same city: a provincial capital outside Java.

## Chosen by Terralogiq: city and road

| # | City | Road type | Road to search | Why |
|---|---|---|---|---|
| 3 | Jakarta Selatan | Congested arterial | Jl. TB Simatupang | Heavy morning and evening commute peaks |
| 4 | Jakarta Barat | Arterial | Jl. Daan Mogot | Commuter link to Tangerang; flood-prone, so it pairs well with the weather data |
| 5 | Jabodetabek toll | Toll rest area | Jakarta–Cikampek toll, rest area KM 57 | Intercity flow with holiday (mudik) peaks |
| 6 | Bandung | Arterial, gateway | Jl. Dr. Djunjunan (Pasteur) | Weekend tourist inflow from Jakarta |
| 7 | Surabaya | Arterial | Jl. Ahmad Yani | Second-largest city, main north–south route |
| 8 | Balikpapan | Arterial | Jl. MT Haryono | Mid-size city in Kalimantan; oil-industry hub |
| 9 | Makassar | National road, airport link | Jl. Perintis Kemerdekaan | Trans-Sulawesi route and airport access; largest city in eastern Indonesia |
| 10 | Denpasar | Bypass | Jl. By Pass Ngurah Rai | Tourism, outside Java |

Overall mix:
- Metro core: 3, 4
- Provincial or large city: 1, 2, 6, 7, 9
- Mid-size city: 8
- Intercity or airport link: 5, 9
- Outside Java (Sumatra, Kalimantan, Sulawesi, Bali): 1, 2, 8, 9, 10

## How each SPBU is picked

For sites 3–10, run a Places Text Search for `SPBU Pertamina <road> <city>`. Among the results, choose one that:
1. Sits directly on the named road, not on a side street.
2. Has a clear direction of travel on its side of the road, so two route segments (one per direction) can be pinned with a heading.
3. Has `businessStatus` OPERATIONAL and a decent number of reviews, which helps the Places panel.

Record the following in `traffic.sites`:
- the SPBU number (from the place name). Site 5's Places listing has no number, so it uses the surrogate `KM57A` until Pertamina confirms the real code.
- `place_id`: the anchor. `data/sites.csv` is the committed source and holds no coordinates.
- location, re-fetched from Place Details at least every 30 days (Places ToS limit on caching lat/lng)
- road name
- city

If no station on a road meets the criteria, choose another road with the same road type in the same city.
