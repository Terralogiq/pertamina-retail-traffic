#!/usr/bin/env python3
"""Prototype for bead .10.4: short AI summaries per SPBU, grounded on facts built in SQL. Plan: docs/plans/ai-summaries.md.

  1. facts_for_site   read-only BigQuery queries -> a small facts dict (minutes, bands and busy windows use the same
                      rules as dashboard/api/busy.py, imported by path).
  2. call_gemini      the facts go to the Gemini API (same model, key and request shape as reviews_job/gemini.py);
                      the answer is 3-5 sentences as JSON, each tagged with a topic.
  3. validate_summary pure function: every number, time, weekday and direction word in a sentence must come from the
                      facts (or be a stated rounding of a fact). A failing sentence is flagged, not shown as clean.

Review text, gists and author names never leave BigQuery: the facts carry label counts only.
Writes out/ai_summaries/<UTC timestamp>/<site_id>.json (git-ignored). No BigQuery writes.

Usage: .venv/bin/python scripts/ai_summary_prototype.py --site 34.121.03 --site KM57A [--facts-only] [--out-dir DIR]
Needs google-cloud-bigquery and ADC (.venv), plus GEMINI_API_KEY or gcloud access to Secret Manager `gemini-api-key`
in gcp-coe-492507 (never printed).
"""
import argparse
import importlib.util
import json
import os
import re
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PROJECT = "gcp-coe-sandbox"
DATASET = "traffic"
LOCATION = "asia-southeast2"
KEY_SECRET_PROJECT = "gcp-coe-492507"
MODEL = "gemini-3.8-flash"   # same pin as reviews_job/gemini.py; copied, not imported, so a prompt change there does not move this
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
PROMPT_VERSION = "s4"
WINDOW_DAYS = 28             # same query window as /api/traffic/typical-day
WEEK_DAYS = 7
SLOT_MINUTES = 30
MIN_RAIN_SLOTS = 8           # below this a rain effect is not reported
MIN_HOUR_READINGS = 4        # same "thin hour" cut as the typical-day profile
POI_TYPES = ["restaurant", "cafe", "lodging", "convenience_store", "school", "shopping_mall"]
# Gemini API paid tier, USD per 1M tokens, through 2026-12-31 (https://ai.google.dev/gemini-api/docs/pricing).
PRICE_IN, PRICE_OUT = 0.75, 3.75


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


busy = _load("busy", "dashboard/api/busy.py")
holidays = _load("holidays", "dashboard/api/holidays.py")
httpjson = _load("httpjson", "reviews_job/httpjson.py")

# ---------------------------------------------------------------------------------------------------------------
# 1. Facts (SQL)
# ---------------------------------------------------------------------------------------------------------------

SITE_SQL = f"""
SELECT site_id, name, city, road_name, road_type, timezone, place_id
FROM `{PROJECT}.{DATASET}.sites` WHERE site_id = @site_id"""

# One row per slot per leg. `slow` is the same moderate-or-worse test as the busy-hour query of the dashboard.
SLOTS_SQL = f"""
SELECT r.leg, t.slot_time, DATETIME(t.slot_time, s.timezone) AS local_dt, t.delay_s, t.baseline_samples,
  IF({busy.slow_count_sql()}, 1, 0) AS slow
FROM `{PROJECT}.{DATASET}.v_traffic` AS t
JOIN `{PROJECT}.{DATASET}.routes` AS r ON r.selected_route_id = t.selected_route_id AND r.active
JOIN `{PROJECT}.{DATASET}.sites` AS s ON s.site_id = r.site_id
WHERE t.slot_time >= @from_ts AND t.slot_time <= @to_ts AND r.site_id = @site_id AND t.delay_s IS NOT NULL
ORDER BY t.slot_time, r.leg"""

