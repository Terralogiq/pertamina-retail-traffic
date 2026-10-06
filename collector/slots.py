"""Slot arithmetic: every run belongs to the nearest :00/:30 UTC slot."""
from datetime import datetime, timedelta, timezone

SLOT = timedelta(minutes=30)


def utc_now():
    return datetime.now(timezone.utc)


def slot_time(now=None):
    """`now` rounded to the NEAREST :00/:30 UTC (a tie at :15/:45 rounds up).

    A job that starts at :29:58 or :00:02 still lands in the slot the scheduler meant.
    """
    now = now or utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    shifted = now.astimezone(timezone.utc) + SLOT / 2
    return shifted.replace(minute=shifted.minute // 30 * 30, second=0, microsecond=0)


def iso(dt):
    """RFC 3339 UTC string, as BigQuery loads accept for TIMESTAMP."""
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
