"""Places API (New) + Places Aggregate calls and row builders. Stdlib only; no BigQuery here.

Request shapes, field masks, radii and brand_of are the ones of scripts/places_test_fetch.py
(vendored: the Cloud Run build context is places_job/ only). One site is profiled with
1 Details + 2 Nearby + 45 Aggregate calls. Only successful calls produce rows; failures are
returned as error strings (the API key is scrubbed from them by httpjson).
"""
import json
import math
import re

import httpjson

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
NEARBY_MAX = 20
AGG_RADII = [500, 1000, 3000]
AGG_TYPES = [
    "restaurant", "cafe", "convenience_store", "supermarket", "shopping_mall",
    "school", "university", "hospital", "bank", "atm", "lodging",
    "car_repair", "car_wash", "electric_vehicle_charging_station",
    "gas_station",
]

ATTEMPTS = 5   # 1, 2, 4, 8 s backoff, as the test-fetch script
TIMEOUT = 60


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


def haversine_m(lat1, lng1, lat2, lng2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(a))


_TS = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d+)?Z$")


def ts(value):
    """A Places RFC 3339 timestamp cut to microseconds (BigQuery rejects nanosecond digits); None if not parseable."""
    m = _TS.match(value or "")
    if not m:
        return None
    return m.group(1) + ((m.group(2) + "000000")[:7] if m.group(2) else "") + "Z"


def _text(obj):
    return (obj or {}).get("text")


def _number(v, cast):
    return cast(v) if v is not None else None


# --- API calls: each returns (parsed_response, None) or (None, error_text) -------------------

def fetch_details(key, place_id):
    return httpjson.request_json(
        "GET", DETAILS_URL.format(place_id) + "?languageCode=id&regionCode=ID",
        {"X-Goog-Api-Key": key, "X-Goog-FieldMask": ",".join(DETAILS_FIELDS)},
        secret=key, attempts=ATTEMPTS, timeout=TIMEOUT)


def fetch_nearby(key, lat, lng, radius_m):
    body = {
        "includedTypes": ["gas_station"],
        "maxResultCount": NEARBY_MAX,
        "rankPreference": "DISTANCE",
        "languageCode": "id",
        "regionCode": "ID",
        "locationRestriction": {"circle": {
            "center": {"latitude": lat, "longitude": lng}, "radius": float(radius_m)}},
    }
    return httpjson.request_json(
        "POST", NEARBY_URL,
        {"X-Goog-Api-Key": key, "X-Goog-FieldMask": ",".join("places." + f for f in NEARBY_FIELDS)},
        body, secret=key, attempts=ATTEMPTS, timeout=TIMEOUT)


def fetch_aggregate(key, place_id, place_type, radius_m):
    body = {
        "insights": ["INSIGHT_COUNT"],
        "filter": {
            "locationFilter": {"circle": {"place": f"places/{place_id}", "radius": radius_m}},
            "typeFilter": {"includedTypes": [place_type]},
            "operatingStatus": ["OPERATING_STATUS_OPERATIONAL"],
        },
    }
    return httpjson.request_json(
        "POST", AGG_URL, {"X-Goog-Api-Key": key}, body,
        secret=key, attempts=ATTEMPTS, timeout=TIMEOUT)


# --- row builders: pure ----------------------------------------------------------------------

def _review(r):
    original = r.get("originalText") or {}
    return {
        "rating": _number(r.get("rating"), int),
        "text": original.get("text") or _text(r.get("text")),
        "language": original.get("languageCode") or (r.get("text") or {}).get("languageCode"),
        "publish_time": ts(r.get("publishTime")),
        "author_name": (r.get("authorAttribution") or {}).get("displayName"),
    }