# Rain is the core rain_flag (precipitation), WeatherNext-compatible. demo_rain_flag is demo-only and stays out of the facts.
WEATHER_SQL = f"""
SELECT slot_time, DATETIME(slot_time, @tz) AS local_dt, temperature_c,
  IFNULL(rain_flag, FALSE) AS rain
FROM `{PROJECT}.{DATASET}.weather_slots`
WHERE site_id = @site_id AND slot_time >= @from_ts AND slot_time <= @to_ts
QUALIFY ROW_NUMBER() OVER (PARTITION BY slot_time ORDER BY fetched_at DESC) = 1
ORDER BY slot_time"""

DETAILS_SQL = f"""
SELECT rating, user_rating_count FROM `{PROJECT}.{DATASET}.places_details`
WHERE site_id = @site_id AND fetched_at >= @from_ts ORDER BY fetched_at DESC LIMIT 1"""

# Latest run, by the rule in data-schema.md: run_id of the row with the greatest fetched_at.
NEARBY_SQL = f"""
WITH latest AS (
  SELECT run_id FROM `{PROJECT}.{DATASET}.places_nearby` WHERE fetched_at >= @from_ts ORDER BY fetched_at DESC LIMIT 1)
SELECT n.radius_m, n.brand, n.distance_m
FROM `{PROJECT}.{DATASET}.places_nearby` AS n JOIN latest USING (run_id)
WHERE n.site_id = @site_id AND n.fetched_at >= @from_ts
  AND n.place_id != (SELECT place_id FROM `{PROJECT}.{DATASET}.sites` WHERE site_id = @site_id)"""

AGG_SQL = f"""
WITH latest AS (
  SELECT run_id FROM `{PROJECT}.{DATASET}.places_aggregate` WHERE fetched_at >= @from_ts ORDER BY fetched_at DESC LIMIT 1)
SELECT place_type, count FROM `{PROJECT}.{DATASET}.places_aggregate` JOIN latest USING (run_id)
WHERE site_id = @site_id AND fetched_at >= @from_ts AND radius_m = 500 AND place_type IN UNNEST(@types)"""

# Labels only (gemini method). The text, the gist and the author never enter the facts.
THEMES_SQL = f"""
SELECT l.sentiment, label
FROM `{PROJECT}.{DATASET}.place_review_labels` AS l LEFT JOIN UNNEST(l.labels) AS label
WHERE l.site_id = @site_id AND l.method = 'gemini'
QUALIFY ROW_NUMBER() OVER (PARTITION BY l.review_key, label ORDER BY l.labeled_at DESC) = 1"""

REVIEWS_SQL = f"""
SELECT COUNT(*) AS n_reviews, COUNTIF(text IS NOT NULL) AS n_text
FROM `{PROJECT}.{DATASET}.v_place_reviews` WHERE site_id = @site_id"""


def _client():
    from google.cloud import bigquery
    return bigquery


def run_query(sql, params):
    bq = _client()
    client = bq.Client(project=PROJECT, location=LOCATION)
    cfg = bq.QueryJobConfig(query_parameters=[_param(bq, k, v) for k, v in params.items()])
    return [dict(row.items()) for row in client.query(sql, job_config=cfg).result()]


def _param(bq, name, value):
    if isinstance(value, list):
        return bq.ArrayQueryParameter(name, "STRING", value)
    if isinstance(value, bool):
        return bq.ScalarQueryParameter(name, "BOOL", value)
    if isinstance(value, int):
        return bq.ScalarQueryParameter(name, "INT64", value)
    if isinstance(value, datetime):
        return bq.ScalarQueryParameter(name, "TIMESTAMP", value)
    return bq.ScalarQueryParameter(name, "STRING", value)


def delay(seconds):
    """A delay as {value, unit}: whole seconds under a minute, else minutes with one decimal, never negative.
    Same format as formatDelay in dashboard/web/src/map/bands.ts, so a summary and the map agree."""
    if seconds is None:
        return None
    seconds = max(seconds, 0)
    if seconds < 60:
        return {"value": round(seconds), "unit": "s"}
    return {"value": round(seconds / 60, 1), "unit": "min"}


def hhmm(hour):
    return f"{hour % 24:02d}:00"


