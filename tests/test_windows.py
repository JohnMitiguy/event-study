from datetime import date

import numpy as np
import pandas as pd
import pytest

from event_study.errors import EventDataError
from event_study.windows import slice_windows

# 20 business days, positions 0..19:
#  0 Jan 02   5 Jan 09  10 Jan 16  15 Jan 23
#  1 Jan 03   6 Jan 10  11 Jan 17  16 Jan 24
#  2 Jan 04   7 Jan 11  12 Jan 18  17 Jan 25
#  3 Jan 05   8 Jan 12  13 Jan 19  18 Jan 26
#  4 Jan 08   9 Jan 15  14 Jan 22  19 Jan 29
DATES = pd.bdate_range("2024-01-02", periods=20)


@pytest.fixture
def returns():
    return pd.Series(np.arange(20) / 100, index=DATES, name="return")


def first_last(series):
    return series.index[0], series.index[-1]


def test_exact_window_dates(returns):
    # day 0 = Jan 16 (position 10). est_length=3, gap=3 -> positions 5..7.
    est, events = slice_windows(
        returns, "2024-01-16", est_length=3, gap=3, event_windows=((-1, 1), (-2, 3))
    )
    assert first_last(est) == (pd.Timestamp("2024-01-09"), pd.Timestamp("2024-01-11"))
    assert len(est) == 3
    assert first_last(events[(-1, 1)]) == (pd.Timestamp("2024-01-15"), pd.Timestamp("2024-01-17"))
    assert first_last(events[(-2, 3)]) == (pd.Timestamp("2024-01-12"), pd.Timestamp("2024-01-19"))


def test_default_positions():
    long = pd.Series(np.zeros(200), index=pd.bdate_range("2020-01-01", periods=200))
    p = 150
    est, events = slice_windows(long, long.index[p])
    assert len(est) == 120
    assert first_last(est) == (long.index[p - 129], long.index[p - 10])
    assert first_last(events[(-1, 1)]) == (long.index[p - 1], long.index[p + 1])
    assert first_last(events[(-5, 5)]) == (long.index[p - 5], long.index[p + 5])


def test_day0_as_date_object(returns):
    est, _ = slice_windows(returns, date(2024, 1, 16), est_length=3, gap=2, event_windows=((-1, 1),))
    assert est.index[-1] == pd.Timestamp("2024-01-12")


def test_boundary_est_ends_day_before_event_window_passes(returns):
    # gap=2 ends estimation on day -2; window (-1, 1) starts on day -1.
    est, events = slice_windows(returns, "2024-01-16", est_length=3, gap=2, event_windows=((-1, 1),))
    assert est.index[-1] == pd.Timestamp("2024-01-12")
    assert events[(-1, 1)].index[0] == pd.Timestamp("2024-01-15")


def test_day0_missing_raises(returns):
    # Saturday, between two rows: must not snap to a neighbour.
    with pytest.raises(ValueError, match="not in the returns index"):
        slice_windows(returns, "2024-01-13", est_length=3, gap=2, event_windows=((-1, 1),))


def test_estimation_before_first_row_raises(returns):
    # day 0 at position 2: estimation would start at 2 - 2 - 3 + 1 = -2.
    with pytest.raises(ValueError, match="estimation window needs 2 more row"):
        slice_windows(returns, "2024-01-04", est_length=3, gap=2, event_windows=((-1, 1),))


def test_event_window_past_last_row_raises(returns):
    # day 0 is the last row, so +1 runs past the end.
    with pytest.raises(ValueError, match="runs outside the series"):
        slice_windows(returns, "2024-01-29", est_length=3, gap=2, event_windows=((-1, 1),))


def test_estimation_overlapping_event_window_raises(returns):
    # gap=2 ends estimation on day -2, the same day (-2, 2) starts.
    with pytest.raises(ValueError, match="on or after the start"):
        slice_windows(returns, "2024-01-16", est_length=3, gap=2, event_windows=((-2, 2),))


def test_unsorted_index_raises(returns):
    with pytest.raises(ValueError, match="sorted"):
        slice_windows(returns.iloc[::-1], "2024-01-16", est_length=3, gap=2)


def test_duplicate_index_raises(returns):
    dup = pd.concat([returns.iloc[:5], returns.iloc[4:]])
    with pytest.raises(ValueError, match="duplicate"):
        slice_windows(dup, "2024-01-16", est_length=3, gap=2)


def test_tz_aware_index_raises(returns):
    aware = returns.tz_localize("America/New_York")
    with pytest.raises(ValueError, match="tz-naive"):
        slice_windows(aware, "2024-01-16", est_length=3, gap=2)


def test_tz_aware_day0_raises(returns):
    day0 = pd.Timestamp("2024-01-16", tz="America/New_York")
    with pytest.raises(ValueError, match="day0 .* must be tz-naive"):
        slice_windows(returns, day0, est_length=3, gap=2, event_windows=((-1, 1),))


def test_non_datetime_index_raises(returns):
    with pytest.raises(ValueError, match="DatetimeIndex"):
        slice_windows(returns.reset_index(drop=True), "2024-01-16")


def test_start_after_end_window_raises(returns):
    with pytest.raises(ValueError, match="start after end"):
        slice_windows(returns, "2024-01-16", est_length=3, gap=2, event_windows=((1, -1),))


# --- Look-ahead (item 2 of the review) -----------------------------------------


def test_gap_zero_with_post_event_window_raises(returns):
    # Without the gap rule, estimation would end on day 0 itself.
    with pytest.raises(ValueError, match="gap must be at least 1"):
        slice_windows(returns, "2024-01-16", est_length=3, gap=0, event_windows=((1, 5),))


def test_negative_gap_with_late_window_raises(returns):
    # Without the gap rule, estimation would run through day +3.
    with pytest.raises(ValueError, match="gap must be at least 1"):
        slice_windows(returns, "2024-01-16", est_length=3, gap=-3, event_windows=((5, 8),))


def test_look_ahead_is_a_parameter_error_even_without_enough_data(returns):
    # Jan 04 lacks history for the estimation window (an EventDataError), but
    # the look-ahead problem is found first and is a plain ValueError, so it
    # stops a run instead of failing one event.
    with pytest.raises(ValueError, match="increase gap") as info:
        slice_windows(returns, "2024-01-04", est_length=3, gap=2, event_windows=((-2, 2),))
    assert not isinstance(info.value, EventDataError)


# --- Error types (item 4) ------------------------------------------------------


@pytest.mark.parametrize(
    "day0, match",
    [
        ("2024-01-13", "not in the returns index"),  # Saturday
        ("2024-01-04", "estimation window needs"),
        ("2024-01-29", "runs outside the series"),
    ],
)
def test_event_data_problems_raise_event_data_error(returns, day0, match):
    with pytest.raises(EventDataError, match=match):
        slice_windows(returns, day0, est_length=3, gap=2, event_windows=((-1, 1),))


@pytest.mark.parametrize(
    "make_bad",
    [
        lambda r: r.iloc[::-1],  # unsorted
        lambda r: pd.concat([r, r.iloc[[3]]]).sort_index(),  # duplicate date
        lambda r: r.tz_localize("UTC"),  # tz-aware
    ],
    ids=["unsorted", "duplicate", "tz-aware"],
)
def test_index_problems_are_plain_value_errors(returns, make_bad):
    with pytest.raises(ValueError) as info:
        slice_windows(make_bad(returns), "2024-01-16", est_length=3, gap=2)
    assert not isinstance(info.value, EventDataError)
