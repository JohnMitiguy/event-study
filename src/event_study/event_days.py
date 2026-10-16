"""Find event day 0: the first NYSE trading day the market could react.

Rules:
- Announced on a trading day before that day's close (pre-market or during
  hours): day 0 is that same day.
- Announced at or after the close, or on a weekend or holiday: day 0 is the
  next trading day.
- "The close" is that day's actual close from the exchange calendar, so on
  early-close days (usually 1pm ET) 1:00pm or later rolls forward.

Known limitation: an announcement during market hours makes day 0 include
trading from before the news, which dilutes the day-0 reaction. This is the
standard convention.

The calendar is exchange_calendars' XNYS, which includes scheduled holidays,
early closes, and unscheduled closures (e.g. Hurricane Sandy, state funerals).
"""

from datetime import datetime
from functools import cache

import exchange_calendars as xcals
import pandas as pd

# The only time zone accepted for announcement times. UTC or fixed offsets
# like -05:00 are rejected: a fixed offset is wrong for half the year (daylight
# saving), so it is a likely data-entry mistake.
EASTERN_TZ_NAME = "America/New_York"

# First date the trading calendar covers. Announcements before this raise.
CALENDAR_START = "2000-01-01"


@cache
def nyse_calendar() -> xcals.ExchangeCalendar:
    """The NYSE (XNYS) trading calendar, built once and reused.

    It covers CALENDAR_START through roughly one year after today
    (the library's default end).
    """
    return xcals.get_calendar("XNYS", start=CALENDAR_START)


def _check_eastern(announced_at: datetime) -> None:
    """Raise ValueError unless announced_at is tz-aware in America/New_York.

    str(tzinfo) gives the zone name for both zoneinfo.ZoneInfo and pandas
    Timestamps ("America/New_York"); UTC gives "UTC" and a fixed offset gives
    something like "UTC-05:00", so both are rejected.
    """
    if announced_at.tzinfo is None:
        raise ValueError(
            f"announced_at {announced_at} has no time zone. Attach US Eastern, e.g. "
            f'datetime(..., tzinfo=ZoneInfo("{EASTERN_TZ_NAME}")).'
        )
    tz_name = str(announced_at.tzinfo)
    if tz_name != EASTERN_TZ_NAME:
        raise ValueError(
            f"announced_at {announced_at} is in time zone {tz_name!r}; "
            f"it must be {EASTERN_TZ_NAME!r}."
        )


def event_day_zero(announced_at: datetime) -> pd.Timestamp:
    """Event day 0 for an announcement time in US Eastern.

    `announced_at` must be a tz-aware datetime or pandas Timestamp in
    America/New_York; anything else raises ValueError.

    Returns the trading date as a tz-naive midnight Timestamp, matching the
    index of the price series from prices.load_prices.
    """
    _check_eastern(announced_at)
    cal = nyse_calendar()
    stamp = pd.Timestamp(announced_at)
    day = pd.Timestamp(stamp.date())

    if day < cal.first_session or day > cal.last_session:
        raise ValueError(
            f"announced_at {announced_at} is outside the trading calendar "
            f"({cal.first_session.date()} to {cal.last_session.date()})."
        )

    # session_close is in UTC; comparing two tz-aware Timestamps is safe
    # because pandas compares the underlying instants.
    if cal.is_session(day) and stamp < cal.session_close(day):
        return day
    # Weekend/holiday: the next session after the date. After the close on a
    # trading day: the session after that one.
    if cal.is_session(day):
        return cal.next_session(day)
    return cal.date_to_session(day, direction="next")
