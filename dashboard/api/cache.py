"""In-process TTL cache per (endpoint, params).

An entry expires at the next :05 or :35 UTC after it was stored: the collector writes the :00/:30 slot
within about 60 s, so a later read always sees the new slot. A fresh slot every 30 min means an entry
never lives longer than 30 min. The clock is injectable for tests.
"""
import threading
from datetime import datetime, timedelta, timezone

MAX_TTL = timedelta(minutes=30)
BOUNDARY_MINUTES = (5, 35)
MAX_ENTRIES = 500  # keys carry user-supplied params (site_id, from, to): bound the memory


def utc_now():
    return datetime.now(timezone.utc)


def next_expiry(now):
    """First :05/:35 boundary strictly after `now`, never more than 30 min away."""
    hour = now.replace(minute=0, second=0, microsecond=0)
    candidates = [hour + timedelta(minutes=m) for m in BOUNDARY_MINUTES]
    candidates.append(hour + timedelta(hours=1, minutes=BOUNDARY_MINUTES[0]))
    boundary = min(c for c in candidates if c > now)
    return min(boundary, now + MAX_TTL)


class TtlCache:
    def __init__(self, clock=utc_now):
        self._clock = clock
        self._lock = threading.Lock()
        self._entries = {}  # key -> (expires_at, value)

    @staticmethod
    def key(endpoint, params):
        return endpoint, tuple(sorted((params or {}).items()))

    def get_or_compute(self, endpoint, params, compute):
        key = self.key(endpoint, params)
        now = self._clock()
        with self._lock:
            hit = self._entries.get(key)
            if hit and now < hit[0]:
                return hit[1]
        value = compute()  # outside the lock: a slow BigQuery job must not block other endpoints
        stored_at = self._clock()
        with self._lock:
            self._entries = {k: e for k, e in self._entries.items() if e[0] > stored_at}
            self._entries[key] = (next_expiry(stored_at), value)
            while len(self._entries) > MAX_ENTRIES:  # evict the entry that expires first
                del self._entries[min(self._entries, key=lambda k: self._entries[k][0])]
        return value

    def clear(self):
        with self._lock:
            self._entries.clear()


# Shared by every router: `cache.default.get_or_compute("sites", {}, lambda: ...)`.
default = TtlCache()
