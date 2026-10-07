"""8-day compositing periods, aligned the same way as OB.DAAC's L3 8-day products.

Periods start on day-of-year 1, 9, 17, ..., 361 of each year. The last period of
a year is cut short at Dec 31 (5 days, or 6 in a leap year) rather than spilling
into the next year.
"""
from datetime import date, timedelta

PERIOD_DAYS = 8


def period_containing(day: date) -> tuple[date, date]:
    """Return the (first, last) day, inclusive, of the 8-day period containing `day`."""
    doy = day.timetuple().tm_yday
    start = date(day.year, 1, 1) + timedelta(days=(doy - 1) // PERIOD_DAYS * PERIOD_DAYS)
    end = min(start + timedelta(days=PERIOD_DAYS - 1), date(day.year, 12, 31))
    return start, end


def latest_complete_period(today: date) -> tuple[date, date]:
    """Return the most recent period that ended before `today`."""
    start, _ = period_containing(today)
    return period_containing(start - timedelta(days=1))
