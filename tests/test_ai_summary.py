"""Unit tests for dashboard/api/ai_summary.py (the prototype's pure parts, moved there): validator, delay format,
traffic facts, the frozen-facts set and the prompt/parse path. Gemini is mocked: no network."""
import json
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dashboard.api import ai_summary as ai  # noqa: E402

with open(os.path.join(ROOT, "tests", "fixtures", "ai_summary_frozen.json")) as f:
    FROZEN = json.load(f)

FACTS = {
    "site": {"id": "KM57A", "name": "SPBU Rest Area KM 57 A"},
    "traffic": {
        "today_weekday": "Wednesday", "as_of_local": "15:00", "data_days": 8,
        "legs": {"approach": {
            "today_slow_slots": 3,
            "today_peak": {"time": "08:00", "delay": {"value": 25, "unit": "s"}},
            "today_vs_usual": {"difference": {"value": 6, "unit": "s"}, "direction": "slower"},
            "busy_windows_for_today_kind": [{"start": "17:00", "end": "19:00",
                                             "median_delay": {"value": 2.4, "unit": "min"}, "direction": "slower"}]}},
    },
    "places": {"google_rating": 4.4, "google_rating_count": 1656},
}


def check(text):
    return ai.validate_summary([{"topic": "traffic", "text": text}] * 4, FACTS)["sentences"][0]


class ValidatorTest(unittest.TestCase):
    def test_numbers_and_times_from_facts_pass(self):
        r = check("At 08:00 the approach leg peaked at 25 s, with 3 slow slots and a 17:00 to 19:00 window of 2.4 min.")
        self.assertTrue(r["ok"], r["problems"])

    def test_invented_number_fails(self):
        self.assertIn("number 7 is not in the facts", check("The approach had 7 slow slots.")["problems"])

    def test_invented_time_fails(self):
        self.assertIn("time 18:30 is not in the facts", check("The window starts at 18:30.")["problems"])

    def test_rounding_is_allowed_and_reported(self):
        r = check("The busy window is about 2 min slower.")
        self.assertTrue(r["ok"])
        self.assertEqual(r["number_matches"], [{"number": "2", "match": "rounded"}])

    def test_wrong_rounding_fails(self):
        self.assertFalse(check("The busy window is about 5 min slower.")["ok"])

    def test_number_words_weekdays_months_quotes_fail(self):
        self.assertFalse(check("Delays doubled at the approach.")["ok"])
        self.assertFalse(check("On Tuesday the approach was slower.")["ok"])
        self.assertFalse(check("On 14 October the approach was slower.")["ok"])
        self.assertFalse(check('One reviewer wrote "rude".')["ok"])
        self.assertTrue(check("On Wednesday the approach was slower.")["ok"])

    def test_direction_word_needs_a_matching_fact(self):
        self.assertTrue(check("The approach was slower than usual.")["ok"])
        self.assertFalse(check("The approach was faster than usual.")["ok"])

    def test_numbers_in_the_site_name_are_facts(self):
        self.assertTrue(check("SPBU Rest Area KM 57 A has a 4.4 rating.")["ok"])

    def test_sign_is_ignored_and_thousands_separator_is_read(self):
        self.assertTrue(check("It has 1,656 ratings.")["ok"])

    def test_sentence_count_must_be_four_to_six_with_every_topic(self):
        one_each = [{"topic": t, "text": "The approach had 3 slow slots."} for t in ai.TOPICS]
        self.assertTrue(ai.validate_summary(one_each, FACTS)["ok"])
        self.assertTrue(ai.validate_summary(one_each + one_each[:2], FACTS)["ok"])
        self.assertFalse(ai.validate_summary(one_each[:3], FACTS)["ok"])
        self.assertFalse(ai.validate_summary(one_each + one_each[:3], FACTS)["ok"])
        self.assertFalse(ai.validate_summary([], FACTS)["ok"])
        four_traffic = [{"topic": "traffic", "text": "The approach had 3 slow slots."}] * 4
        r = ai.validate_summary(four_traffic, FACTS)
        self.assertFalse(r["ok"])
        self.assertTrue(r["count_ok"])
        self.assertEqual(r["missing_topics"], ["weather", "places", "review_themes"])

    def test_malformed_sentences_fail_without_raising(self):
        r = ai.validate_summary(["not a dict", {"topic": "weather", "text": 3}, {"text": "x"}, {"topic": "places"}], FACTS)
        self.assertFalse(r["ok"])
        self.assertFalse(r["sentences"][0]["ok"])