NO_DIFFERENCE_S = 5   # a median within 5 s of the comparison is "no clear difference"


def direction(delta_s):
    return "no clear difference" if abs(delta_s) < NO_DIFFERENCE_S else ("slower" if delta_s > 0 else "faster")


def _median(values):
    return statistics.median(values) if values else None


def traffic_facts(rows, weather, road_class):
    """Pure: slot rows (leg, local_dt, delay_s, baseline_samples, slow) and weather rows -> the traffic and weather facts."""
    if not rows:
        return None, None
    as_of = max(r["local_dt"] for r in rows)
    today, hour_now = as_of.date(), as_of.hour
    kind = "weekend" if holidays.is_weekend(today) else "weekday"
    dates = sorted({r["local_dt"].date() for r in rows})
    kind_days = sorted({d for d in dates if ("weekend" if holidays.is_weekend(d) else "weekday") == kind})
    ready = len(dates) >= 7
    week_from = today - timedelta(days=WEEK_DAYS - 1)
    for r in rows:
        r["date"] = r["local_dt"].date()
        r["hour"] = r["local_dt"].hour
        r["kind"] = "weekend" if holidays.is_weekend(r["date"]) else "weekday"
        r["delay"] = max(r["delay_s"], 0)
    rain_at = {w["slot_time"]: bool(w["rain"]) for w in weather}
    for r in rows:
        r["rain"] = rain_at.get(r["slot_time"])

    legs = {}
    for leg in sorted({r["leg"] for r in rows}):
        lr = [r for r in rows if r["leg"] == leg]
        # Busy windows of today's day kind, from the same hour rule and window merge as the API.
        hours = []
        for h in range(24):
            hr = [r for r in lr if r["kind"] == kind and r["hour"] == h]
            med = _median([r["delay"] for r in hr])
            hours.append({"hour": h, "median_delay_s": med, "n": len(hr),
                          "busy": busy.counts_are_busy(sum(r["slow"] for r in hr), len(hr), med)})
        windows = []
        if ready:
            for w in busy.peak_windows(hours):
                windows.append({"start": hhmm(w["start_hour"]), "end": hhmm(w["end_hour"]),
                                "median_delay": delay(w["median_delay_s"]), "direction": "slower"})
        t = [r for r in lr if r["date"] == today]
        usual = [r["delay"] for r in lr if r["date"] != today and r["kind"] == kind and r["hour"] <= hour_now]
        today_med = _median([r["delay"] for r in t])
        usual_med = _median(usual)
        peak = max(t, key=lambda r: (r["delay"], r["local_dt"]), default=None)
        wk = [r for r in lr if r["date"] >= week_from]
        by_hour = defaultdict(list)
        for r in wk:
            by_hour[r["hour"]].append(r["delay"])
        busiest = max(((h, _median(v)) for h, v in by_hour.items() if len(v) >= MIN_HOUR_READINGS),
                      key=lambda x: x[1], default=None)
        entry = {
            "today_slots": len(t),
            "today_median_delay": delay(today_med),
            "today_peak": None if peak is None else {"time": peak["local_dt"].strftime("%H:%M"),
                                                      "delay": delay(peak["delay"])},
            "today_slow_slots": sum(r["slow"] for r in t),
            "usual_median_delay_same_hours": delay(usual_med),
            "week_median_delay": delay(_median([r["delay"] for r in wk])),
            "week_slow_share_pct": round(100 * sum(r["slow"] for r in wk) / len(wk)) if wk else None,
            "week_busiest_hour": None if busiest is None else {"hour": hhmm(busiest[0]),
                                                                "median_delay": delay(busiest[1])},
            "busy_windows_for_today_kind": windows,
        }
        if today_med is not None and usual_med is not None:
            diff = today_med - usual_med
            entry["today_vs_usual"] = {"difference": delay(abs(diff)), "direction": direction(diff)}
        else:
            entry["today_vs_usual"] = None
        legs[leg] = entry

    # Worst leg: the larger median delay today, only when the two legs differ by at least NO_DIFFERENCE_S.
    medians = {leg: _median([r["delay"] for r in rows if r["leg"] == leg and r["date"] == today]) for leg in legs}
    medians = {leg: m for leg, m in medians.items() if m is not None}
    worst = None
    if len(medians) == 2 and abs(max(medians.values()) - min(medians.values())) >= NO_DIFFERENCE_S:
        worst = max(medians, key=medians.get)
    elif len(medians) == 1:
        worst = next(iter(medians))
    traffic = {
        "as_of_local": as_of.strftime("%H:%M"),
        "today_weekday": as_of.strftime("%A"),
        "day_kind": kind,
        "data_days": len(dates),
        "same_kind_days_in_history": len(kind_days),
        "busy_windows_ready": ready,
        "busy_windows_needs_more_days": 0 if ready else 7 - len(dates),
        "worst_leg_today_by_median": worst,
        "legs": legs,
        "road_class": road_class,
    }

    # Weather: today's slots, and the rain effect = delay in a rain slot minus the median dry delay of the same
    # local hour and leg, so the afternoon-rain / afternoon-peak overlap does not read as an effect of rain.
    wt = [w for w in weather if w["local_dt"].date() == today]
    rain_effect = {}
    for leg in legs:
        lr = [r for r in rows if r["leg"] == leg and r["rain"] is not None]
        dry = defaultdict(list)
        for r in lr:
            if not r["rain"]:
                dry[r["hour"]].append(r["delay"])
        deltas = [r["delay"] - _median(dry[r["hour"]]) for r in lr if r["rain"] and len(dry[r["hour"]]) >= 3]
        if len(deltas) >= MIN_RAIN_SLOTS:
            d = _median(deltas)
            rain_effect[leg] = {"rain_slots_compared": len(deltas), "days_of_data": len(dates),
                                "median_difference": delay(abs(d)), "direction": direction(d)}
        else:
            rain_effect[leg] = None
    weather_facts = {
        "slot_minutes": SLOT_MINUTES,
        "today_rain_slots": sum(1 for w in wt if w["rain"]),
        "today_slots_with_weather": len(wt),
        "raining_at_as_of": bool(wt and wt[-1]["rain"]) if wt else None,
        "today_temp_min_c": None if not wt else round(min(w["temperature_c"] for w in wt)),
        "today_temp_max_c": None if not wt else round(max(w["temperature_c"] for w in wt)),
        "rain_effect_by_leg": rain_effect,
        "rain_definition": "core rain_flag (precipitation)",
    }
    return traffic, weather_facts


