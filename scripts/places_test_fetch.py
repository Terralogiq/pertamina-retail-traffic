#!/usr/bin/env python3
"""Profile the 10 SPBU sites with Places API (New) + Places Aggregate.

Anchor is place_id only (data/sites.csv). Coordinates are used at runtime
for the Nearby Search circle and never read from or written to a file other
than the gitignored raw responses under out/.

Outputs:
  out/places_test/<date>/site_<n>/{details,nearby_1000,nearby_3000,aggregate}.json
  out/places_test/<date>/fill_rate.csv
  out/places_test/<date>/summary.json   (derived aggregates, no Places content)
  docs/plans/places-test-fetch.md       (committed: derived aggregates only)

Usage: python3 scripts/places_test_fetch.py [--date YYYY-MM-DD] [--reuse]
  --reuse  skip API calls whose raw response file already exists
"""
import argparse
import csv
import datetime
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITES_CSV = os.path.join(ROOT, "data", "sites.csv")
DOC_PATH = os.path.join(ROOT, "docs", "plans", "places-test-fetch.md")

DETAILS_URL = "https://places.googleapis.com/v1/places/{}"
NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
AGG_URL = "https://areainsights.googleapis.com/v1:computeInsights"

DETAILS_FIELDS = [
    "id", "displayName", "formattedAddress", "shortFormattedAddress",
    "addressComponents", "location", "plusCode", "businessStatus", "types",
    "primaryType", "rating", "userRatingCount", "reviews", "googleMapsUri",
    "regularOpeningHours", "currentOpeningHours", "nationalPhoneNumber",
    "websiteUri", "fuelOptions", "evChargeOptions", "paymentOptions",
    "parkingOptions", "accessibilityOptions", "restroom", "goodForChildren",
    "allowsDogs", "servesCoffee", "takeout", "delivery", "dineIn",
    "priceLevel", "editorialSummary", "generativeSummary", "reviewSummary",
    "photos", "utcOffsetMinutes",
]
NEARBY_FIELDS = [
    "id", "displayName", "location", "primaryType", "rating",
    "userRatingCount", "businessStatus", "fuelOptions",
]
NEARBY_RADII = [1000, 3000]
AGG_RADII = [500, 1000, 3000]
AGG_TYPES = [
    "restaurant", "cafe", "convenience_store", "supermarket", "shopping_mall",
    "school", "university", "hospital", "bank", "atm", "lodging",
    "car_repair", "car_wash", "electric_vehicle_charging_station",
    "gas_station",
]
BRANDS = ["Pertamina", "Shell", "BP", "Vivo", "other"]

CALLS = {"details": 0, "nearby": 0, "aggregate": 0, "retries": 0, "errors": 0}


def get_api_key():
    key = os.environ.get("MAPS_API_KEY")
    if key:
        return key.strip()
    out = subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest",
         "--secret=MAPS_API_KEY", "--project=gcp-coe-sandbox",
         "--billing-project=gcp-coe-sandbox"],
        capture_output=True, text=True, check=True)
    return out.stdout.strip()


def http(method, url, key, mask=None, body=None, params=None):
    """Return (status, parsed_json). Retries on 429/5xx. Never logs the key."""
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    headers = {"X-Goog-Api-Key": key, "Content-Type": "application/json"}
    if mask:
        headers["X-Goog-FieldMask"] = mask
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(5):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            if e.code == 429 or e.code >= 500:
                CALLS["retries"] += 1
                time.sleep(min(2 ** attempt, 16))
                continue
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, {"error": {"message": raw[:500]}}
        except (urllib.error.URLError, TimeoutError):
            CALLS["retries"] += 1
            time.sleep(min(2 ** attempt, 16))
    return 599, {"error": {"message": "retries exhausted"}}


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def load(path):
    with open(path) as f:
        return json.load(f)


def non_empty(v):
    if v is None:
        return False
    if isinstance(v, (str, list, dict)):
        return len(v) > 0
    return True  # bool False / 0 are real values


def brand_of(name):
    n = (name or "").lower()
    if "pertamina" in n or "pertamax" in n or re.search(r"\b\d{2}[.\-]?\d{3}[.\-]?\d{2,3}\b", n):
        return "Pertamina"
    if "shell" in n:
        return "Shell"
    if re.search(r"\bbp\b", n) or n.startswith("bp-") or "bp akr" in n:
        return "BP"
    if "vivo" in n or "revvo" in n:
        return "Vivo"
    return "other"


def route_of(details):
    for c in details.get("addressComponents", []):
        if "route" in c.get("types", []):
            return c.get("longText") or c.get("shortText") or ""
    return ""