class FrozenFactsTest(unittest.TestCase):
    """The frozen set (tests/fixtures/ai_summary_frozen.json): each model answer gets its expected gate result."""

    def test_every_case(self):
        for case in FROZEN["cases"]:
            with self.subTest(case["name"]):
                r = ai.validate_summary(case["sentences"], FROZEN["facts"][case["facts"]])
                problems = [p for s in r["sentences"] for p in s["problems"]]
                self.assertEqual(r["ok"], case["ok"], problems)
                self.assertEqual(r["count_ok"], case["count_ok"])
                self.assertEqual(r["missing_topics"], case["missing_topics"])
                self.assertEqual(sorted(problems), sorted(case["problems"]))

    def test_passing_cases_report_how_each_number_matched(self):
        r = ai.validate_summary(FROZEN["cases"][0]["sentences"], FROZEN["facts"]["urban"])
        kinds = {m["match"] for s in r["sentences"] for m in s["number_matches"]}
        self.assertEqual(kinds, {"exact"})


def gemini_body(sentences, finish="STOP", model_version="gemini-3.8-flash-001"):
    return {"candidates": [{"finishReason": finish, "content": {"parts": [
        {"text": "thinking", "thought": True}, {"text": json.dumps({"sentences": sentences})}]}}],
        "usageMetadata": {"promptTokenCount": 1900, "candidatesTokenCount": 300}, "modelVersion": model_version}