def profile_facts(details, nearby, agg, themes, reviews):
    """Pure: query rows -> the site profile facts. Label counts only."""
    comp = {}
    for radius in (1000, 3000):
        rr = [n for n in nearby if n["radius_m"] == radius]
        comp[f"within_{radius}_m"] = {
            "radius_m": radius, "count": len(rr), "by_brand": dict(Counter(n["brand"] for n in rr).most_common()),
            "list_capped": len(rr) >= 19}   # 20 results incl. the site itself: a count at the cap is a lower bound
    nearest = min(nearby, key=lambda n: n["distance_m"], default=None)
    neg = [t for t in themes if t["sentiment"] in ("neg", "mixed") and t["label"]]   # one row per review and label
    return {
        "google_rating": details and details["rating"],
        "google_rating_count": details and details["user_rating_count"],
        "competitor_gas_stations": comp,
        "nearest_competitor": None if nearest is None else {"brand": nearest["brand"], "distance_m": nearest["distance_m"]},
        "places_nearby_counts": {"radius_m": 500, **{a["place_type"]: a["count"] for a in agg}},
        "review_sample": {
            "reviews_stored": reviews["n_reviews"], "reviews_with_text": reviews["n_text"],
            "complaint_theme_counts": dict(Counter(t["label"] for t in neg).most_common(3)),
            "note": "a small sample of the newest and most relevant Google reviews, not all reviews",
        },
    }


