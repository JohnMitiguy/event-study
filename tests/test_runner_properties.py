"""Property-based tests for run_events on random simulated inputs.

hypothesis draws random settings, a random stretch of real NYSE sessions
(the overlap diagnostics count sessions, so the dates must be real ones),
random market-model returns, random damage to those returns (NaN, inf, a
perfect-fit stretch, a benchmark cut short at one end), and 0-5 events whose day 0 is
anywhere in the data or just outside it. Then it checks the shape of the
results table, which must hold whatever happens to each event, that no ok
event's estimation window uses a day inside another event's widest window,
and that adding later events never changes an earlier event's row.

Not generated, because both stop the run with ValueError by design (tested
at the end): a repeated event window, and a benchmark that is flat for a
whole estimation window.
"""

import numpy as np
import pandas as pd
import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from test_runner import make_events

from event_study.errors import EventDataError
from event_study.event_days import nyse_calendar
from event_study.market_model import HARD_MIN_OBS, fit_market_model
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
        # A benchmark cut short at one end: still all NYSE sessions, so the
        # calendar check passes, but the two series no longer share dates.
        # (A day missing in the middle stops the run; tested in test_runner.py.)
        benchmark_returns = benchmark_returns.drop(dates[draw(st.sampled_from([0, n - 1]))])

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
    number_columns += ["alpha", "beta", "resid_std", "n", "est_start", "est_end", "est_masked_days"]
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
    assert ok[["est_start", "est_end", "est_masked_days"]].notna().all().all()


@given(run_inputs())
def test_abnormal_table_has_exactly_the_ok_events(inputs):
    results, abnormal = run_events(**inputs)
    ok_ids = results.loc[results["status"] == "ok", "event_id"].tolist()
    assert abnormal.index.tolist() == ok_ids
    start, end = widest_window(inputs["event_windows"])
    assert abnormal.columns.tolist() == list(range(start, end + 1))


# --- Skipping other events' days ----------------------------------------------


@st.composite
def close_event_inputs(draw) -> dict:
    """Clean returns on 200 sessions and 2-5 events within about six weeks
    of each other, at least 100 rows in, so most events run and their
    estimation windows often have days to skip. run_inputs alone gives few
    such events: its data is often short or damaged and its events spread out.
    """
    est_length = draw(st.integers(min_value=HARD_MIN_OBS, max_value=40))
    gap = draw(st.integers(min_value=1, max_value=8))
    windows = tuple(draw(st.lists(event_window(gap), min_size=1, max_size=3, unique=True)))

    n = 200
    first_row = draw(st.integers(min_value=MARGIN, max_value=len(SESSIONS) - n - MARGIN))
    dates = SESSIONS[first_row : first_row + n]
    rng = np.random.default_rng(draw(st.integers(min_value=0, max_value=2**32 - 1)))
    benchmark = rng.normal(0.0, 0.01, n)
    security = 0.0002 + 1.2 * benchmark + rng.normal(0.0, 0.01, n)

    anchor = first_row + draw(st.integers(min_value=100, max_value=n - 1))
    # Up to 5 rows past the last data row: still a session, thanks to MARGIN.
    rows = st.integers(min_value=anchor - 25, max_value=anchor + 5)
    day0s = [SESSIONS[r] for r in draw(st.lists(rows, min_size=2, max_size=5))]
    return {
        "events": make_events(day0s),
        "security_returns": pd.Series(security, index=dates),
        "benchmark_returns": pd.Series(benchmark, index=dates),
        "est_length": est_length,
        "gap": gap,
        "event_windows": windows,
    }


# Both kinds of input: the general one, and one built to make events skip days.
SKIP_INPUTS = st.one_of(run_inputs(), close_event_inputs())


def other_events_days(inputs: dict) -> list[list[pd.Timestamp]]:
    """For each event, the dates inside every other event's widest window.

    Worked out here from session positions, not taken from the runner.
    """
    sessions = nyse_calendar().sessions
    start, end = widest_window(inputs["event_windows"])
    positions = [sessions.get_loc(d) for d in inputs["events"]["day0"]]
    windows = [list(sessions[p + start : p + end + 1]) for p in positions]
    return [
        [d for j, days in enumerate(windows) if j != i for d in days] for i in range(len(windows))
    ]


@given(SKIP_INPUTS)
def test_no_estimation_day_inside_another_events_window(inputs):
    """For every ok event, the days fitted are exactly the data days from
    est_start to est_end outside every other event's widest window.

    The results give only est_start and est_end, not every day used. So this
    takes the allowed days between them, refits on those, and compares with
    the results. Had the runner used a skipped day, or left out an allowed
    one, the count or the fitted numbers would differ.
    """
    results, _ = run_events(**inputs)
    security, benchmark = inputs["security_returns"], inputs["benchmark_returns"]
    est_length, gap = inputs["est_length"], inputs["gap"]
    skip = other_events_days(inputs)
    for i, row in results[results["status"] == "ok"].iterrows():
        span = security.loc[row["est_start"] : row["est_end"]].index
        used = span[~span.isin(skip[i])]
        assert len(used) == est_length == row["n"]
        fit = fit_market_model(security.loc[used], benchmark.loc[used], min_obs=est_length)
        assert row["alpha"] == pytest.approx(fit.alpha)
        assert row["beta"] == pytest.approx(fit.beta)
        assert row["resid_std"] == pytest.approx(fit.resid_std)

        # The window ends as late as allowed: on day -gap, or every data day
        # after est_end up to day -gap is skipped.
        day_minus_gap = security.index[security.index.get_loc(row["day0"]) - gap]
        assert row["est_end"] <= day_minus_gap
        after_end = security.loc[row["est_end"] : day_minus_gap].index[1:]
        assert after_end.isin(skip[i]).all()
        span_to_gap = security.loc[row["est_start"] : day_minus_gap]
        assert row["est_masked_days"] == len(span_to_gap) - est_length


@given(SKIP_INPUTS, st.data())
def test_later_events_never_change_earlier_rows(inputs, data):
    """Adding events after every existing one leaves the existing rows unchanged.

    nearby_events is left out: it counts neighbours on both sides on purpose,
    so a later event close by changes it.
    """
    day0s = list(inputs["events"]["day0"])
    assume(day0s)
    sessions = nyse_calendar().sessions
    latest = sessions.get_loc(max(day0s))
    later_rows = st.integers(min_value=latest + 1, max_value=latest + 30)
    later = [sessions[r] for r in data.draw(st.lists(later_rows, min_size=1, max_size=3))]

    before, before_abnormal = run_events(**inputs)
    after, after_abnormal = run_events(**(inputs | {"events": make_events(day0s + later)}))

    earlier = after.iloc[: len(day0s)]
    keep = [c for c in before.columns if c not in ("nearby_events", "error")]
    pd.testing.assert_frame_equal(earlier[keep], before[keep], check_exact=True)
    # error is compared by value only: its column type depends on whether any
    # event in the run failed (None in an all-ok run, a string column once a
    # later event fails), but the messages must be the same.
    assert earlier["error"].fillna("").tolist() == before["error"].fillna("").tolist()
    # check_index_type=False: with no ok event the empty table's event_id
    # index has a different type, which says nothing about the numbers.
    pd.testing.assert_frame_equal(
        after_abnormal.loc[before_abnormal.index],
        before_abnormal,
        check_exact=True,
        check_index_type=False,
    )


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
