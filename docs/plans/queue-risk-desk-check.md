# Desk check of the approach legs (queue-risk validation step 1)

Validation step 1 from [queue-risk.md](queue-risk.md), done 2026-10-21 against the 14-day levels in that plan's "14-day rerun" section. Sources: Street View Static (metadata first), Maps Static satellite tiles at zoom 19–20, and Places API (New) Nearby Search for transit within 200 m of the Front point. Leg geometry comes from `traffic.routes` (active rows, read-only). Script: `scripts/streetview_desk_check.py`. Images are in the session scratchpad, not the repo.

The rule from the plan: no signal or U-turn gap within about 150 m before the Front point. If there is one, the site drops to very low.

Distances are along the approach leg, measured back from the Front point (the approach leg's destination). They are read from Street View positions and the 25 m and 50 m markers on the satellite tiles, so they are accurate to about ±15 m.

## In brief

| Site | Verdict | Level now (14-day) | Proposed |
|---|---|---|---|
| Pemogan 54.801.17 | **Drops to very low**: a vehicle-facing signal head at about 60–70 m | Medium | Very low (see the note on the 13–17 Oct spell) |
| MT Haryono 61.761.03 | **Passes**, narrowly: no signal seen; the median ends at a crossroads about 150–165 m out | Low | Low (no change) |
| Makassar 74.902.22 | **Drops to very low**: signalised junction from about 30 m before Front | Low | Very low |
| Lingkar Selatan 34.121.03 | **Passes**: no signal or U-turn gap; frontage road with a bus stop at 80 m | Low | Low (no change) |
| Gayungan 54.601.80 | **Passes**: nothing within 200 m that slows the through lanes | Medium (that the road is not slowed) | No change |

Proposed reason text for the two changes:

- Pemogan, very low: "A signal over the kerb lane about 65 m before the station, plus a bus stop at 52 m, can slow this road on their own."
- Makassar, very low: "A signalised junction starts about 30 m before the station, so a red light alone slows this road."

**Applied 2026-10-21.** Makassar drops to very low, as proposed. Pemogan is held at **medium** and its verdict becomes **inconclusive**, for two reasons. The head is a two-lamp unit, which is not a three-aspect vehicle signal and in Indonesia is usually a flashing-amber warning or a pedestrian signal. And on ordinary weekdays the approach ran at about 10 s median (12, 19 and 20 Oct), which a working vehicle signal 65 m out would not allow. The rule drops a site when a signal could explain the pattern. Here the data on those weekdays argues that this one does not. Next step: check that the head is in service and what it shows (site staff or a newer capture). If it is a vehicle signal, Pemogan drops to very low. Gayungan's reason takes the geometry finding.

## Pemogan, Denpasar (Jl. By Pass Ngurah Rai)

Imagery: all 2025-06 (16 months old) on both legs. Pano offsets 1–5 m. Satellite capture date not given (tile credit only).

The approach is the eastbound carriageway of a divided bypass: two lanes, a raised kerbed median with planting, and the station on the left.

| Before Front | Feature |
|---|---|
| 250–160 m | Parallel side lane on the left behind a guardrail. Through lanes stay at two |
| ~150–160 m | Side-road junction on the left (SPBU side), with a yellow warning diamond and a blue pedestrian-crossing sign. Road markings not checked |
| ~60–70 m | **Signal head**: a vertical two-lamp head on a yellow cantilever over the kerb lane, facing eastbound traffic (`x_approach_075_f15_p14_h-12.jpg`). Unlit in the capture. It stands at the PT HM Sampoerna gate and an access road north |
| 52 m | Kepaon bus stop (Places `bus_stop`, 8 m off the leg, SPBU side). A red kerb-lane box with white lettering at about 40–55 m reads as the bus-stop marking. A truck and a minibus are stopped in it in the 2025-06 imagery. Large minibus and bus yard behind it, north of the Front point |
| 40–0 m | Continuous median, no gap. Station pylon (54.801.17) visible at 10 m |

Departure (contrast): a putaran balik sign on the median about 80–100 m after the Front point, so the U-turn gap is on the departure leg. Otherwise two free lanes and a continuous median to 250 m.

**Verdict: drops to very low.** A vehicle-facing signal head over the carriageway within 150 m meets the rule's word "signal". Most likely it is a pedestrian or crossing signal at the Sampoerna gate, not a junction signal. I could not confirm that it shows red to vehicles or that it is still in service: the imagery is 16 months old and the head is dark. The bus stop at 52 m, the factory gate and the bus yard all generate stopping and turning traffic in the kerb lane, on weekday mornings especially.

Note for the ranking: a fixed signal or bus stop does not explain the 13–17 Oct spell, when the approach ran 36–75 s slow for whole days while the departure stayed near 10 s, and then stopped. Those features do explain the mild base, the weekday 08:00 busy hour. The rule therefore takes Pemogan out of the evidence for a recurring station effect. It does not explain the spell, which stays the first ask for transaction counts and supply or closure logs (`.10.17`).

## MT Haryono, Balikpapan (Jl. MT Haryono)

Imagery: mixed. 2026-09 (1 month old) at 400–320 m, 250 m, 160 m and 120 m. 2025-07 (15 months old) at 480 m, 200 m and 80–10 m. Departure is 2025-07 and 2025-08. Pano offsets 2–6 m.

The approach runs south-west. From the start of the leg to about 165 m out, the road is divided by a narrow median. After that it is an undivided four-lane road with shops on both sides and the station on the left.

| Before Front | Feature |
|---|---|
| ~350–170 m | Divided section. Vehicles line the SPBU-side kerb in the satellite tile |
| ~150–165 m | The median ends at the crossroads with Jl. Penegak (left) and Jl. Penggalang (right). Turning, U-turns included, is possible there. It is an open junction, not a marked putaran balik |
| ~125–135 m | Zebra crossing (seen from 160 m, 2026-09) |
| 150–0 m | Kerbside parking along the SPBU side in the satellite tile |
| ~40–45 m | Zebra crossing with a red-painted strip beyond it (`x_approach_045_f80_p-25_h0.jpg`). No signal heads on poles or over the road, here or at the junction ahead (`x_approach_070_f60_p8_h0.jpg`) |
| ~0 m | Jl. Pramuka joins from the right at the Front point. An orange plastic barrier sits at the station mouth at 10 m. Vehicles beside it face the camera, which reads as traffic leaving the forecourt, not a median opening |

Places: no bus stop within 200 m. The one hit is a "Dipo Kereta Api" transit depot 66 m off the leg, which is not a stop on this road.

Departure (contrast): shops and an Alfamart in the first 20 m, and a concrete median barrier from about 150 m. No signal or U-turn gap was seen.

**Verdict: passes, narrowly.** I found no signal. The only place to turn across is the median end at about 150–165 m, which sits at the edge of the rule's window and is a junction, not a U-turn gap. The leg still has several sources of 20–40 s friction: two zebra crossings (≈130 m and ≈40 m), kerbside parking, right turns into Jl. Pramuka at the Front point, and the 150 m crossroads. Its delays are about 30 s, so these fit as well as station demand does. Level stays **low**. The evening and weekend timing (19:00–22:00) remains the point in its favour.

## Makassar (Jl. Perintis Kemerdekaan)

Imagery: 2026-01 (9 months old) over the last 200 m, 2026-02 (8 months old) further back. Pano offsets 0–5 m.

The approach runs west on a divided national road. The Front point lies inside the junction with Jl. Pintu I, the main Universitas Hasanuddin gate.

| Before Front | Feature |
|---|---|
| ~400–450 m | Junction with Jl. P. Kemerdekaan VIII (right) |
| ~200 m | Two yellow "traffic signal ahead" warning signs on the left |
| 173 m | Bus stop (Places `bus_stop`, "Pimpinan Wilayah Muhammadiyah", 9 m off the leg, SPBU side) |
| ~30 m to Front | **Signalised junction.** Its east edge, and so the westbound stop line, is about 30 m before Front (satellite, `x_sat_040_z20.png`). Mast-arm signal heads and a pole-mounted head showing red are visible from 80 m (`x_approach_080_f35_p8_h0.jpg`). The stop line itself was not resolved |
| ~25 m | Station turn-in: a wide open apron directly off the main road on the left (`x_approach_025_f90_p0_h-75.jpg`). The forecourt is reached from Jl. Perintis Kemerdekaan, not via Jl. Pintu I |
| +5 m | Bus stop "Taman Danau Universitas Hasanuddin" on the far side, 30 m off the leg |

**Verdict: drops to very low.** A signal with its stop line inside the last 30 m means a red phase holds the approach and releases the departure. That alone produces approach-slow, departure-free slots. It also fits this site's corridor-like profile (both legs slow 42% of slots) and its mild delays, none over a minute.

Leg-placement note, not corrected: the Front point sits inside the junction, so the end of the approach overlaps the signal's storage, and the start of the departure is the junction exit. A third leg ending before the stop line would not separate the station from the signal either, because the turn-in is at about 25 m.

## Lingkar Selatan, Jakarta Selatan (Jl. TB Simatupang)

Imagery: 2026-07 (3 months old) everywhere except 320 m and 250 m, which are 2023-12 (34 months old). Pano offsets 0–5 m.

The approach runs west on the southern frontage road of TB Simatupang. Kerbed, tree-lined separators keep it apart from the arterial lanes and the JORR toll. It is two narrow lanes with the station on the left.

| Before Front | Feature |
|---|---|
| ~200–280 m | Merge: gore and chevron hatching where traffic from the arterial joins the frontage road (`sat_250.png`) |
| ~100–110 m | Side road joins from the left (SPBU side) |
| ~75 m | Pedestrian footbridge over the whole corridor |
| 80 m | Halte Jaha bus stop at the kerb, SPBU side (Places `bus_stop`, 2 m off the leg), with a red-painted bus bay in the kerb lane. A second stop, Al Mahbubiyah, 61 m off the leg, is on the far side |
| ~15–30 m | Kerb drops to a side road or the station entry on the left. Station pylon at 10 m, forecourt raised above the road |

No signal was seen. The separators allow no U-turn.

**Verdict: passes.** Without a signal or U-turn gap, the rule leaves it at **low**. The bus bay at 80 m on a two-lane frontage road, and the arterial merge at about 200–280 m, are strong alternatives for a weekday-evening, commute-shaped slowdown with about 25 s of delay. They fit that shape better than fuel demand does.

## Gayungan, Surabaya (Jl. Ahmad Yani)

Imagery: 2026-03 (7 months old) except 250 m, which is 2021-01 (69 months old). Pano offsets 0–4 m, so the leg and the panos are on the same carriageway.

The approach runs north on the western carriageway of Jl. Ahmad Yani. It is one-way, has four marked lanes plus a kerb lane separated by a solid white line, and is divided from the next carriageway by a wide tree-planted median. The satellite tiles show further carriageways east of that median. This fits the western frontage road of A. Yani, but I have not confirmed which carriageway carries the main through traffic.

| Before Front | Feature |
|---|---|
| ~450–250 m | Side roads on the left: Jl. Gayungan I (~450 m), Gayungan II (~400 m, with a bus-stop icon on the basemap near it), Gayungan PTT (~250 m) |
| 200–40 m | No signal, crossing, bus stop or median gap. Wide paved apron and footway, about 8–10 m, between the kerb and the buildings on the SPBU side |
| ~25–30 m | Jl. Gayungan III joins from the left. The station canopy is on the far corner, and motorcycles turn in here (`x_approach_030_f90_p-10_h-35.jpg`) |
| 0 m | Station pylon. Wide open apron at the corner |

Places: no transit within 200 m.

**Verdict: passes.** There is nothing within 200 m that would slow the through lanes.

**What the geometry supports.** The reviews describe motorcycles waiting for Pertalite out onto Jl. Ahmad Yani. On this road that line can sit in three places without touching the four through lanes: the kerb lane behind its solid line, the wide apron, and the mouth of Jl. Gayungan III, which is where the station is entered. Probe speeds come from the through lanes, so they barely move. This is the "sits on the shoulder" explanation in the plan, and the geometry favours it over the other two (spills shorter than a slot, or days outside the window). No level change. Tightened reason text: "Four through lanes, a separate kerb lane, a wide apron and a side-road entry let roadside waiting happen without slowing through traffic."

## Limits

- Street View is one moment, 1–69 months old. A signal can be added, removed or switched to flashing since the capture. Pemogan's signal head is dark in its only capture.
- Distances are about ±15 m. Stop lines were not resolved at Makassar or Pemogan.
- "Signal" in the rule does not separate a junction signal from a pedestrian signal. Pemogan's verdict rests on that reading.
- Places transit coverage is incomplete: angkot stops are mostly informal and unmapped. None was seen in the imagery at the four ranked sites, but a stopping point leaves no fixed trace.
- Only the last ~200 m was imaged densely (every 40–50 m). The remainder was imaged every 70–80 m, plus satellite tiles.

## Requests

| API | Calls | Note |
|---|---|---|
| Street View metadata | 89 | Free. One call before the APIs were enabled was denied. One call mid-run (Pemogan, 120 m) returned `REQUEST_DENIED` and succeeded on re-fetch. The error text was not captured, which is consistent with the API still propagating after enablement. The script now records `error_message` |
| Street View Static image | 77 | 58 grid images plus 19 targeted zoom shots |
| Maps Static (satellite or hybrid) | 24 | 4 per site from the script, plus 4 at zoom 20 |
| Places Nearby Search (New) | 6 | Transit types, 200 m around each Front point |
| BigQuery | read-only | `traffic.routes` active legs |

## Reproduce

```bash
python3 scripts/streetview_desk_check.py --out <scratch dir>
```

It writes per-site Street View images at 480–10 m before Front, departure images for Pemogan and MT Haryono, three zoom-19 satellite tiles and a zoom-17 hybrid overview (marker k sits k × 50 m before Front), and `transit_nearby.json` with each stop's position along the leg and its side. It also writes `manifest.json`, with pano id, capture date, age and offset per image, and `calls.json`. The zoom shots cited above were ad hoc calls using the same endpoints.