def facts_for_site(site_id, now=None):
    now = now or datetime.now(timezone.utc)
    site = run_query(SITE_SQL, {"site_id": site_id})[0]
    road_class = "toll" if "toll" in (site["road_type"] or "").lower() else "urban"
    p = {"site_id": site_id, "from_ts": now - timedelta(days=WINDOW_DAYS), "to_ts": now}
    rows = run_query(SLOTS_SQL, {**p, "gate_s": busy.GATE_S[road_class],
                                 "provisional_kmh": busy.PROVISIONAL_KMH[road_class]})
    weather = run_query(WEATHER_SQL, {**p, "tz": site["timezone"]})
    wide = {"site_id": site_id, "from_ts": now - timedelta(days=90)}
    details = (run_query(DETAILS_SQL, wide) or [None])[0]
    traffic, weather_facts = traffic_facts(rows, weather, road_class)
    profile = profile_facts(
        details, run_query(NEARBY_SQL, wide), run_query(AGG_SQL, {**wide, "types": POI_TYPES}),
        run_query(THEMES_SQL, {"site_id": site_id}), run_query(REVIEWS_SQL, {"site_id": site_id})[0])
    return {
        "site": {"id": site["site_id"], "name": site["name"], "city": site["city"], "road": site["road_name"],
                 "road_class": road_class},
        "traffic": traffic, "weather": weather_facts, "site_profile": profile,
        "sources": ["traffic.v_traffic (Routes API, demo stand-in for RMI)", "traffic.weather_slots (Google Weather)",
                    "traffic.places_* (Places)", "traffic.place_review_labels (Gemini labels)"],
    }


# ---------------------------------------------------------------------------------------------------------------
# 2. Gemini
# ---------------------------------------------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You write a short status note about one Pertamina fuel station (SPBU) in Indonesia for an operations dashboard. The user message is a JSON object of facts computed by SQL. You only phrase them.

Write 3 to 5 sentences of plain English, as a JSON list. Each sentence has a topic: traffic, weather or site_profile. Cover all three topics, traffic first.

