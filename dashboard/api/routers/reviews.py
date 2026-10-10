"""GET /api/sites/{site_id}/review-themes: counts of negative or mixed review topics for one site.

Reads place_review_labels joined to v_place_reviews (bead .10.5.3). One label row counts per review: `gemini`
wins over `manual` when both exist. The response holds counts and masked English gists only: never review
text, author fields or raw. The data is a non-random sample (at most 15 reviews per window and site), so the
panel shows counts and n, never rates or a cross-site ranking. The table is a few hundred rows in total, so no
partition filter applies (docs/plans/data-schema.md, "Reviews tables").
"""
from datetime import timedelta

from fastapi import APIRouter

from .. import bq, cache
from .traffic import _require_site

router = APIRouter()

RECENT_DAYS = 365  # "recent" = published within the last 12 months
GIST_LIMIT = 5
NEGATIVE = ("neg", "mixed")

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


def themes(site_id, counts, rows, since):
    """Counts row + one-label-per-review rows -> the response. Negative or mixed topics only; `since` splits recent from older."""
    per_category = {}
    gists = []
    for r in rows:
        if r["sentiment"] not in NEGATIVE:
            continue
        recent = r["published_at"] is not None and r["published_at"] >= since
        for category in sorted(set(r["labels"] or [])):
            slot = per_category.setdefault(category, {"category": category, "recent": 0, "older": 0})
            slot["recent" if recent else "older"] += 1
        if r["gist"] and recent:
            gists.append(r)
    gists.sort(key=lambda r: r["published_at"], reverse=True)
    categories = sorted(per_category.values(), key=lambda c: (-(c["recent"] + c["older"]), c["category"]))
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
    counts = bq.query(COUNTS_SQL, {"site_id": site_id})[0]  # an aggregate without GROUP BY always returns a row
    rows = bq.query(LABELS_SQL, {"site_id": site_id})
    return themes(site_id, counts, rows, since)


@router.get("/sites/{site_id}/review-themes")
def review_themes(site_id: str):
    _require_site(site_id)
    return cache.default.get_or_compute("review-themes", {"site_id": site_id}, lambda: _themes(site_id))
