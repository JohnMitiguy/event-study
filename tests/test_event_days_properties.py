"""Property-based tests for event_day_zero.

Instead of hand-picked dates (tests/test_event_days.py has those), hypothesis
generates random US Eastern announcement times and checks rules that must
hold for every one of them.

The main check compares against an independent definition of day 0: the
first NYSE session whose close is strictly after the announcement. That one
sentence covers pre-market, during hours, after the close, weekends,
holidays and early-close days, so it is a good cross-check on the
step-by-step logic in event_days.py.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from event_study.event_days import EASTERN_TZ_NAME, event_day_zero, nyse_calendar

ET = ZoneInfo(EASTERN_TZ_NAME)
CAL = nyse_calendar()
SESSIONS = CAL.sessions
# One close per session, as UTC instants, in session order.
CLOSES = pd.DatetimeIndex(CAL.closes)

# Generated times run from the first session through the end of the
# second-to-last session, so "the next session" always exists.
FIRST_TIME = datetime.combine(SESSIONS[0].date(), time(0, 0))
LAST_TIME = datetime.combine(SESSIONS[-2].date(), time(23, 59, 59))

# Sessions with a normal close and with an early close, leaving out the
# calendar's last session (after its close there is no next session).
# Plain lists, because hypothesis's sampled_from needs an ordered list.
EARLY_CLOSE_DAYS = list(CAL.early_closes.intersection(SESSIONS[:-1]))
REGULAR_DAYS = list(SESSIONS[:-1].difference(EARLY_CLOSE_DAYS))
ALL_BUT_LAST_SESSION = list(SESSIONS[:-1])

ONE_MICROSECOND = timedelta(microseconds=1)

# Random tz-aware Eastern datetimes. allow_imaginary=False skips wall-clock
# times that never happened (the 2:00-2:59 gap when daylight saving starts).
eastern_times = st.datetimes(
    min_value=FIRST_TIME,
    max_value=LAST_TIME,
    timezones=st.just(ET),
    allow_imaginary=False,
)


def expected_day_zero(announced_at: datetime) -> pd.Timestamp:
    """The first session whose close is strictly after announced_at.

    searchsorted(side="right") gives the position of the first close that is
    later than the given instant (a close equal to it does not count, so an
    announcement exactly at the close rolls forward).
    """
    instant = pd.Timestamp(announced_at).tz_convert("UTC")
    return SESSIONS[CLOSES.searchsorted(instant, side="right")]


def close_et(session: pd.Timestamp) -> pd.Timestamp:
    """That session's close as a US Eastern Timestamp."""
    return CAL.session_close(session).tz_convert(EASTERN_TZ_NAME)


@given(eastern_times)
def test_day_zero_is_a_session_date(announced_at):
    day0 = event_day_zero(announced_at)
    assert day0 in SESSIONS
    # Same form as the returns index: tz-naive, midnight.
    assert day0.tz is None
    assert day0 == day0.normalize()


@given(eastern_times)
def test_day_zero_never_before_announcement_date(announced_at):
    assert event_day_zero(announced_at).date() >= announced_at.date()


@given(eastern_times)
def test_day_zero_is_first_session_closing_after_announcement(announced_at):
    assert event_day_zero(announced_at) == expected_day_zero(announced_at)


@given(eastern_times, eastern_times)
def test_later_announcement_never_gives_earlier_day_zero(a, b):
    earlier, later = sorted([a, b])
    assert event_day_zero(earlier) <= event_day_zero(later)


@given(eastern_times)
def test_datetime_and_pandas_timestamp_agree(announced_at):
    # load_events passes pandas Timestamps; tests mostly pass datetimes.
    as_timestamp = pd.Timestamp(announced_at).tz_convert(EASTERN_TZ_NAME)
    assert event_day_zero(as_timestamp) == event_day_zero(announced_at)


# --- The close boundary -----------------------------------------------------


@given(st.sampled_from(REGULAR_DAYS))
def test_regular_close_is_four_pm(session):
    assert close_et(session).time() == time(16, 0)


@given(st.sampled_from(REGULAR_DAYS))
def test_regular_close_boundary(session):
    close = close_et(session)
    assert event_day_zero(close - ONE_MICROSECOND) == session
    assert event_day_zero(close) == CAL.next_session(session)


@given(st.sampled_from(EARLY_CLOSE_DAYS))
def test_early_close_boundary(session):
    close = close_et(session)
    assert event_day_zero(close - ONE_MICROSECOND) == session
    assert event_day_zero(close) == CAL.next_session(session)


@given(
    st.sampled_from(ALL_BUT_LAST_SESSION),
    # Seconds into the day, 00:00:00 through 23:59:59.
    st.integers(min_value=0, max_value=24 * 3600 - 1),
)
def test_same_day_before_close_next_session_from_close(session, seconds):
    """Covers regular and early-close days alike, at any time of day."""
    midnight = pd.Timestamp(session).tz_localize(EASTERN_TZ_NAME)
    # Adding a Timedelta to a tz-aware Timestamp adds real elapsed time, so on
    # a daylight-saving day the wall clock can be an hour off. The NYSE never
    # trades on those Sundays, so every session date here is safe.
    announced_at = midnight + pd.Timedelta(seconds=seconds)
    assert announced_at.date() == session.date()
    if announced_at < close_et(session):
        assert event_day_zero(announced_at) == session
    else:
        assert event_day_zero(announced_at) == CAL.next_session(session)


def test_early_close_days_exist_in_calendar():
    # Guards the early-close tests above against silently sampling nothing.
    assert len(EARLY_CLOSE_DAYS) > 20


# --- Rejected inputs ----------------------------------------------------------


@given(st.datetimes(min_value=FIRST_TIME, max_value=LAST_TIME))
def test_naive_datetime_raises(announced_at):
    with pytest.raises(ValueError, match="no time zone"):
        event_day_zero(announced_at)


@given(
    st.datetimes(min_value=FIRST_TIME, max_value=LAST_TIME),
    # Any IANA zone except the one accepted. Aliases of it such as
    # "US/Eastern" are rejected too, by design (only the exact name passes).
    st.timezones().filter(lambda tz: str(tz) != EASTERN_TZ_NAME),
)
def test_other_time_zones_raise(naive, tz):
    with pytest.raises(ValueError, match="must be"):
        event_day_zero(naive.replace(tzinfo=tz))