Hard rules:
- Use only facts in the JSON. Never invent a number, time, place, brand or cause. If a fact is null, or a *_ready flag is false, say briefly that it is not available yet; use busy_windows_needs_more_days for the wait.
- Copy numbers as they appear. You may round to a whole number, but never add, subtract, divide, convert units or compute a share. Use digits for every number, never number words.
- Every delay is a {value, unit} pair, "s" for seconds or "min" for minutes: write it with its unit, as given ("about 18 s slower than usual", "about 2.4 min slower"). A value of 0 means "no delay". Times are 24-hour local times written HH:MM, as given. Do not write dates or month names; a weekday name may be used only if it is today_weekday.
- today_slow_slots counts today's 30-minute slots at moderate or worse. When it is 0, say the leg flowed freely today and do not present its largest delay as a peak or a slowdown.
- In the traffic topic, also give each leg's busy_windows_for_today_kind as start to end with the median delay (say "on typical {day_kind}s"), or say there is no usual busy window when busy_windows_ready is true and the list is empty.
- Say "slower" or "faster" only as given in a direction field. For rain, say the delay "coincided with" or "was associated with" rain, never that rain caused it, and give rain_slots_compared and days_of_data when you mention it (the comparison covers all days of data, not only today). When the direction is "no clear difference", say only that, without a number.
- Name the leg (approach is the road before the station, departure is the road after it) when you give a delay.
- For the site profile use the Google rating and the number of ratings (say "ratings", not "reviews"), competitor and nearby-place counts (give the radius; when list_capped is true the count is a lower bound, so say "at least"), and complaint theme counts. Say the themes come from reviews_with_text reviews, a small sample. Theme names are Indonesian category keys: translate them in plain English (antrian = queueing, pelayanan_petugas = staff service, bbm_kosong = fuel out of stock, kualitas_bbm = fuel quality, takaran = fill volume, pembayaran = payment, harga = price, kebersihan = cleanliness, toilet = toilets, fasilitas = facilities, keamanan_lalu_lintas = traffic safety at the entrance or exit, lainnya = other). A count is a number of reviews that raised the theme.
- No quotes, no advice, no forecast.\
"""


def response_schema():
    return {
        "type": "OBJECT",
        "properties": {"sentences": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {"topic": {"type": "STRING", "enum": ["traffic", "weather", "site_profile"]},
                           "text": {"type": "STRING"}},
            "required": ["topic", "text"], "propertyOrdering": ["topic", "text"]}}},
        "required": ["sentences"],
    }


def request_body(facts, thinking_level="LOW"):
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": "Facts:\n" + json.dumps(facts, ensure_ascii=False)}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                             "responseSchema": response_schema()},
    }
    if thinking_level:
        body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": thinking_level}
    return body


def get_key():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    out = subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest", "--secret=gemini-api-key",
         f"--project={KEY_SECRET_PROJECT}", f"--billing-project={PROJECT}"], capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        sys.exit("GEMINI_API_KEY is not set and the gcloud secret fetch failed: " + out.stderr.strip()[:200])
    return out.stdout.strip()


def call_gemini(key, facts, thinking_level="LOW"):
    """Returns (sentences, usage, seconds, error). The error is a short code, never a body or the key."""
    t0 = time.monotonic()
    data, err = httpjson.request_json("POST", URL, {"x-goog-api-key": key}, request_body(facts, thinking_level),
                                      secret=key, attempts=3, timeout=120)
    seconds = round(time.monotonic() - t0, 2)
    if err:
        return None, None, seconds, err.split(":", 1)[0]
    cands = data.get("candidates") or []
    if not cands or cands[0].get("finishReason") not in (None, "STOP"):
        return None, data.get("usageMetadata"), seconds, "no usable candidate"
    parts = (cands[0].get("content") or {}).get("parts") or []
    try:
        obj = json.loads("".join(p.get("text", "") for p in parts if not p.get("thought")))
        sentences = obj["sentences"]
    except (ValueError, KeyError, TypeError):
        return None, data.get("usageMetadata"), seconds, "output is not the expected JSON"
    return sentences, data.get("usageMetadata"), seconds, None


def cost_usd(usage):
    """Gemini API paid-tier cost of one call; thinking tokens bill as output."""
    if not usage:
        return None
    out = (usage.get("candidatesTokenCount") or 0) + (usage.get("thoughtsTokenCount") or 0)
    return (usage.get("promptTokenCount", 0) * PRICE_IN + out * PRICE_OUT) / 1e6


# ---------------------------------------------------------------------------------------------------------------
# 3. Validator (pure)
# ---------------------------------------------------------------------------------------------------------------

TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")
NUM_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
NUMBER_WORDS = re.compile(
    r"\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twice|double|doubled|half|triple|tripled|dozen"
    r"|hundred|thousand|percent)\b", re.I)
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
DIRECTION_WORDS = {"slower": ("slower", "longer"), "faster": ("faster", "quicker", "shorter")}


def _walk(value, numbers, strings, directions):
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        numbers.add(abs(float(value)))
    elif isinstance(value, str):
        strings.append(value)
    elif isinstance(value, dict):
        for k, v in value.items():
            if k == "direction" and isinstance(v, str):
                directions.add(v)
            _walk(v, numbers, strings, directions)
    elif isinstance(value, list):
        for v in value:
            _walk(v, numbers, strings, directions)


def facts_vocabulary(facts):
    """Numbers, HH:MM times, weekday names and direction words that the facts contain."""
    numbers, strings, directions = set(), [], set()
    _walk(facts, numbers, strings, directions)
    # Numbers inside the site's own name and road ("KM 57 A") are facts too, and nothing else in a string counts.
    for s in (facts.get("site") or {}).values():
        if isinstance(s, str):
            numbers.update(float(n.replace(",", "")) for n in NUM_RE.findall(s))
    times = set()
    for s in strings:
        for h, m in TIME_RE.findall(s):
            times.add(f"{int(h):02d}:{m}")
    days = {d for d in WEEKDAYS if any(d in s for s in strings)}
    return numbers, times, days, directions


def number_match(token, numbers):
    """'exact', 'rounded' or None. A token matches a fact when it equals it, or is the fact rounded to the token's own
    number of decimals. Sign is ignored: the facts carry a direction word instead."""
    text = token.replace(",", "")
    value = float(text)
    decimals = len(text.split(".")[1]) if "." in text else 0
    for fact in numbers:
        if abs(fact - value) < 1e-9:
            return "exact"
    for fact in numbers:
        if abs(round(fact, decimals) - value) < 1e-9:
            return "rounded"
    return None


def validate_sentence(text, vocab):
    numbers, times, days, directions = vocab
    problems, matches = [], []
    for h, m in TIME_RE.findall(text):
        t = f"{int(h):02d}:{m}"
        if t not in times:
            problems.append(f"time {t} is not in the facts")
    rest = TIME_RE.sub(" ", text)
    for token in NUM_RE.findall(rest):
        how = number_match(token, numbers)
        if how is None:
            problems.append(f"number {token} is not in the facts")
        else:
            matches.append({"number": token, "match": how})
    for w in NUMBER_WORDS.findall(rest):
        problems.append(f"spelled-out number or share word '{w}'")
    for d in WEEKDAYS:
        if re.search(rf"\b{d}\b", text) and d not in days:
            problems.append(f"weekday {d} is not in the facts")
    for m in MONTHS:
        if re.search(rf"\b{m}\b", text):
            problems.append(f"date word {m}")
    for direction_value, words in DIRECTION_WORDS.items():
        for w in words:
            if re.search(rf"\b{w}\b", text, re.I) and direction_value not in directions:
                problems.append(f"direction '{w}' not given by the facts")
    if re.search(r"[\"“”]", text):
        problems.append("quoted text")
    return {"ok": not problems, "problems": problems, "number_matches": matches}


def validate_summary(sentences, facts):
    """Pure. `sentences` is a list of {topic, text}. Returns {ok, count_ok, sentences: [... + ok, problems]}."""
    vocab = facts_vocabulary(facts)
    out = []
    for s in sentences or []:
        text = s.get("text", "") if isinstance(s, dict) else ""
        out.append({"topic": s.get("topic") if isinstance(s, dict) else None, "text": text,
                    **validate_sentence(text, vocab)})
    count_ok = 3 <= len(out) <= 5
    return {"ok": count_ok and bool(out) and all(s["ok"] for s in out), "count_ok": count_ok, "sentences": out}


# ---------------------------------------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--site", action="append", required=True, help="site_id; repeat for several sites")
    ap.add_argument("--facts-only", action="store_true", help="build and save the facts; no Gemini call")
    ap.add_argument("--thinking-level", default="LOW", help="LOW, MEDIUM, HIGH or '' to leave the model default")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out_dir or os.path.join(ROOT, "out", "ai_summaries", stamp)
    os.makedirs(out_dir, exist_ok=True)
    key = None if args.facts_only else get_key()
    for site_id in args.site:
        t0 = time.monotonic()
        facts = facts_for_site(site_id)
        facts_seconds = round(time.monotonic() - t0, 2)
        result = {"site_id": site_id, "generated_at": datetime.now(timezone.utc).isoformat(), "model": MODEL,
                  "prompt_version": PROMPT_VERSION, "facts": facts, "facts_query_seconds": facts_seconds}
        if key:
            sentences, usage, seconds, err = call_gemini(key, facts, args.thinking_level or None)
            result.update({"gemini_seconds": seconds, "usage": usage, "cost_usd": cost_usd(usage), "error": err})
            if sentences is not None:
                result["validation"] = validate_summary(sentences, facts)
        with open(os.path.join(out_dir, f"{site_id}.json"), "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)
        v = result.get("validation")
        print(f"{site_id}: facts {facts_seconds}s"
              + (f", gemini {result['gemini_seconds']}s, error {result['error']}" if key else "")
              + (f", validation ok={v['ok']}" if v else ""))
    print(f"wrote {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
