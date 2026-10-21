"""AI summaries per SPBU, grounded on facts built in SQL (docs/plans/ai-summaries.md). Moved here from the
prototype scripts/ai_summary_prototype.py, which now imports this module, so the dashboard and the prototype
share one copy of the queries, prompt and validator.

  1. facts_for_site   read-only BigQuery queries, run in parallel -> a small facts dict, one key per topic (bands
                      and busy windows use the same rules as busy.py).
  2. call_gemini      the facts go to the Gemini API (same model and request shape as reviews_job/gemini.py);
                      the answer is 4-6 sentences as JSON, each tagged with one topic.
  3. validate_summary pure function: every number, time, weekday and direction word in a sentence must come from the
                      facts (or be a stated rounding of a fact), the count is 4-6 and every topic has a sentence.

Review text, gists and author names never leave BigQuery: the facts carry label counts only.
"""
import json
import os
import re
import statistics
import time
from collections import Counter, defaultdict
from datetime import timedelta

from . import bq, busy, holidays, httpjson

MODEL = "gemini-3.8-flash"   # same pin as reviews_job/gemini.py; copied, not imported, so a prompt change there does not move this
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
PROMPT_VERSION = "s5"        # s5 (2026-10-21): topics traffic/weather/places/review_themes, 4-6 sentences, one per topic at least
# s4 (2026-10-14): prototype; topics traffic/weather/site_profile, 3-5 sentences
TOPICS = ("traffic", "weather", "places", "review_themes")   # page order of the four cards
MIN_SENTENCES, MAX_SENTENCES = 4, 6
GEMINI_ATTEMPTS = 2          # a viewer is waiting: one retry on 429/5xx, not the labeller's five
GEMINI_TIMEOUT = 60
WINDOW_DAYS = 28             # same query window as /api/traffic/typical-day
WEEK_DAYS = 7
SLOT_MINUTES = 30
MIN_RAIN_SLOTS = 8           # below this a rain effect is not reported
MIN_HOUR_READINGS = 4        # same "thin hour" cut as the typical-day profile
POI_TYPES = ["restaurant", "cafe", "lodging", "convenience_store", "school", "shopping_mall"]

# Tables each card's facts come from (the "Source data" disclosure).
SOURCES = {
    "traffic": ["traffic.v_traffic (Routes API, demo stand-in for RMI)"],
    "weather": ["traffic.weather_slots (Google Weather, core rain_flag)", "traffic.v_traffic (delays in rain slots)"],
    "places": ["traffic.places_details", "traffic.places_nearby", "traffic.places_aggregate (Places)"],
    "review_themes": ["traffic.place_review_labels (Gemini labels)", "traffic.v_place_reviews (counts only)"],
}

# ---------------------------------------------------------------------------------------------------------------
# 1. Facts (SQL)
# ---------------------------------------------------------------------------------------------------------------

# One row per slot per leg. `slow` is the same moderate-or-worse test as the busy-hour query of the dashboard.
SLOTS_SQL = f"""
SELECT r.leg, t.slot_time, DATETIME(t.slot_time, s.timezone) AS local_dt, t.delay_s, t.baseline_samples,
  IF({busy.slow_count_sql()}, 1, 0) AS slow
FROM {bq.table("v_traffic")} AS t
JOIN {bq.table("routes")} AS r ON r.selected_route_id = t.selected_route_id AND r.active
JOIN {bq.table("sites")} AS s ON s.site_id = r.site_id
WHERE t.slot_time >= @from_ts AND t.slot_time <= @to_ts AND r.site_id = @site_id AND t.delay_s IS NOT NULL
ORDER BY t.slot_time, r.leg"""

