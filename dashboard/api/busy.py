"""Busy hours for the typical-day profile. Same cuts as the map bands.

A reading is moderate or worse when it is at least 1.5× usual time and over the delay gate
(20 s urban, 30 s toll). An hour is busy when at least half of its readings are moderate or
worse and the median delay is at least 30 s. Consecutive busy hours are one peak window.
"""
import statistics

BAND_MODERATE = 1.5
GATE_S = {"urban": 20, "toll": 30}
PROVISIONAL_KMH = {"urban": 45, "toll": 80}
BASELINE_FULL = 302
BUSY_MEDIAN_S = 30


def reading_is_slow(index, delay_s, road_class="urban"):
    """Moderate, heavy, or jammed under the band rule. `index` is × usual time."""
    if index is None or delay_s is None:
        return False
    return index >= BAND_MODERATE and delay_s >= GATE_S[road_class]


def hour_is_busy(readings, median_delay_s, road_class="urban"):
    """`readings` is a list of (index, delay_s). At least half must be moderate or worse."""
    n = len(readings)
    if n == 0 or median_delay_s is None:
        return False
    slow = sum(1 for index, delay_s in readings if reading_is_slow(index, delay_s, road_class))
    return counts_are_busy(slow, n, median_delay_s)


def counts_are_busy(slow_n, n, median_delay_s):
    """Same rule as hour_is_busy, from the SQL aggregates."""
    if n <= 0 or median_delay_s is None:
        return False
    return slow_n * 2 >= n and median_delay_s >= BUSY_MEDIAN_S


def _hours_in(start, end):
    """Hour indexes in [start, end). `end` below `start` wraps past midnight. 24 is the end of the day."""
    if end == 24 or end > start:
        return list(range(start, 24 if end == 24 else end))
    return list(range(start, 24)) + list(range(0, end))


def _one_window(start, end, hours):
    values = [hours[i]["median_delay_s"] for i in _hours_in(start, end) if hours[i]["median_delay_s"] is not None]
    return {
        "start_hour": start,
        "end_hour": end,
        "median_delay_s": statistics.median(values) if values else None,
    }


def peak_windows(hours):
    """Consecutive busy hours. `end_hour` is exclusive. A full day is 0–24. A midnight wrap has end < start."""
    flags = [bool(hour["busy"]) for hour in hours]
    if not any(flags):
        return []
    if all(flags):
        return [_one_window(0, 24, hours)]
    runs = []
    start = None
    for hour, busy in enumerate(flags):
        if busy and start is None:
            start = hour
        elif not busy and start is not None:
            runs.append((start, hour))
            start = None
    if start is not None:
        runs.append((start, 24))
    if len(runs) >= 2 and runs[0][0] == 0 and runs[-1][1] == 24:
        wrapped = (runs[-1][0], runs[0][1])
        runs = [wrapped] + runs[1:-1]
    return [_one_window(start, end, hours) for start, end in runs]


def slow_count_sql():
    """COUNTIF body. Gate and provisional speed come from the site's road class (@gate_s, @provisional_kmh)."""
    free_s = "r.expected_distance_m / (@provisional_kmh * 1000 / 3600)"
    return f"""
    (
      IFNULL(t.baseline_samples, 0) >= {BASELINE_FULL}
      AND t.congestion_index IS NOT NULL
      AND t.congestion_index >= {BAND_MODERATE}
      AND t.delay_s >= @gate_s
    )
    OR
    (
      IFNULL(t.baseline_samples, 0) < {BASELINE_FULL}
      AND t.duration_in_seconds IS NOT NULL
      AND IF(r.expected_distance_m > 0, t.duration_in_seconds / ({free_s}), NULL) >= {BAND_MODERATE}
      AND IF(r.expected_distance_m > 0, t.duration_in_seconds - ({free_s}), NULL) >= @gate_s
    )
    """
