"""GET /api/sites/{site_id}/review-themes and GET /api/review-themes: counts of negative or mixed review topics.

Reads place_review_labels joined to v_place_reviews (bead .10.5.3). One label row counts per review: `gemini`
wins over `manual` when both exist. The responses hold counts and masked English gists only: never review
text, author fields or raw. The data is a non-random sample (at most 15 reviews per window and site), so the
UI shows counts with n; a cross-site sort is allowed, rates are not. The table is a few hundred rows in total, so no
partition filter applies (docs/plans/data-schema.md, "Reviews tables").
"""
from datetime import timedelta

from fastapi import APIRouter

from .. import bq, cache
from . import traffic
from .traffic import _require_site

router = APIRouter()

RECENT_DAYS = 365  # "recent" = published within the last 12 months
GIST_LIMIT = 5
NEGATIVE = ("neg", "mixed")
QUEUE_CATEGORY = "antrian"

COUNTS_SQL = f"""
SELECT COUNT(*) AS n_reviews, COUNTIF(TRIM(IFNULL(text, '')) != '') AS n_text_reviews
FROM {bq.table("v_place_reviews")}
WHERE site_id = @site_id
"""

# One row per labelled review, `gemini` before `manual`, then the latest label. site_id sits on both tables
# (the labels table is clustered by it).
LABELS_SQL = f"""
SELECT r.published_at, l.labels, l.sentiment, l.gist
FROM {bq.table("place_review_labels")} AS l
JOIN {bq.table("v_place_reviews")} AS r ON r.review_key = l.review_key
WHERE l.site_id = @site_id AND r.site_id = @site_id
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY l.review_key ORDER BY IF(l.method = 'gemini', 0, 1), l.labeled_at DESC) = 1
"""

# The same one-label-per-review rule over every site: no gist, no text.
ALL_LABELS_SQL = f"""
SELECT l.site_id, r.published_at, l.labels, l.sentiment
FROM {bq.table("place_review_labels")} AS l
JOIN {bq.table("v_place_reviews")} AS r ON r.review_key = l.review_key AND r.site_id = l.site_id
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY l.review_key ORDER BY IF(l.method = 'gemini', 0, 1), l.labeled_at DESC) = 1
"""


def _tally(rows, since):
    """One-label-per-review rows -> (per-category recent/older counts, recent rows with a gist). Negative or mixed only."""
    per_category = {}
    gists = []
    for r in rows:
        if r["sentiment"] not in NEGATIVE:
            continue
        recent = r["published_at"] is not None and r["published_at"] >= since
        for category in sorted(set(r["labels"] or [])):
            slot = per_category.setdefault(category, {"category": category, "recent": 0, "older": 0})
            slot["recent" if recent else "older"] += 1
        if r.get("gist") and recent:
            gists.append(r)
    categories = sorted(per_category.values(), key=lambda c: (-(c["recent"] + c["older"]), c["category"]))
    return categories, gists


def themes(site_id, counts, rows, since):
    """Counts row + one-label-per-review rows -> the response. Negative or mixed topics only; `since` splits recent from older."""
    categories, gists = _tally(rows, since)
    gists.sort(key=lambda r: r["published_at"], reverse=True)
    return {
        "site_id": site_id,
        "n_reviews": counts["n_reviews"],
        "n_text_reviews": counts["n_text_reviews"],
        "n_labelled": len(rows),
        "categories": categories,
        "gists": [{"month": r["published_at"].strftime("%Y-%m"), "labels": sorted(set(r["labels"] or [])),
                   "gist": r["gist"]} for r in gists[:GIST_LIMIT]],
    }


def _themes(site_id):
    since = cache.utc_now() - timedelta(days=RECENT_DAYS)
    params = {"site_id": site_id}
    counts, rows = bq.query_all((COUNTS_SQL, params), (LABELS_SQL, params))
    return themes(site_id, counts[0], rows, since)  # an aggregate without GROUP BY always returns a row


@router.get("/sites/{site_id}/review-themes")
def review_themes(site_id: str):
    _require_site(site_id)
    return cache.default.get_or_compute("review-themes", {"site_id": site_id}, lambda: _themes(site_id))


def summary_entry(site_id, rows, since):
    """One site's counts for the cross-site table. `top` holds every category tied at the highest count."""
    categories, _ = _tally(rows, since)
    counted = [{"category": c["category"], "count": c["recent"] + c["older"]} for c in categories]
    top = None
    if counted:
        best = counted[0]["count"]  # sorted by count descending
        top = {"categories": sorted(c["category"] for c in counted if c["count"] == best), "count": best}
    return {
        "site_id": site_id,
        "n_labelled": len(rows),
        "queue_complaints": next((c["count"] for c in counted if c["category"] == QUEUE_CATEGORY), 0),
        "top": top,
        "categories": counted,
    }


def _summary():
    since = cache.utc_now() - timedelta(days=RECENT_DAYS)
    by_site = {}
    for row in bq.query(ALL_LABELS_SQL):
        by_site.setdefault(row["site_id"], []).append(row)
    return {"sites": [summary_entry(s["site_id"], by_site.get(s["site_id"], []), since) for s in traffic.get_sites()]}


@router.get("/review-themes")
def review_themes_summary():
    return cache.default.get_or_compute("review-themes-summary", {}, _summary)