# Rain is the core rain_flag (precipitation), WeatherNext-compatible. demo_rain_flag is demo-only and stays out of the facts.
WEATHER_SQL = f"""
SELECT slot_time, DATETIME(slot_time, @tz) AS local_dt, temperature_c,
  IFNULL(rain_flag, FALSE) AS rain
FROM {bq.table("weather_slots")}
WHERE site_id = @site_id AND slot_time >= @from_ts AND slot_time <= @to_ts
QUALIFY ROW_NUMBER() OVER (PARTITION BY slot_time ORDER BY fetched_at DESC) = 1
ORDER BY slot_time"""

DETAILS_SQL = f"""
SELECT rating, user_rating_count FROM {bq.table("places_details")}
WHERE site_id = @site_id AND fetched_at >= @from_ts ORDER BY fetched_at DESC LIMIT 1"""

# Latest run, by the rule in data-schema.md: run_id of the row with the greatest fetched_at.
NEARBY_SQL = f"""
WITH latest AS (
  SELECT run_id FROM {bq.table("places_nearby")} WHERE fetched_at >= @from_ts ORDER BY fetched_at DESC LIMIT 1)
SELECT n.radius_m, n.brand, n.distance_m
FROM {bq.table("places_nearby")} AS n JOIN latest USING (run_id)
WHERE n.site_id = @site_id AND n.fetched_at >= @from_ts
  AND n.place_id != (SELECT place_id FROM {bq.table("sites")} WHERE site_id = @site_id)"""

# The place types are constants (bq.query takes scalar parameters only), so they are inlined.
AGG_SQL = f"""
WITH latest AS (
  SELECT run_id FROM {bq.table("places_aggregate")} WHERE fetched_at >= @from_ts ORDER BY fetched_at DESC LIMIT 1)
SELECT place_type, count FROM {bq.table("places_aggregate")} JOIN latest USING (run_id)
WHERE site_id = @site_id AND fetched_at >= @from_ts AND radius_m = 500
  AND place_type IN ({", ".join(f"'{t}'" for t in POI_TYPES)})"""

# Labels only (gemini method). The text, the gist and the author never enter the facts.
THEMES_SQL = f"""
SELECT l.sentiment, label
FROM {bq.table("place_review_labels")} AS l LEFT JOIN UNNEST(l.labels) AS label
WHERE l.site_id = @site_id AND l.method = 'gemini'
QUALIFY ROW_NUMBER() OVER (PARTITION BY l.review_key, label ORDER BY l.labeled_at DESC) = 1"""

REVIEWS_SQL = f"""
SELECT COUNT(*) AS n_reviews, COUNTIF(text IS NOT NULL) AS n_text
FROM {bq.table("v_place_reviews")} WHERE site_id = @site_id"""


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
    temps = [w["temperature_c"] for w in wt if w["temperature_c"] is not None]   # temperature_c is nullable
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
        "today_temp_min_c": round(min(temps)) if temps else None,
        "today_temp_max_c": round(max(temps)) if temps else None,
        "rain_effect_by_leg": rain_effect,
        "rain_definition": "core rain_flag (precipitation)",
    }
    return traffic, weather_facts


def places_facts(details, nearby, agg):
    """Pure: query rows -> the places facts (rating, competitors, nearby-place counts)."""
    comp = {}
    for radius in (1000, 3000):
        rr = [n for n in nearby if n["radius_m"] == radius]
        comp[f"within_{radius}_m"] = {
            "radius_m": radius, "count": len(rr), "by_brand": dict(Counter(n["brand"] for n in rr).most_common()),
            "list_capped": len(rr) >= 19}   # 20 results incl. the site itself: a count at the cap is a lower bound
    nearest = min(nearby, key=lambda n: n["distance_m"], default=None)
    return {
        "google_rating": details and details["rating"],
        "google_rating_count": details and details["user_rating_count"],
        "competitor_gas_stations": comp,
        "nearest_competitor": None if nearest is None else {"brand": nearest["brand"], "distance_m": nearest["distance_m"]},
        "places_nearby_counts": {"radius_m": 500, **{a["place_type"]: a["count"] for a in agg}},
    }