class PromptAndParseTest(unittest.TestCase):
    def test_request_body_carries_the_prompt_facts_and_topic_schema(self):
        facts = FROZEN["facts"]["urban"]
        body = ai.request_body(facts)
        self.assertEqual(body["systemInstruction"]["parts"][0]["text"], ai.SYSTEM_PROMPT)
        self.assertEqual(json.loads(body["contents"][0]["parts"][0]["text"].removeprefix("Facts:\n")), facts)
        item = body["generationConfig"]["responseSchema"]["properties"]["sentences"]["items"]
        self.assertEqual(item["properties"]["topic"]["enum"], ["traffic", "weather", "places", "review_themes"])
        self.assertEqual(body["generationConfig"]["temperature"], 0)
        self.assertEqual(body["generationConfig"]["thinkingConfig"], {"thinkingLevel": "LOW"})
        for topic in ai.TOPICS:
            self.assertIn(topic, ai.SYSTEM_PROMPT)
        self.assertIn("4 to 6 sentences", ai.SYSTEM_PROMPT)

    def test_facts_carry_no_review_text(self):
        keys = set()

        def walk(v):
            if isinstance(v, dict):
                keys.update(v)
                for x in v.values():
                    walk(x)
        walk(FROZEN["facts"]["urban"])
        self.assertFalse(keys & {"text", "gist", "author_name", "raw"})

    def test_call_gemini_parses_a_canned_answer_and_the_gate_passes(self):
        case = FROZEN["cases"][0]
        with mock.patch.object(ai.httpjson, "request_json", return_value=(gemini_body(case["sentences"]), None)) as rq:
            g = ai.call_gemini("k3y", FROZEN["facts"]["urban"])
        method, url, headers, body = rq.call_args.args
        self.assertEqual((method, url, headers), ("POST", ai.URL, {"x-goog-api-key": "k3y"}))
        self.assertEqual(rq.call_args.kwargs["secret"], "k3y")
        self.assertIsNone(g["error"])
        self.assertEqual(g["sentences"], case["sentences"])
        self.assertEqual(g["model_version"], "gemini-3.8-flash-001")
        self.assertEqual(g["usage"]["promptTokenCount"], 1900)
        self.assertTrue(ai.validate_summary(g["sentences"], FROZEN["facts"]["urban"])["ok"])

    def test_call_gemini_reports_short_codes_on_failure(self):
        with mock.patch.object(ai.httpjson, "request_json", return_value=(None, "HTTP 429: quota body")):
            g = ai.call_gemini("k", {})
        self.assertEqual((g["sentences"], g["error"]), (None, "HTTP 429"))
        with mock.patch.object(ai.httpjson, "request_json", return_value=(gemini_body([], finish="SAFETY"), None)):
            self.assertEqual(ai.call_gemini("k", {})["error"], "no usable candidate")
        bad = {"candidates": [{"content": {"parts": [{"text": "not json"}]}}]}
        with mock.patch.object(ai.httpjson, "request_json", return_value=(bad, None)):
            g = ai.call_gemini("k", {})
        self.assertEqual((g["sentences"], g["error"]), (None, "output is not the expected JSON"))
        listless = {"candidates": [{"content": {"parts": [{"text": '{"sentences": "x"}'}]}}]}
        with mock.patch.object(ai.httpjson, "request_json", return_value=(listless, None)):
            self.assertEqual(ai.call_gemini("k", {})["error"], "output is not the expected JSON")

    def test_api_key_comes_from_the_environment_only(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": " k \n"}):
            self.assertEqual(ai.api_key(), "k")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(ai.api_key())


class DelayFormatTest(unittest.TestCase):
    def test_matches_dashboard_format_delay(self):
        self.assertEqual(ai.delay(16.4), {"value": 16, "unit": "s"})
        self.assertEqual(ai.delay(59.4), {"value": 59, "unit": "s"})
        self.assertEqual(ai.delay(78), {"value": 1.3, "unit": "min"})
        self.assertEqual(ai.delay(-2), {"value": 0, "unit": "s"})
        self.assertIsNone(ai.delay(None))


def slot_rows(days, delay_for):
    """Rows for one leg, 48 slots a day, `days` local dates ending 2026-10-14 15:00 (UTC+7 already applied)."""
    rows = []
    end = datetime(2026, 10, 14, 15, 0)
    start = datetime(2026, 10, 14) - timedelta(days=days - 1)
    t = start
    while t <= end:
        d = delay_for(t)
        rows.append({"leg": "approach", "slot_time": t - timedelta(hours=7), "local_dt": t, "delay_s": d,
                     "baseline_samples": 336, "slow": 1 if d >= 40 else 0})
        t += timedelta(minutes=30)
    return rows


class TrafficFactsTest(unittest.TestCase):
    def test_busy_window_and_today_vs_usual(self):
        # 17:00-18:59 is slow every day (60 s); today's slots before that are 10 s, the usual ones 10 s too.
        rows = slot_rows(8, lambda t: 60 if t.hour in (17, 18) else 10)
        traffic, weather = ai.traffic_facts(rows, [], "urban")
        leg = traffic["legs"]["approach"]
        self.assertTrue(traffic["busy_windows_ready"])
        self.assertEqual(leg["busy_windows_for_today_kind"],
                         [{"start": "17:00", "end": "19:00", "median_delay": {"value": 1.0, "unit": "min"},
                           "direction": "slower"}])
        self.assertEqual(leg["today_vs_usual"], {"difference": {"value": 0, "unit": "s"}, "direction": "no clear difference"})
        self.assertEqual(leg["today_slow_slots"], 0)

    def test_windows_stay_empty_until_seven_dates(self):
        rows = slot_rows(5, lambda t: 60 if t.hour in (17, 18) else 10)
        traffic, _ = ai.traffic_facts(rows, [], "urban")
        self.assertFalse(traffic["busy_windows_ready"])
        self.assertEqual(traffic["busy_windows_needs_more_days"], 2)
        self.assertEqual(traffic["legs"]["approach"]["busy_windows_for_today_kind"], [])

    def test_rain_effect_needs_enough_rain_slots_and_compares_the_same_hour(self):
        rows = slot_rows(8, lambda t: 10)
        weather = [{"slot_time": r["slot_time"], "local_dt": r["local_dt"], "temperature_c": 30.0,
                    "rain": r["local_dt"].hour == 12 and r["local_dt"].date() >= datetime(2026, 10, 12).date()}
                   for r in rows]
        _, w = ai.traffic_facts(rows, weather, "urban")
        self.assertIsNone(w["rain_effect_by_leg"]["approach"])   # 3 days x 2 slots = 6 rain slots, below 8
        self.assertEqual(w["today_rain_slots"], 2)
        # make the rain slots 30 s slower than the dry slots of the same hour; 4 days -> 8 slots
        for r in rows:
            if r["local_dt"].hour == 12 and r["local_dt"].date() >= datetime(2026, 10, 11).date():
                r["delay_s"] = 40
        weather = [{**wt, "rain": wt["local_dt"].hour == 12 and wt["local_dt"].date() >= datetime(2026, 10, 11).date()}
                   for wt in weather]
        _, w = ai.traffic_facts(rows, weather, "urban")
        self.assertEqual(w["rain_effect_by_leg"]["approach"],
                         {"rain_slots_compared": 8, "days_of_data": 8, "median_difference": {"value": 30, "unit": "s"},
                          "direction": "slower"})


if __name__ == "__main__":
    unittest.main()
