"""Queue-risk signal tier and sort order (docs/plans/overview-station-table.md, "Signal tier").

Pure functions over the per-site metrics of the queue-risk query. Neutral by design: the tier says how
often the road is slower before the station than after it, not that a queue exists.
"""
import json
from pathlib import Path

TIERS = ("strong", "moderate", "weak", "none", "cannot_tell")
_RANK = {name: rank for rank, name in enumerate(TIERS)}

RECURRENCE_SHARE = 0.7  # days with 2 h of approach-led slowdown, as a share of full days
STRONG_MEDIAN_S = 60
MASKED_FACTOR = 2

CONFIDENCE_PATH = Path(__file__).with_name("queue_confidence.json")


def tier(metrics):
    """Signal tier from als_pct, both_slow_pct, departure_only_pct, days_with_2h_als, full_days, als_median_delay_s."""
    als = metrics["als_pct"]
    if metrics["both_slow_pct"] > MASKED_FACTOR * als and metrics["departure_only_pct"] > MASKED_FACTOR * als:
        return "cannot_tell"
    days = metrics["days_with_2h_als"]
    full_days = metrics["full_days"]
    median = metrics.get("als_median_delay_s")
    # With no full day there is no recurrence to measure; 0 >= 0.7 * 0 must not read as Moderate.
    if full_days > 0 and days >= RECURRENCE_SHARE * full_days:
        return "strong" if median is not None and median >= STRONG_MEDIAN_S else "moderate"
    if days >= 1:
        return "weak"
    return "none"


def sort_key(entry):
    """Tier, then days with 2 h of slowdown, then median delay, both descending (no median last), then site_id."""
    median = entry.get("als_median_delay_s")
    return (_RANK[entry["tier"]], -entry["days_with_2h_als"], median is None, -(median or 0), entry["site_id"])


def load_confidence(path=CONFIDENCE_PATH):
    """site_id -> {level, reason, as_of}: the reviewed judgement, not computed."""
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)
