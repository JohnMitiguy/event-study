from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from event_study.event_days import event_day_zero

ET = ZoneInfo("America/New_York")


def et(y, mo, d, h, mi=0):
    """A datetime in US Eastern."""
    return datetime(y, mo, d, h, mi, tzinfo=ET)


@pytest.mark.parametrize(
    "announced_at, expected",
    [
        # Saturday -> Monday
        (et(2024, 6, 1, 10), "2024-06-03"),
        # Friday after the close -> Monday
        (et(2024, 5, 31, 16, 30), "2024-06-03"),
        # Market holiday (July 4) -> next day
        (et(2024, 7, 4, 10), "2024-07-05"),
        # Pre-market -> same day
        (et(2024, 6, 4, 8), "2024-06-04"),
        # Regular close boundaries
        (et(2024, 6, 4, 15, 59), "2024-06-04"),
        (et(2024, 6, 4, 16, 0), "2024-06-05"),
        # Day after Thanksgiving 2024 closes at 1pm
        (et(2024, 11, 29, 12, 59), "2024-11-29"),
        (et(2024, 11, 29, 13, 0), "2024-12-02"),
        (et(2024, 11, 29, 14, 0), "2024-12-02"),
        # Unscheduled closures: Hurricane Sandy (Oct 29-30, 2012)
        (et(2012, 10, 29, 10), "2012-10-31"),
        # George H.W. Bush funeral (Dec 5, 2018)
        (et(2018, 12, 5, 10), "2018-12-06"),
    ],
)
def test_event_day_zero(announced_at, expected):
    assert event_day_zero(announced_at) == pd.Timestamp(expected)


def test_returns_tz_naive_date():
    day0 = event_day_zero(et(2024, 6, 4, 8))
    assert day0.tz is None
    assert day0 == day0.normalize()


def test_pandas_timestamp_in_eastern_accepted():
    stamp = pd.Timestamp("2024-06-04 08:00", tz="America/New_York")
    assert event_day_zero(stamp) == pd.Timestamp("2024-06-04")


def test_naive_datetime_rejected():
    with pytest.raises(ValueError, match="no time zone"):
        event_day_zero(datetime(2024, 6, 4, 8))


@pytest.mark.parametrize(
    "tz",
    [timezone.utc, timezone(timedelta(hours=-5))],
    ids=["utc", "fixed_minus_5"],
)
def test_non_eastern_timezone_rejected(tz):
    with pytest.raises(ValueError, match="America/New_York"):
        event_day_zero(datetime(2024, 6, 4, 8, tzinfo=tz))
