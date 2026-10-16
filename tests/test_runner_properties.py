"""Property-based tests for run_events on random simulated inputs.

hypothesis draws random settings, a random stretch of real NYSE sessions
(the overlap diagnostics count sessions, so the dates must be real ones),
random market-model returns, random damage to those returns (NaN, inf, a
perfect-fit stretch, a benchmark row missing), and 0-5 events whose day 0 is
anywhere in the data or just outside it. Then it checks the shape of the
results table, which must hold whatever happens to each event.

Not generated, because both stop the run with ValueError by design (tested
at the end): a repeated event window, and a benchmark that is flat for a
whole estimation window.
"""

import numpy as np
import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st
from test_runner import make_events

from event_study.errors import EventDataError
from event_study.event_days import nyse_calendar
from event_study.market_model import HARD_MIN_OBS
from event_study.runner import result_columns, run_events, widest_window

SESSIONS = nyse_calendar().sessions_in_range("2010-01-04", "2019-12-31")
# Rows of SESSIONS kept free before and after the data, so a day 0 just
# outside the data is still a real session.
MARGIN = 20
MAX_OFFSET = 8  # event windows start and end within +/- this many days


@st.composite
def event_window(draw, gap: int) -> tuple[int, int]:
    """A valid window: start <= end and it starts after day -gap."""
    start = draw(st.integers(min_value=-gap + 1, max_value=MAX_OFFSET))
    end = draw(st.integers(min_value=start, max_value=MAX_OFFSET))
    return start, end


def damage(draw, security: np.ndarray, benchmark: np.ndarray, est_length: int) -> None:
    """Change the returns in place in 0-3 random ways that make events fail."""
    n = len(security)
    position = st.integers(min_value=0, max_value=n - 1)
    for _ in range(draw(st.integers(min_value=0, max_value=3))):
        kind = draw(st.sampled_from(["nan", "inf", "perfect_fit"]))
        if kind == "nan":
            security[draw(position)] = np.nan
        elif kind == "inf":
            benchmark[draw(position)] = draw(st.sampled_from([np.inf, -np.inf]))
        else:
            # Security an exact linear function of the benchmark over a
            # stretch at least as long as the estimation window.
            first = draw(position)
            last = min(n, first + est_length + draw(st.integers(0, 10)))
            security[first:last] = 0.001 + 1.5 * benchmark[first:last]


@st.composite
def run_inputs(draw) -> dict:
    """Arguments for run_events: events, both return series and the settings."""
    est_length = draw(st.integers(min_value=HARD_MIN_OBS, max_value=40))
    gap = draw(st.integers(min_value=1, max_value=8))
    windows = tuple(draw(st.lists(event_window(gap), min_size=1, max_size=3, unique=True)))

    n = draw(st.integers(min_value=10, max_value=150))
    first_row = draw(st.integers(min_value=MARGIN, max_value=len(SESSIONS) - n - MARGIN))
    dates = SESSIONS[first_row : first_row + n]

    rng = np.random.default_rng(draw(st.integers(min_value=0, max_value=2**32 - 1)))
    benchmark = rng.normal(0.0, 0.01, n)
    security = 0.0002 + 1.2 * benchmark + rng.normal(0.0, 0.01, n)
    damage(draw, security, benchmark, est_length)
    security_returns = pd.Series(security, index=dates)
    benchmark_returns = pd.Series(benchmark, index=dates)
    if draw(st.integers(0, 4)) == 0:
        # A benchmark with one day missing: positions no longer line up.
        benchmark_returns = benchmark_returns.drop(dates[draw(st.integers(0, n - 1))])

    # Day 0 anywhere in the data, or up to MARGIN sessions before or after it.
    day0_rows = st.integers(min_value=first_row - MARGIN, max_value=first_row + n - 1 + MARGIN)
    day0s = [SESSIONS[row] for row in draw(st.lists(day0_rows, max_size=5))]
    return {
        "events": make_events(day0s),
        "security_returns": security_returns,
        "benchmark_returns": benchmark_returns,
        "est_length": est_length,
        "gap": gap,
        "event_windows": windows,
    }


@given(run_inputs())
def test_results_always_have_the_same_columns(inputs):
    results, _ = run_events(**inputs)
    assert list(results.columns) == result_columns(inputs["event_windows"])


