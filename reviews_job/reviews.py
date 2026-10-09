"""Legacy Place Details calls and row builders for the newest-reviews poller. Stdlib only; no BigQuery here.

Why legacy: Places API (New) returns at most 5 reviews in Google's own order, with no sort option. The legacy
Place Details endpoint takes `reviews_sort=newest`, so a forward poll can catch every new review
(docs/plans/reviews-feasibility.md, "Test"). Legacy Places is enabled only in project demogcp-terra2021, where the
API key lives; the job reads it from Secret Manager there. The key goes in the query string (the legacy API has no
header form), so URLs are never logged or stored, and the key is scrubbed from every error text.
"""
import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpjson

DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
FIELDS = "reviews,user_ratings_total,rating"

# mode -> [(reviews_sort, language)]. The variant label is "<sort>_<language>".
MODES = {
    "newest": [("newest", "id")],
    "sample": [("newest", "id"), ("most_relevant", "id"), ("most_relevant", "en")],
}

ATTEMPTS = 3
TIMEOUT = 30


def variant_name(sort, language):
    return f"{sort}_{language}"


def fetch_details(key, place_id, sort, language):
    """One legacy Place Details call. Returns (whole_response_dict, None) or (None, error_text)."""
    query = urlencode({
        "place_id": place_id, "fields": FIELDS, "reviews_no_translations": "true",
        "reviews_sort": sort, "language": language, "key": key,
    })
    data, err = httpjson.request_json("GET", f"{DETAILS_URL}?{query}", {}, secret=key,
                                      attempts=ATTEMPTS, timeout=TIMEOUT)
    if err:
        return None, err
    # The legacy API answers HTTP 200 with a status field, including for denied or malformed requests.
    status = data.get("status")
    if status != "OK":
        msg = f"status {status}: {data.get('error_message', '')}".strip()
        return None, msg.replace(key, "***")
    return data, None


def review_key(place_id, review):
    """Stable id of one review: hash of place and author profile URL (one review per author per place).

    Without a profile URL, falls back to place, author name and publish time. Rating, text and time are left
    out of the URL form on purpose: reviews are editable, and an edit must not create a new row.
    """
    if review.get("author_url"):
        basis = f"{place_id}|{review['author_url']}"
    else:
        basis = f"{place_id}|{review.get('author_name') or ''}|{review.get('time')}"
    return hashlib.sha256(basis.encode()).hexdigest()


def _iso_epoch(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def review_row(site, review, variant, fetched_iso):
    """One place_reviews staging row. None when the review has no time (it cannot be keyed)."""
    if not isinstance(review.get("time"), (int, float)):
        return None
    return {
        "review_key": review_key(site["place_id"], review),
        "site_id": site["site_id"],
        "place_id": site["place_id"],
        "published_at": _iso_epoch(review["time"]),
        "rating": review.get("rating"),
        "text": review.get("text") or None,   # rating-only reviews have "" or no text: stored as NULL
        "language": review.get("language"),
        "original_language": review.get("original_language"),
        "first_seen_at": fetched_iso,
        "last_seen_at": fetched_iso,
        "seen_in": [variant],
        "raw": json.dumps(review, ensure_ascii=False),
    }


def snapshot_row(site, mode, variant, response, run_id, fetched_iso):
    """One place_review_snapshots staging row from the whole API response (raw)."""
    result = response.get("result") or {}
    reviews = result.get("reviews") or []
    return {
        "run_id": run_id, "site_id": site["site_id"], "mode": mode, "variant": variant,
        "fetched_at": fetched_iso, "user_ratings_total": result.get("user_ratings_total"),
        "rating": result.get("rating"), "n_reviews": len(reviews),
        "raw": json.dumps(response, ensure_ascii=False),
    }


def dedupe(rows):
    """One row per review_key; seen_in lists every variant that returned the review."""
    out = {}
    for r in rows:
        have = out.get(r["review_key"])
        if have is None:
            out[r["review_key"]] = dict(r, seen_in=list(r["seen_in"]))
        else:
            have["seen_in"] = sorted(set(have["seen_in"]) | set(r["seen_in"]))
    return list(out.values())


def poll_site(key, site, mode, run_id, fetched_iso):
    """All variants of `mode` for one site. Returns (review_rows, snapshot_rows, n_calls, errors).

    A failed call leaves no snapshot and no review rows; the error text names the site and variant.
    """
    reviews, snaps, errors = [], [], []
    variants = MODES[mode]
    for sort, language in variants:
        variant = variant_name(sort, language)
        response, err = fetch_details(key, site["place_id"], sort, language)
        if err:
            errors.append(f"{site['site_id']} {variant}: {err}")
            continue
        snaps.append(snapshot_row(site, mode, variant, response, run_id, fetched_iso))
        for rv in (response.get("result") or {}).get("reviews") or []:
            row = review_row(site, rv, variant, fetched_iso)
            if row:
                reviews.append(row)
    return dedupe(reviews), snaps, len(variants), errors
