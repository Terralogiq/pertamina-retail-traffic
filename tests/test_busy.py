"""Busy-hour rule. No BigQuery."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard.api.busy import hour_is_busy, peak_windows  # noqa: E402


def _hours(busy_at):
    return [
        {"hour": hour, "busy": hour in busy_at, "median_delay_s": 40.0 if hour in busy_at else 0.0}
        for hour in range(24)
    ]


class BusyHourTest(unittest.TestCase):
    def test_three_of_four_moderate_readings_need_a_30s_median(self):
        # 1.6× and 25 s is moderate on an urban road (gate 20 s) and free flow on a toll road (gate 30 s).
        readings = [(1.6, 25), (1.6, 25), (1.6, 25), (1.2, 10)]
        self.assertTrue(hour_is_busy(readings, 40))
        self.assertFalse(hour_is_busy(readings, 20))
        self.assertFalse(hour_is_busy(readings, 40, road_class="toll"))

    def test_exactly_half_is_busy_when_the_median_clears_30s(self):
        readings = [(1.6, 25), (1.6, 25), (1.0, 5), (1.0, 5)]
        self.assertTrue(hour_is_busy(readings, 30))
        self.assertFalse(hour_is_busy([(1.6, 25), (1.0, 5), (1.0, 5), (1.0, 5)], 40))

    def test_windows_merge_consecutive_hours_and_wrap_midnight(self):
        self.assertEqual(peak_windows(_hours({7, 8})), [{"start_hour": 7, "end_hour": 9, "median_delay_s": 40.0}])
        wrapped = peak_windows(_hours({0, 23}))
        self.assertEqual(wrapped, [{"start_hour": 23, "end_hour": 1, "median_delay_s": 40.0}])
        self.assertEqual(peak_windows(_hours(set())) , [])


if __name__ == "__main__":
    unittest.main()
