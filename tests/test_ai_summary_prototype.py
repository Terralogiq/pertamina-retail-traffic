"""Unit tests for the pure parts of scripts/ai_summary_prototype.py: validator, delay format, traffic facts. No network."""
import importlib.util
import os
import unittest
from datetime import datetime, timedelta, timezone

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
_spec = importlib.util.spec_from_file_location("ai_summary_prototype", os.path.join(SCRIPTS, "ai_summary_prototype.py"))
ai = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ai)

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
    "site_profile": {"google_rating": 4.4, "google_rating_count": 1656},
}


def check(text):
    return ai.validate_summary([{"topic": "traffic", "text": text}] * 3, FACTS)["sentences"][0]


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

    def test_sentence_count_must_be_three_to_five(self):
        two = [{"topic": "traffic", "text": "The approach had 3 slow slots."}] * 2
        self.assertFalse(ai.validate_summary(two, FACTS)["ok"])
        self.assertTrue(ai.validate_summary(two + two[:1], FACTS)["ok"])
        self.assertFalse(ai.validate_summary(two * 3, FACTS)["ok"])
        self.assertFalse(ai.validate_summary([], FACTS)["ok"])


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