@given(run_inputs())
def test_one_row_per_event_in_input_order(inputs):
    results, _ = run_events(**inputs)
    assert results["event_id"].tolist() == inputs["events"]["event_id"].tolist()


@given(run_inputs())
def test_status_is_ok_or_failed(inputs):
    results, _ = run_events(**inputs)
    assert set(results["status"]) <= {"ok", "failed"}


@given(run_inputs())
def test_failed_rows_have_a_message_and_no_numbers(inputs):
    results, _ = run_events(**inputs)
    failed = results[results["status"] == "failed"]
    for message in failed["error"]:
        assert isinstance(message, str)
        assert message.strip()
    number_columns = [c for c in results.columns if c.startswith(("car_", "t_"))]
    number_columns += ["alpha", "beta", "resid_std", "n"]
    assert failed[number_columns].isna().all().all()


@given(run_inputs())
def test_ok_rows_have_numbers_and_no_message(inputs):
    results, _ = run_events(**inputs)
    ok = results[results["status"] == "ok"]
    assert ok["error"].isna().all()
    assert (ok["n"] == inputs["est_length"]).all()
    number_columns = [c for c in ok.columns if c.startswith(("car_", "t_"))]
    number_columns += ["alpha", "beta", "resid_std"]
    assert np.isfinite(ok[number_columns].to_numpy(dtype=float)).all()


@given(run_inputs())
def test_abnormal_table_has_exactly_the_ok_events(inputs):
    results, abnormal = run_events(**inputs)
    ok_ids = results.loc[results["status"] == "ok", "event_id"].tolist()
    assert abnormal.index.tolist() == ok_ids
    start, end = widest_window(inputs["event_windows"])
    assert abnormal.columns.tolist() == list(range(start, end + 1))


# --- Settings and data that stop the run -------------------------------------


def clean_inputs(n: int = 300) -> tuple[pd.Series, pd.Series]:
    """Undamaged security and benchmark returns on real NYSE sessions."""
    dates = SESSIONS[MARGIN : MARGIN + n]
    rng = np.random.default_rng(7)
    benchmark = rng.normal(0.0, 0.01, n)
    security = 1.2 * benchmark + rng.normal(0.0, 0.01, n)
    return pd.Series(security, index=dates), pd.Series(benchmark, index=dates)


@pytest.mark.parametrize(
    "windows",
    [
        ((-1, 1), (-1, 1)),
        ((-1, 1), (-5, 5), (-1, 1)),
        ((-1, 1), [-1, 1]),  # a list and a tuple with the same days
    ],
)
@pytest.mark.parametrize("n_events", [0, 1])
def test_repeated_event_window_raises(windows, n_events):
    """It used to give each CAR and t column four times (23 columns, not 19)."""
    security, benchmark = clean_inputs()
    events = make_events([security.index[200]] * n_events)
    with pytest.raises(ValueError, match=r"same window more than once: \[-1,\+1\]") as info:
        run_events(events, security, benchmark, event_windows=windows)
    assert not isinstance(info.value, EventDataError)


@given(st.lists(event_window(10), min_size=1, max_size=3), st.data())
def test_any_repeated_window_raises(windows, data):
    repeated = data.draw(st.sampled_from(windows))
    position = data.draw(st.integers(min_value=0, max_value=len(windows)))
    windows = windows[:position] + [repeated] + windows[position:]
    security, benchmark = clean_inputs()
    with pytest.raises(ValueError, match="same window more than once"):
        run_events(make_events([]), security, benchmark, event_windows=tuple(windows))


def test_flat_benchmark_stops_the_run():
    """A benchmark with no variance is a broken series, not one failed event.

    The plain ValueError (not EventDataError) stops the whole run, even
    though the other event's estimation window is fine.
    """
    security, benchmark = clean_inputs()
    # Event A (row 200) estimates on rows 71-190, all flat; event B (row 290)
    # on rows 161-280, partly flat.
    benchmark.iloc[60:200] = 0.0
    events = make_events([security.index[200], security.index[290]], ids=["flat", "fine"])
    with pytest.raises(ValueError, match="same every day") as info:
        run_events(events, security, benchmark)
    assert not isinstance(info.value, EventDataError)
