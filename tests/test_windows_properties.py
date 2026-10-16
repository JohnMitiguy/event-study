"""Property-based tests for slice_windows.

hypothesis draws random valid settings (est_length, gap, event windows), a
random series just long enough for them (plus a few spare rows), and checks
that the windows land in the right rows. Then it breaks the settings or the
data in random ways and checks that slice_windows always raises.

The series dates are Monday-Friday business days (pd.bdate_range).
slice_windows counts rows, not calendar sessions, so holidays don't matter
here.
"""

import numpy as np
import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from event_study.errors import EventDataError
from event_study.windows import slice_windows

MAX_EST_LENGTH = 60
MAX_GAP = 15
MAX_OFFSET = 15  # event windows start and end within +/- this many days


@st.composite
def event_window(draw, gap: int) -> tuple[int, int]:
    """A window (start, end) with start <= end that starts after day -gap."""
    start = draw(st.integers(min_value=-gap + 1, max_value=MAX_OFFSET))
    end = draw(st.integers(min_value=start, max_value=MAX_OFFSET))
    return start, end


@st.composite
def valid_setup(draw) -> dict:
    """Valid settings and a series that fits them.

    Returns a dict of slice_windows' arguments plus "p", the row number of
    day 0. The series has exactly the rows the windows need, plus 0-5 spare
    rows at each end.
    """
    est_length = draw(st.integers(min_value=1, max_value=MAX_EST_LENGTH))
    gap = draw(st.integers(min_value=1, max_value=MAX_GAP))
    windows = tuple(draw(st.lists(event_window(gap), min_size=1, max_size=3)))

    # Rows needed before day 0: the estimation window reaches back to
    # day -(gap + est_length - 1); an event window can't start earlier
    # than that, but take the max anyway.
    rows_before = max(gap + est_length - 1, -min(start for start, _ in windows))
    rows_after = max(0, max(end for _, end in windows))
    p = rows_before + draw(st.integers(min_value=0, max_value=5))
    n = p + rows_after + 1 + draw(st.integers(min_value=0, max_value=5))

    seed = draw(st.integers(min_value=0, max_value=2**32 - 1))
    values = np.random.default_rng(seed).normal(0.0, 0.01, n)
    returns = pd.Series(values, index=pd.bdate_range("2020-01-01", periods=n))
    return {
        "returns": returns,
        "day0": returns.index[p],
        "est_length": est_length,
        "gap": gap,
        "event_windows": windows,
        "p": p,
    }


def call(setup: dict):
    """slice_windows with the arguments in setup (ignoring "p")."""
    args = {k: v for k, v in setup.items() if k != "p"}
    return slice_windows(**args)


@given(valid_setup())
def test_estimation_window_has_est_length_rows(setup):
    estimation, _ = call(setup)
    assert len(estimation) == setup["est_length"]


@given(valid_setup())
def test_estimation_window_ends_gap_rows_before_day_zero(setup):
    estimation, _ = call(setup)
    returns, p, gap = setup["returns"], setup["p"], setup["gap"]
    first = p - gap - setup["est_length"] + 1
    # Same dates and values as rows first .. p - gap of the input.
    pd.testing.assert_series_equal(estimation, returns.iloc[first : p - gap + 1])
    assert estimation.index[-1] == returns.index[p - gap]


@given(valid_setup())
def test_event_windows_are_in_the_right_rows(setup):
    _, event_slices = call(setup)
    returns, p = setup["returns"], setup["p"]
    assert set(event_slices) == set(setup["event_windows"])
    for (start, end), window in event_slices.items():
        assert len(window) == end - start + 1
        pd.testing.assert_series_equal(window, returns.iloc[p + start : p + end + 1])
        if start <= 0 <= end:
            assert setup["day0"] in window.index


@given(valid_setup())
def test_estimation_window_never_overlaps_day_zero_or_event_windows(setup):
    estimation, event_slices = call(setup)
    est_dates = set(estimation.index)
    assert setup["day0"] not in est_dates
    for window in event_slices.values():
        assert est_dates.isdisjoint(window.index)
        # Stronger: the estimation window ends before each window starts.
        assert estimation.index[-1] < window.index[0]


@given(valid_setup())
def test_input_is_not_changed(setup):
    before = setup["returns"].copy()
    call(setup)
    pd.testing.assert_series_equal(setup["returns"], before)


# --- Too little data ----------------------------------------------------------


@given(valid_setup())
def test_one_row_short_at_the_start_raises(setup):
    """Drop rows from the start until the estimation window is one row short."""
    returns, p = setup["returns"], setup["p"]
    est_first = p - setup["gap"] - setup["est_length"] + 1
    earliest_start = min(start for start, _ in setup["event_windows"])
    first_needed = min(est_first, p + earliest_start)
    setup["returns"] = returns.iloc[first_needed + 1 :]
    with pytest.raises(EventDataError):
        call(setup)


@given(valid_setup())
def test_one_row_short_at_the_end_raises(setup):
    returns, p = setup["returns"], setup["p"]
    latest_end = max(end for _, end in setup["event_windows"])
    last_needed = max(p, p + latest_end)
    setup["returns"] = returns.iloc[:last_needed]  # drops row last_needed
    with pytest.raises(EventDataError):
        call(setup)


# --- Bad settings -------------------------------------------------------------


@st.composite
def bad_setup(draw) -> dict:
    """A valid setup with exactly one setting made invalid."""
    setup = draw(valid_setup())
    gap = setup["gap"]
    kind = draw(st.sampled_from(["est_length", "gap", "start_after_end", "lookahead"]))
    if kind == "est_length":
        setup["est_length"] = draw(st.integers(max_value=0))
    elif kind == "gap":
        setup["gap"] = draw(st.integers(max_value=0))
    elif kind == "start_after_end":
        start = draw(st.integers(min_value=-gap + 2, max_value=MAX_OFFSET))
        end = draw(st.integers(min_value=-gap + 1, max_value=start - 1))
        setup["event_windows"] = (*setup["event_windows"], (start, end))
    else:
        # A window starting on or before day -gap, where the estimation
        # window ends: estimation would overlap or touch the event window.
        start = draw(st.integers(min_value=-gap - 20, max_value=-gap))
        end = draw(st.integers(min_value=start, max_value=MAX_OFFSET))
        setup["event_windows"] = (*setup["event_windows"], (start, end))
    return setup


@given(bad_setup())
def test_bad_settings_always_raise_value_error(setup):
    with pytest.raises(ValueError) as info:
        call(setup)
    # A bad setting is a whole-run problem, so it must not be the per-event
    # EventDataError that the runner would record and skip past.
    assert not isinstance(info.value, EventDataError)


@given(bad_setup())
def test_bad_settings_raise_even_when_day_zero_is_missing(setup):
    """Settings are checked before the data, so they fail the same way for every event."""
    setup["day0"] = pd.Timestamp("1990-01-01")
    with pytest.raises(ValueError) as info:
        call(setup)
    assert not isinstance(info.value, EventDataError)


@given(
    valid_setup(),
    st.sampled_from(["est_length", "gap", "event_windows"]),
    # Whole-number floats like 120.0, and non-whole ones like 2.5.
    st.floats(min_value=1, max_value=30, allow_nan=False),
)
def test_non_integer_settings_raise(setup, name, value):
    """A float setting must raise, never quietly return windows.

    It currently raises TypeError from pandas' iloc ("cannot do positional
    indexing ... of type float"), not ValueError; either counts here.
    """
    if name == "event_windows":
        setup["event_windows"] = ((value, value + 1),)
    else:
        setup[name] = value
    with pytest.raises((TypeError, ValueError)):
        call(setup)