def review_theme_facts(themes, reviews):
    """Pure: label rows and the review counts row -> the review-theme facts. Label counts only."""
    neg = [t for t in themes if t["sentiment"] in ("neg", "mixed") and t["label"]]   # one row per review and label
    return {
        "reviews_stored": reviews["n_reviews"], "reviews_with_text": reviews["n_text"],
        "complaint_theme_counts": dict(Counter(t["label"] for t in neg).most_common(3)),
        "note": "a small sample of the newest and most relevant Google reviews, not all reviews",
    }


def facts_for_site(site, now):
    """`site` is an /api/sites entry (site_id, name, city, road_name, road_class, timezone). The seven queries run
    in parallel. Returns (facts, as_of): as_of is the latest traffic slot in the facts (UTC), None without traffic."""
    site_id, road_class = site["site_id"], site.get("road_class") or "urban"
    p = {"site_id": site_id, "from_ts": now - timedelta(days=WINDOW_DAYS), "to_ts": now}
    wide = {"site_id": site_id, "from_ts": now - timedelta(days=90)}
    rows, weather, details, nearby, agg, themes, reviews = bq.query_all(
        (SLOTS_SQL, {**p, "gate_s": busy.GATE_S[road_class], "provisional_kmh": busy.PROVISIONAL_KMH[road_class]}),
        (WEATHER_SQL, {**p, "tz": site["timezone"]}),
        (DETAILS_SQL, wide),
        (NEARBY_SQL, wide),
        (AGG_SQL, wide),
        (THEMES_SQL, {"site_id": site_id}),
        (REVIEWS_SQL, {"site_id": site_id}),
    )
    as_of = max((r["slot_time"] for r in rows), default=None)
    traffic, weather_facts = traffic_facts(rows, weather, road_class)
    facts = {
        "site": {"id": site_id, "name": site["name"], "city": site["city"], "road": site["road_name"],
                 "road_class": road_class},
        "traffic": traffic,
        "weather": weather_facts,
        "places": places_facts((details or [None])[0], nearby, agg),
        "review_themes": review_theme_facts(themes, reviews[0]),   # an aggregate without GROUP BY always returns a row
    }
    return facts, as_of


# ---------------------------------------------------------------------------------------------------------------
# 2. Gemini
# ---------------------------------------------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You write a short status note about one Pertamina fuel station (SPBU) in Indonesia for an operations dashboard. The user message is a JSON object of facts computed by SQL. You only phrase them.

Write 4 to 6 sentences of plain English, as a JSON list. Each sentence has one topic: traffic, weather, places or review_themes, and covers that topic only (each topic is shown in its own section of the dashboard). Write at least one sentence per topic, in that order.

