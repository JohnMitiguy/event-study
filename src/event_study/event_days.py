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


def next_session(day: pd.Timestamp) -> pd.Timestamp:
    """The NYSE session after `day`, which must itself be a session.

    Used to move day 0 one trading day later. Raises ValueError if `day` is
    not a session or is the last one in the calendar.
    """
    ts = pd.Timestamp(day)
    cal = nyse_calendar()
    if ts not in cal.sessions or ts == cal.last_session:
        raise ValueError(f"{ts.date()} has no next NYSE session in the calendar")
    return cal.next_session(ts)


def session_position(day: pd.Timestamp) -> int:
    """Row number of `day` in the NYSE session list (CALENDAR_START onward).

    Differences between positions count trading days, with no price data
    needed, so an event can be placed even when its dates are outside the
    downloaded data. `day` must be a tz-naive session date; a weekend,
    holiday, or date outside the calendar raises ValueError.
    """
    ts = pd.Timestamp(day)
    sessions = nyse_calendar().sessions
    if ts not in sessions:
        raise ValueError(
            f"{ts.date()} is not an NYSE session between "
            f"{sessions[0].date()} and {sessions[-1].date()}"
        )
    return sessions.get_loc(ts)


def check_trading_days(returns: pd.Series) -> None:
    """Raise ValueError unless the index has exactly the NYSE sessions
    between its own first and last dates.

    Lists sessions missing from the series and index dates that are not
    sessions (weekends, holidays, or timestamps that are not midnight).

    Limits: it cannot detect a series cut short at either end, since it only
    checks between the series' own first and last dates. Duplicate dates are
    not reported (windows.slice_windows catches those).
    """
    index = returns.index
    if not isinstance(index, pd.DatetimeIndex):
        raise ValueError(f"returns must have a DatetimeIndex, got {type(index).__name__}")
    if index.tz is not None:
        raise ValueError(f"returns index must be tz-naive, got time zone {index.tz}")

    cal = nyse_calendar()
    sessions = cal.sessions_in_range(index.min().normalize(), index.max().normalize())
    # .difference gives the dates in the first index but not the second.
    missing = sessions.difference(index)
    extra = index.difference(sessions)
    if len(missing) == 0 and len(extra) == 0:
        return

    def fmt(dates: pd.DatetimeIndex) -> str:
        return ", ".join(str(d.date()) if d == d.normalize() else str(d) for d in dates) or "none"

    raise ValueError(
        f"returns index does not match NYSE sessions "
        f"({index.min().date()} to {index.max().date()}).\n"
        f"  Missing sessions ({len(missing)}): {fmt(missing)}\n"
        f"  Non-session dates ({len(extra)}): {fmt(extra)}"
    )
