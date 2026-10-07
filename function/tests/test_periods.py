import unittest
from datetime import date

from l2_to_l3.periods import latest_complete_period, period_containing


class PeriodTests(unittest.TestCase):
    def test_periods_start_on_doy_1_9_17(self):
        self.assertEqual(period_containing(date(2025, 1, 1)), (date(2025, 1, 1), date(2025, 1, 8)))
        self.assertEqual(period_containing(date(2025, 1, 9)), (date(2025, 1, 9), date(2025, 1, 16)))
        # DOY 153..160
        self.assertEqual(period_containing(date(2025, 6, 3)), (date(2025, 6, 2), date(2025, 6, 9)))

    def test_last_period_of_year_is_truncated(self):
        self.assertEqual(period_containing(date(2025, 12, 30)), (date(2025, 12, 27), date(2025, 12, 31)))
        self.assertEqual(period_containing(date(2024, 12, 31)), (date(2024, 12, 26), date(2024, 12, 31)))

    def test_latest_complete_period(self):
        self.assertEqual(latest_complete_period(date(2025, 6, 2)), (date(2025, 5, 25), date(2025, 6, 1)))
        self.assertEqual(latest_complete_period(date(2025, 6, 9)), (date(2025, 5, 25), date(2025, 6, 1)))
        self.assertEqual(latest_complete_period(date(2026, 1, 3)), (date(2025, 12, 27), date(2025, 12, 31)))
