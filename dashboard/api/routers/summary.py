"""GET /api/sites/{site_id}/ai-summary: the site's AI summary for the current 30-minute slot (docs/plans/ai-summaries.md).

On demand: a view looks up traffic.ai_summaries for (site, slot). On a miss it builds the facts (queries in
parallel), calls Gemini once and applies the validator gate (ai_summary.validate_summary). Only a summary that
passes is stored and shown. Any failure (no key, Gemini error, rejected answer, BigQuery error) answers
`summary: null`, never an HTTP error, so the site page keeps its sections. Concurrent views on one instance share
one lookup and generation (cache.get_or_compute, keyed on site and slot), and the result, null included, is
reused until the next slot. Two
instances racing on one slot both generate; the MERGE key makes the second overwrite the first's row.
"""
import json
import logging
from datetime import timedelta

from fastapi import APIRouter

from .. import ai_summary, bq, cache
from . import traffic
from .traffic import _iso, _require_site

router = APIRouter()
log = logging.getLogger(__name__)

# A view belongs to the :00/:30 slot that started at least 5 minutes earlier, the cache's :05/:35 boundary: the
# collector has written that slot's readings by then. The cache key carries the slot, so an entry is never served
# after its slot.
SLOT_LAG = timedelta(minutes=cache.BOUNDARY_MINUTES[0])

LOOKUP_SQL = f"""
SELECT slot_time, as_of, generated_at, model, model_version, prompt_version, TO_JSON_STRING(facts) AS facts,
  ARRAY(SELECT AS STRUCT s.topic, s.text FROM UNNEST(sentences) AS s WITH OFFSET AS i ORDER BY i) AS sentences
FROM {bq.table("ai_summaries")}
WHERE slot_time = @slot_time AND site_id = @site_id AND model = @model AND prompt_version = @prompt_version
  AND validation_ok
ORDER BY generated_at DESC
LIMIT 1
"""

# bq.query takes scalar parameters only: facts and sentences arrive as JSON strings and are rebuilt here. A NULL
# parameter is typed STRING, so the nullable non-string values are CAST.
MERGE_SQL = f"""
MERGE {bq.table("ai_summaries")} AS t
USING (
  SELECT
    @site_id AS site_id, @slot_time AS slot_time, CAST(@as_of AS TIMESTAMP) AS as_of, @generated_at AS generated_at,
    @model AS model, @model_version AS model_version, @prompt_version AS prompt_version,
    PARSE_JSON(@facts) AS facts,
    ARRAY(
      SELECT AS STRUCT
        JSON_VALUE(s, '$.topic') AS topic, JSON_VALUE(s, '$.text') AS text, BOOL(s.ok) AS ok,
        JSON_VALUE_ARRAY(s, '$.problems') AS problems,
        ARRAY(
          SELECT AS STRUCT JSON_VALUE(m, '$.number') AS number, JSON_VALUE(m, '$.match') AS match
          FROM UNNEST(JSON_QUERY_ARRAY(s, '$.number_matches')) AS m WITH OFFSET AS j ORDER BY j) AS number_matches
      FROM UNNEST(JSON_QUERY_ARRAY(PARSE_JSON(@sentences))) AS s WITH OFFSET AS i ORDER BY i) AS sentences,
    @validation_ok AS validation_ok, CAST(@input_tokens AS INT64) AS input_tokens,
    CAST(@output_tokens AS INT64) AS output_tokens, CAST(@latency_ms AS INT64) AS latency_ms
) AS s
ON t.slot_time = @slot_time AND t.site_id = s.site_id AND t.model = s.model AND t.prompt_version = s.prompt_version
WHEN MATCHED THEN UPDATE SET
  as_of = s.as_of, generated_at = s.generated_at, model_version = s.model_version, facts = s.facts,
  sentences = s.sentences, validation_ok = s.validation_ok, input_tokens = s.input_tokens,
  output_tokens = s.output_tokens, latency_ms = s.latency_ms
WHEN NOT MATCHED THEN INSERT
  (site_id, slot_time, as_of, generated_at, model, model_version, prompt_version, facts, sentences, validation_ok,
   input_tokens, output_tokens, latency_ms)
VALUES
  (s.site_id, s.slot_time, s.as_of, s.generated_at, s.model, s.model_version, s.prompt_version, s.facts, s.sentences,
   s.validation_ok, s.input_tokens, s.output_tokens, s.latency_ms)
"""