def details_row(run_id, site_id, fetched_at, resp):
    """One places_details row from a Place Details response; raw is the whole response as JSON text."""
    regular = resp.get("regularOpeningHours") or {}
    current = resp.get("currentOpeningHours") or {}
    return {
        "run_id": run_id, "site_id": site_id, "fetched_at": fetched_at,
        "place_id": resp.get("id"),
        "display_name": _text(resp.get("displayName")),
        "rating": _number(resp.get("rating"), float),
        "user_rating_count": _number(resp.get("userRatingCount"), int),
        "business_status": resp.get("businessStatus"),
        "primary_type": resp.get("primaryType"),
        "open_now": current.get("openNow", regular.get("openNow")),
        "weekday_descriptions": list(regular.get("weekdayDescriptions") or []),
        "utc_offset_minutes": _number(resp.get("utcOffsetMinutes"), int),
        "reviews": [_review(r) for r in resp.get("reviews") or []],
        "raw": json.dumps(resp, ensure_ascii=False),
    }


def nearby_rows(run_id, site_id, fetched_at, radius_m, site_lat, site_lng, resp):
    """places_nearby rows for one radius, in the API's DISTANCE order (rank is 1-based).

    Every returned place is kept, the site itself included: it is excluded at read time via
    sites.place_id. A place id repeated in one response keeps its first row (MERGE needs unique keys).
    """
    rows, seen = [], set()
    for rank, p in enumerate(resp.get("places") or [], start=1):
        pid = p.get("id")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        loc = p.get("location") or {}
        name = _text(p.get("displayName"))
        dist = None
        if "latitude" in loc and "longitude" in loc:
            dist = round(haversine_m(site_lat, site_lng, loc["latitude"], loc["longitude"]))
        rows.append({
            "run_id": run_id, "site_id": site_id, "radius_m": radius_m, "place_id": pid,
            "fetched_at": fetched_at, "name": name, "brand": brand_of(name),
            "primary_type": p.get("primaryType"), "distance_m": dist,
            "rating": _number(p.get("rating"), float),
            "user_rating_count": _number(p.get("userRatingCount"), int),
            "business_status": p.get("businessStatus"), "rank": rank,
            "raw": json.dumps(p, ensure_ascii=False),
        })
    return rows


def aggregate_row(run_id, site_id, fetched_at, place_type, radius_m, resp):
    """The count is an int64 string in the response, and absent when zero."""
    return {
        "run_id": run_id, "site_id": site_id, "place_type": place_type, "radius_m": radius_m,
        "fetched_at": fetched_at, "count": int(resp.get("count") or 0),
        "raw": json.dumps(resp, ensure_ascii=False),
    }


def profile_site(key, site, run_id, fetched_at):
    """Profile one site. Returns (details_rows, nearby_rows, aggregate_rows, n_calls, errors)."""
    site_id, place_id = site["site_id"], site["place_id"]
    calls, errors = 0, []
    d_rows, n_rows, a_rows = [], [], []

    calls += 1
    details, err = fetch_details(key, place_id)
    if err:
        errors.append(f"details {site_id}: {err}")
    else:
        d_rows.append(details_row(run_id, site_id, fetched_at, details))

    loc = (details or {}).get("location") or {}
    if "latitude" in loc and "longitude" in loc:
        for r in NEARBY_RADII:
            calls += 1
            resp, err = fetch_nearby(key, loc["latitude"], loc["longitude"], r)
            if err:
                errors.append(f"nearby {site_id} {r} m: {err}")
            else:
                n_rows += nearby_rows(run_id, site_id, fetched_at, r, loc["latitude"], loc["longitude"], resp)
    elif details is not None:
        errors.append(f"details {site_id}: no location in the response; Nearby skipped")

    for t in AGG_TYPES:
        for r in AGG_RADII:
            calls += 1
            resp, err = fetch_aggregate(key, place_id, t, r)
            if err:
                errors.append(f"aggregate {site_id} {t} {r} m: {err}")
            else:
                a_rows.append(aggregate_row(run_id, site_id, fetched_at, t, r, resp))
    return d_rows, n_rows, a_rows, calls, errors
