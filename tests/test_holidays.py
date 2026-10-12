"""Holiday classification. No BigQuery."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard.api.holidays import is_weekend, sql_date_list  # noqa: E402


class HolidaysTest(unittest.TestCase):
    def test_independence_day_is_weekend(self):
        # Monday 17 Aug 2026 is a national holiday, so it counts as a weekend day.
        self.assertEqual(date(2026, 8, 17).weekday(), 0)
        self.assertTrue(is_weekend(date(2026, 8, 17)))

    def test_cuti_bersama_imlek_is_weekday(self):
        # Monday 16 Feb 2026 is collective leave, not a public holiday.
        self.assertEqual(date(2026, 2, 16).weekday(), 0)
        self.assertFalse(is_weekend(date(2026, 2, 16)))

    def test_saturday_is_weekend_and_a_plain_monday_is_not(self):
        self.assertTrue(is_weekend(date(2026, 8, 15)))  # Saturday
        self.assertFalse(is_weekend(date(2026, 8, 18)))  # Tuesday after Independence Day

    def test_sql_lists_the_holiday_and_omits_cuti_bersama(self):
        sql = sql_date_list()
        self.assertIn("DATE '2026-08-17'", sql)
        self.assertNotIn("DATE '2026-02-16'", sql)


if __name__ == "__main__":
    unittest.main()