def slot_for(now):
    """The :00/:30 UTC slot a view at `now` belongs to; it changes at :05 and :35."""
    t = now - SLOT_LAG
    return t.replace(minute=t.minute - t.minute % 30, second=0, microsecond=0)


def _key(site_id, slot):
    return {"site_id": site_id, "slot_time": slot, "model": ai_summary.MODEL,
            "prompt_version": ai_summary.PROMPT_VERSION}


def summary_payload(row):
    """A stored row (or a just-generated record of the same shape) -> the response's `summary`."""
    return {
        "slot_time": _iso(row["slot_time"]),
        "as_of": _iso(row["as_of"]),
        "generated_at": _iso(row["generated_at"]),
        "model": row["model"],
        "model_version": row["model_version"],
        "prompt_version": row["prompt_version"],
        "sentences": [{"topic": s["topic"], "text": s["text"]} for s in row["sentences"]],
        "facts": json.loads(row["facts"]),
        "sources": ai_summary.SOURCES,
    }


def generate(site, slot, now):
    """Facts, one Gemini call, the gate. A record ready to store, or None (logged with counts only, never text)."""
    site_id = site["site_id"]
    key = ai_summary.api_key()
    if not key:
        log.warning("ai-summary %s: GEMINI_API_KEY is not set", site_id)
        return None
    try:
        facts, as_of = ai_summary.facts_for_site(site, now)
    except Exception as e:  # any BigQuery failure means no summary, not a 500
        log.warning("ai-summary %s: facts query failed (%s)", site_id, type(e).__name__)
        return None
    try:
        g = ai_summary.call_gemini(key, facts)
    except Exception as e:  # e.g. IncompleteRead or SSLError past httpjson: no summary, not an uncached 500
        log.warning("ai-summary %s: Gemini call raised (%s)", site_id, type(e).__name__)
        return None
    if g["error"]:
        log.warning("ai-summary %s: Gemini failed (%s)", site_id, g["error"])
        return None
    v = ai_summary.validate_summary(g["sentences"], facts)
    if not v["ok"]:
        failing = sum(1 for s in v["sentences"] if not s["ok"])
        log.warning("ai-summary %s: rejected (%d sentences, count_ok=%s, missing topics %s, %d failing)",
                    site_id, len(v["sentences"]), v["count_ok"], v["missing_topics"], failing)
        return None
    usage = g["usage"] or {}
    return {
        **_key(site_id, slot),
        "as_of": as_of,
        "generated_at": cache.utc_now(),
        "model_version": g["model_version"],
        "facts": json.dumps(facts, ensure_ascii=False, default=str),
        "sentences": v["sentences"],
        "validation_ok": True,
        "input_tokens": usage.get("promptTokenCount"),
        "output_tokens": (usage.get("candidatesTokenCount") or 0) + (usage.get("thoughtsTokenCount") or 0)
        if usage else None,   # thinking tokens bill as output
        "latency_ms": g["latency_ms"],
    }


def store(record):
    bq.query(MERGE_SQL, {**record, "sentences": json.dumps(record["sentences"], ensure_ascii=False)})


def site_summary(site, slot, now):
    """The response body: the stored summary for `slot`, else a fresh one that passed the gate, else null."""
    site_id = site["site_id"]
    try:
        rows = bq.query(LOOKUP_SQL, _key(site_id, slot))
    except Exception as e:  # e.g. the table does not exist yet: no card rather than a Gemini call we cannot store
        log.warning("ai-summary %s: lookup failed (%s)", site_id, type(e).__name__)
        return {"site_id": site_id, "summary": None}
    if rows:
        return {"site_id": site_id, "summary": summary_payload(rows[0])}
    record = generate(site, slot, now)
    if record is None:
        return {"site_id": site_id, "summary": None}
    try:
        store(record)
    except Exception as e:  # the summary passed the gate; show it, and say the audit row is missing
        log.warning("ai-summary %s: store failed (%s); shown without a stored row", site_id, type(e).__name__)
    return {"site_id": site_id, "summary": summary_payload(record)}


@router.get("/sites/{site_id}/ai-summary")
def ai_summary_for_site(site_id: str):
    _require_site(site_id)
    site = next(s for s in traffic.get_sites() if s["site_id"] == site_id)
    # The slot is fixed at request time and is part of the cache key: a generation that finishes after :05/:35 is
    # stored under, and cached for, the slot it started in, and the next view's new slot misses that entry.
    now = cache.utc_now()
    slot = slot_for(now)
    return cache.default.get_or_compute("ai-summary", {"site_id": site_id, "slot": slot.isoformat()},
                                        lambda: site_summary(site, slot, now))