Hard rules:
- Use only facts in the JSON. Never invent a number, time, place, brand or cause. If a fact is null, or a *_ready flag is false, say briefly that it is not available yet; use busy_windows_needs_more_days for the wait.
- Copy numbers as they appear. You may round to a whole number, but never add, subtract, divide, convert units or compute a share. Use digits for every number, never number words.
- Every delay is a {value, unit} pair, "s" for seconds or "min" for minutes: write it with its unit, as given ("about 18 s slower than usual", "about 2.4 min slower"). A value of 0 means "no delay". Times are 24-hour local times written HH:MM, as given. Do not write dates or month names; a weekday name may be used only if it is today_weekday.
- today_slow_slots counts today's 30-minute slots at moderate or worse. When it is 0, say the leg flowed freely today and do not present its largest delay as a peak or a slowdown.
- In the traffic topic, also give each leg's busy_windows_for_today_kind as start to end with the median delay (say "on typical {day_kind}s"), or say there is no usual busy window when busy_windows_ready is true and the list is empty.
- Say "slower" or "faster" only as given in a direction field. For rain, say the delay "coincided with" or "was associated with" rain, never that rain caused it, and give rain_slots_compared and days_of_data when you mention it (the comparison covers all days of data, not only today). When the direction is "no clear difference", say only that, without a number.
- Name the leg (approach is the road before the station, departure is the road after it) when you give a delay.
- In the places topic use the Google rating and the number of ratings (say "ratings", not "reviews"), and the competitor and nearby-place counts (give the radius; when list_capped is true the count is a lower bound, so say "at least").
- In the review_themes topic give the complaint theme counts and say they come from reviews_with_text reviews, a small sample; when complaint_theme_counts is empty, say the sample raised no complaint theme. Theme names are Indonesian category keys: translate them in plain English (antrian = queueing, pelayanan_petugas = staff service, bbm_kosong = fuel out of stock, kualitas_bbm = fuel quality, takaran = fill volume, pembayaran = payment, harga = price, kebersihan = cleanliness, toilet = toilets, fasilitas = facilities, keamanan_lalu_lintas = traffic safety at the entrance or exit, lainnya = other). A count is a number of reviews that raised the theme.
- No quotes, no advice, no forecast.\
"""


def response_schema():
    return {
        "type": "OBJECT",
        "properties": {"sentences": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {"topic": {"type": "STRING", "enum": list(TOPICS)},
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


def api_key():
    """GEMINI_API_KEY from the environment (Cloud Run mounts Secret Manager `gemini-api-key` there); None when unset."""
    return os.environ.get("GEMINI_API_KEY", "").strip() or None


def parse_response(data):
    """Gemini response body -> (sentences, error). The error is a short code, never a body."""
    cands = data.get("candidates") or []
    if not cands or cands[0].get("finishReason") not in (None, "STOP"):
        return None, "no usable candidate"
    parts = (cands[0].get("content") or {}).get("parts") or []
    try:
        obj = json.loads("".join(p.get("text", "") for p in parts if not p.get("thought")))
        sentences = obj["sentences"]
    except (ValueError, KeyError, TypeError):
        return None, "output is not the expected JSON"
    if not isinstance(sentences, list):
        return None, "output is not the expected JSON"
    return sentences, None


def call_gemini(key, facts, thinking_level="LOW"):
    """One generateContent call. Returns {sentences, usage, model_version, latency_ms, error}; `error` is a short
    code (never a body or the key) and `sentences` is None whenever it is set."""
    t0 = time.monotonic()
    data, err = httpjson.request_json("POST", URL, {"x-goog-api-key": key}, request_body(facts, thinking_level),
                                      secret=key, attempts=GEMINI_ATTEMPTS, timeout=GEMINI_TIMEOUT)
    latency_ms = round((time.monotonic() - t0) * 1000)
    if err:
        return {"sentences": None, "usage": None, "model_version": None, "latency_ms": latency_ms,
                "error": err.split(":", 1)[0]}
    sentences, err = parse_response(data)
    return {"sentences": sentences, "usage": data.get("usageMetadata"), "model_version": data.get("modelVersion"),
            "latency_ms": latency_ms, "error": err}


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
    """Pure. `sentences` is a list of {topic, text}. The gate: every sentence passes, 4-6 sentences, and every topic
    has at least one. Returns {ok, count_ok, missing_topics, sentences: [... + ok, problems, number_matches]}."""
    vocab = facts_vocabulary(facts)
    out = []
    for s in sentences or []:
        text = s.get("text", "") if isinstance(s, dict) else ""
        topic = s.get("topic") if isinstance(s, dict) else None
        checked = validate_sentence(text if isinstance(text, str) else "", vocab)
        if topic not in TOPICS:
            checked["problems"].insert(0, f"topic {topic!r} is not one of {', '.join(TOPICS)}")
            checked["ok"] = False
        out.append({"topic": topic, "text": text, **checked})
    count_ok = MIN_SENTENCES <= len(out) <= MAX_SENTENCES
    missing = [t for t in TOPICS if not any(s["topic"] == t for s in out)]
    return {"ok": count_ok and not missing and all(s["ok"] for s in out), "count_ok": count_ok,
            "missing_topics": missing, "sentences": out}