def norm_road(s):
    s = s.lower()
    s = re.sub(r"\b(jalan|jl)\b\.?", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\b(p|pangeran|dr|h|k\.?h)\b", " ", s)
    return " ".join(s.split())


def road_matches(csv_road, route):
    """Loose token-overlap check; flags are reviewed by a human."""
    a, b = set(norm_road(csv_road).split()), set(norm_road(route).split())
    if not a or not b:
        return False
    return len(a & b) / min(len(a), len(b)) >= 0.5


def fetch_site(site, key, outdir, reuse, invalid):
    n = site["site_no"]
    sdir = os.path.join(outdir, f"site_{n}")
    pid = site["place_id"]

    # 1. Place Details
    p = os.path.join(sdir, "details.json")
    if reuse and os.path.exists(p):
        details = load(p)
    else:
        CALLS["details"] += 1
        status, details = http(
            "GET", DETAILS_URL.format(pid), key,
            mask=",".join(DETAILS_FIELDS),
            params={"languageCode": "id", "regionCode": "ID"})
        if status != 200:
            CALLS["errors"] += 1
            print(f"  site {n} details HTTP {status}: {json.dumps(details)[:400]}")
            details = {"_error": details, "_status": status}
        save(p, details)
    loc = details.get("location") or {}
    if "latitude" not in loc:
        print(f"  site {n}: no location from details; skipping nearby")

    # 2. Nearby Search (location used at runtime only)
    for r in NEARBY_RADII:
        p = os.path.join(sdir, f"nearby_{r}.json")
        if reuse and os.path.exists(p):
            continue
        if "latitude" not in loc:
            continue
        CALLS["nearby"] += 1
        body = {
            "includedTypes": ["gas_station"],
            "maxResultCount": 20,
            "rankPreference": "DISTANCE",
            "languageCode": "id",
            "regionCode": "ID",
            "locationRestriction": {"circle": {
                "center": {"latitude": loc["latitude"], "longitude": loc["longitude"]},
                "radius": float(r)}},
        }
        status, resp = http(
            "POST", NEARBY_URL, key,
            mask=",".join("places." + f for f in NEARBY_FIELDS), body=body)
        if status != 200:
            CALLS["errors"] += 1
            print(f"  site {n} nearby_{r} HTTP {status}: {json.dumps(resp)[:400]}")
            resp = {"_error": resp, "_status": status}
        save(p, resp)

    # 3. Places Aggregate, anchored on place_id
    p = os.path.join(sdir, "aggregate.json")
    agg = load(p) if (reuse and os.path.exists(p)) else {}
    for t in AGG_TYPES:
        for r in AGG_RADII:
            k = f"{t}@{r}"
            if k in agg and "_error" not in agg[k]:
                continue
            CALLS["aggregate"] += 1
            body = {
                "insights": ["INSIGHT_COUNT"],
                "filter": {
                    "locationFilter": {"circle": {
                        "place": f"places/{pid}", "radius": r}},
                    "typeFilter": {"includedTypes": [t]},
                    "operatingStatus": ["OPERATING_STATUS_OPERATIONAL"],
                },
            }
            status, resp = http("POST", AGG_URL, key, body=body)
            if status != 200:
                CALLS["errors"] += 1
                msg = json.dumps(resp)[:300]
                invalid.setdefault(t, msg)
                resp = {"_error": resp, "_status": status}
            agg[k] = resp
    save(p, agg)
    return details


def nearby_stats(path, site_id):
    """Return (brand counts, total, capped) excluding the site itself."""
    if not os.path.exists(path):
        return None
    d = load(path)
    if "_error" in d:
        return None
    places = d.get("places", [])
    capped = len(places) >= 20
    counts = {b: 0 for b in BRANDS}
    total = 0
    for pl in places:
        if pl.get("id") == site_id:
            continue
        counts[brand_of((pl.get("displayName") or {}).get("text"))] += 1
        total += 1
    return counts, total, capped


def agg_count(resp):
    if resp is None or "_error" in resp:
        return None
    return int(resp.get("count", 0))


def build_report(sites, outdir, date, invalid_agg):
    """Compute derived aggregates from raw files; write csv/summary/doc."""
    details_by_site = {}
    for s in sites:
        p = os.path.join(outdir, f"site_{s['site_no']}", "details.json")
        details_by_site[s["site_no"]] = load(p) if os.path.exists(p) else {}

    for s in sites:
        ap = os.path.join(outdir, f"site_{s['site_no']}", "aggregate.json")
        if os.path.exists(ap):
            for k, v in load(ap).items():
                if "_error" in v:
                    invalid_agg.setdefault(k.split("@")[0], json.dumps(v["_error"])[:300])
    bad_details = [s["site_no"] for s in sites
                   if "_error" in details_by_site[s["site_no"]]]

    # Fill rate
    fill = {}
    for f in DETAILS_FIELDS:
        fill[f] = sum(1 for d in details_by_site.values()
                      if "_error" not in d and non_empty(d.get(f)))
    with open(os.path.join(outdir, "fill_rate.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["field", "sites_non_empty", "sites_total"])
        for f in DETAILS_FIELDS:
            w.writerow([f, fill[f], len(sites)])

    # Per-site facts
    rows = []
    for s in sites:
        n, pid = s["site_no"], s["place_id"]
        d = details_by_site[n]
        reviews = d.get("reviews", []) or []
        langs = sorted({(r.get("originalText") or {}).get("languageCode", "?")
                        for r in reviews})
        route = route_of(d)
        rows.append({
            "site_no": n, "place_id": pid, "city": s["city"], "road": s["road"],
            "status": d.get("businessStatus", "(missing)"),
            "primaryType": d.get("primaryType", "(missing)"),
            "route": route,
            "road_match": road_matches(s["road"], route) if route else None,
            "n_reviews": len(reviews), "review_langs": langs,
            "id_match": d.get("id") == pid,
            "nearby": {r: nearby_stats(os.path.join(
                outdir, f"site_{n}", f"nearby_{r}.json"), pid) for r in NEARBY_RADII},
            "agg": {},
        })
        ap = os.path.join(outdir, f"site_{n}", "aggregate.json")
        agg = load(ap) if os.path.exists(ap) else {}
        for t in AGG_TYPES:
            rows[-1]["agg"][t] = [agg_count(agg.get(f"{t}@{r}")) for r in AGG_RADII]

    # Nearby fuelOptions fill among competitors (counts only)
    nb_total = nb_fuel = 0
    for s in sites:
        for r in NEARBY_RADII:
            p = os.path.join(outdir, f"site_{s['site_no']}", f"nearby_{r}.json")
            if os.path.exists(p):
                for pl in load(p).get("places", []):
                    nb_total += 1
                    nb_fuel += non_empty(pl.get("fuelOptions"))

    summary = {
        "date": date, "calls": CALLS, "fill_rate": fill,
        "invalid_aggregate_types": invalid_agg,
        "nearby_fuel_options": [nb_fuel, nb_total],
        "sites": [{k: v for k, v in r.items()} for r in rows],
    }
    save(os.path.join(outdir, "summary.json"), summary)
    write_doc(sites, rows, fill, date, invalid_agg, nb_fuel, nb_total, bad_details)
    return rows, fill


def write_doc(sites, rows, fill, date, invalid_agg, nb_fuel, nb_total, bad_details):
    # Observations are hand-written after a run; keep them across regenerations.
    observations = "(filled in after the run)"
    if os.path.exists(DOC_PATH):
        with open(DOC_PATH) as f:
            old = f.read()
        marker = "## Observations\n\n"
        if marker in old:
            observations = old.split(marker, 1)[1].strip() or observations
    L = []
    a = L.append
    a("# Places test fetch")
    a("")
    a(f"Run date: {date}. Script: `scripts/places_test_fetch.py`. Anchor: `place_id` from `data/sites.csv` only.")
    a("Raw responses are in gitignored `out/places_test/<date>/`; this file holds derived aggregates only "
      "(no review text, authors, ratings, photos or coordinates).")
    a("")
    a("## Calls")
    a("")
    a("| API | Calls this run |")
    a("|---|---|")
    a(f"| Place Details | {CALLS['details']} |")
    a(f"| Nearby Search (1 km, 3 km) | {CALLS['nearby']} |")
    a(f"| Places Aggregate (type x radius) | {CALLS['aggregate']} |")
    a(f"| Retries on 429/5xx/network | {CALLS['retries']} |")
    a(f"| Calls ending in non-200 | {CALLS['errors']} |")
    a("")
    a("## Place Details fill rate (sites with non-empty field, of 10)")
    a("")
    a("| Field | Fill |")
    a("|---|---|")
    for f in DETAILS_FIELDS:
        a(f"| {f} | {fill[f]}/{len(sites)} |")
    a("")
    a("A boolean `false` counts as present. Nearby Search `fuelOptions` present on "
      f"{nb_fuel}/{nb_total} returned gas stations (all radii, all sites).")
    a("")
    a("## Sites")
    a("")
    a("| # | place_id | city | businessStatus | primaryType | reviews returned | review languages | road matches |")
    a("|---|---|---|---|---|---|---|---|")
    for r in rows:
        rm = {True: "yes", False: "**NO**", None: "no route"}[r["road_match"]]
        a(f"| {r['site_no']} | `{r['place_id']}` | {r['city']} | {r['status']} | {r['primaryType']} "
          f"| {r['n_reviews']} | {','.join(r['review_langs']) or '-'} | {rm} |")
    a("")
    a("Road check: loose token overlap between the `road` column and the `route` address component. Flags need human review.")
    flagged = [r for r in rows if r["road_match"] is not True]
    for r in flagged:
        a(f"- Site {r['site_no']}: sites.csv road `{r['road']}`; {'no route component' if r['road_match'] is None else 'mismatch'}.")
    a("")
    a("## Competitors (gas_station, Nearby Search, DISTANCE rank, max 20, site excluded)")
    a("")
    a("Brand derived from displayName (Pertamina incl. SPBU codes like `NN.NNN.NN`, Shell, BP, Vivo, other). "
      "`*` = result hit the 20 cap, so the count is a lower bound.")
    a("")
    for r_km, label in ((1000, "1 km"), (3000, "3 km")):
        a(f"### {label}")
        a("")
        a("| # | Pertamina | Shell | BP | Vivo | other | total |")
        a("|---|---|---|---|---|---|---|")
        for r in rows:
            st = r["nearby"][r_km]
            if st is None:
                a(f"| {r['site_no']} | error | | | | | |")
                continue
            c, tot, capped = st
            star = "*" if capped else ""
            a(f"| {r['site_no']} | {c['Pertamina']} | {c['Shell']} | {c['BP']} | {c['Vivo']} | {c['other']} | {tot}{star} |")
        a("")
    a("## POI counts (Places Aggregate, operational; counts at 500 m / 1 km / 3 km)")
    a("")
    a("| # | " + " | ".join(AGG_TYPES) + " |")
    a("|---|" + "---|" * len(AGG_TYPES))
    for r in rows:
        cells = []
        for t in AGG_TYPES:
            v = r["agg"][t]
            cells.append("/".join("err" if x is None else str(x) for x in v))
        a(f"| {r['site_no']} | " + " | ".join(cells) + " |")
    a("")
    a("## Invalid fields / types")
    a("")
    if invalid_agg:
        for t, msg in invalid_agg.items():
            a(f"- Aggregate type `{t}` rejected: {msg}")
    else:
        a("- Aggregate: none of the 15 types was rejected.")
    if bad_details:
        a(f"- Place Details failed for sites {bad_details}; check the field mask.")
    else:
        a(f"- Place Details: all {len(DETAILS_FIELDS)} requested fields accepted by the field mask (HTTP 200 for every site).")
    a("")
    a("## Observations")
    a("")
    a(observations)
    a("")
    with open(DOC_PATH, "w") as f:
        f.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--reuse", action="store_true")
    ap.add_argument("--report-only", action="store_true",
                    help="rebuild csv/summary/doc from existing raw files")
    args = ap.parse_args()

    with open(SITES_CSV, newline="") as f:
        sites = list(csv.DictReader(f))
    outdir = os.path.join(ROOT, "out", "places_test", args.date)
    os.makedirs(outdir, exist_ok=True)

    invalid_agg = {}
    if args.report_only:
        sp = os.path.join(outdir, "summary.json")
        if os.path.exists(sp):
            CALLS.update(load(sp)["calls"])
    else:
        key = get_api_key()
        for s in sites:
            print(f"site {s['site_no']} ({s['city']})", flush=True)
            fetch_site(s, key, outdir, args.reuse, invalid_agg)

    rows, fill = build_report(sites, outdir, args.date, invalid_agg)
    print("\n== Summary ==")
    print("calls:", json.dumps(CALLS))
    print("details fill (of %d):" % len(sites))
    for f in DETAILS_FIELDS:
        print(f"  {f:24s} {fill[f]}")
    for r in rows:
        n1, n3 = r["nearby"][1000], r["nearby"][3000]
        print(f"site {r['site_no']:>2} {r['status']:<14} road_match={r['road_match']} "
              f"comp1km={n1[1] if n1 else 'err'} comp3km={n3[1] if n3 else 'err'}")
    if invalid_agg:
        print("invalid aggregate types:", list(invalid_agg))


if __name__ == "__main__":
    sys.exit(main())
