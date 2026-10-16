"""Tests for the runner, on simulated returns (event_study.simulate).

Event rows are fake. Dates are rows of the simulated index, so day 0 is
always a date the data has unless a test says otherwise.
"""

import numpy as np
import pandas as pd
import pytest

# pytest puts the tests/ folder on the import path, so the fake-CSV helpers
# from test_events.py can be imported by module name.
from test_events import valid_row, write_events

from event_study.errors import EventDataError
from event_study.event_days import nyse_calendar
from event_study.events import load_events
from event_study.market_model import abnormal_returns, car_test, fit_market_model
from event_study.runner import (
    CARRIED_COLUMNS,
    events_needing_later_data,
    overlap_diagnostics,
    result_columns,
    run_events,
)
from event_study.simulate import DAY0_POSITION, planted_event
from event_study.windows import (
    DEFAULT_EST_LENGTH,
    DEFAULT_EVENT_WINDOWS,
    DEFAULT_GAP,
    slice_windows,
)


@pytest.fixture(scope="module")
def sim():
    """Simulated (security, benchmark, day0) with +4% planted on day 0."""
    return planted_event()


def make_events(day0s, ids=None) -> pd.DataFrame:
    """A minimal events table with the columns run_events needs."""
    ids = ids or [f"test_event_{i}" for i in range(len(day0s))]
    return pd.DataFrame(
        {
            "event_id": ids,
            "decision_group": "ministerial",
            "direction": "cut",
            "surprise_flag": pd.array([pd.NA] * len(ids), dtype="Int64"),
            "event_time": pd.NaT,
            "used_leak": False,
            "day0": pd.to_datetime(list(day0s)),
        }
    )


def test_matches_direct_pipeline(sim):
    security, benchmark, day0 = sim
    results, abnormal = run_events(make_events([day0]), security, benchmark)
    row = results.iloc[0]

    sec_est, sec_events = slice_windows(security, day0)
    bench_est, bench_events = slice_windows(benchmark, day0)
    fit = fit_market_model(sec_est, bench_est, min_obs=DEFAULT_EST_LENGTH)
    assert row["alpha"] == pytest.approx(fit.alpha)
    assert row["beta"] == pytest.approx(fit.beta)
    assert row["resid_std"] == pytest.approx(fit.resid_std)
    assert row["n"] == DEFAULT_EST_LENGTH
    for window, label in (((-1, 1), "[-1,+1]"), ((-5, 5), "[-5,+5]")):
        direct = car_test(fit, sec_events[window], bench_events[window])
        assert row[f"car_{label}"] == pytest.approx(direct.car)
        assert row[f"t_{label}"] == pytest.approx(direct.test_stat)

    direct_abnormal = abnormal_returns(fit, sec_events[(-5, 5)], bench_events[(-5, 5)])
    assert list(abnormal.columns) == list(range(-5, 6))
    assert abnormal.loc["test_event_0"].tolist() == pytest.approx(direct_abnormal.tolist())
    assert pd.isna(row["error"])
    assert row["status"] == "ok"


def test_planted_jump_is_detected(sim):
    security, benchmark, day0 = sim
    results, _ = run_events(make_events([day0]), security, benchmark)
    assert results.loc[0, "t_[-1,+1]"] > 1.96


def test_failures_are_recorded_and_others_still_run(sim):
    security, benchmark, day0 = sim
    events = make_events(
        [
            day0,
            # Not in the data. It must be an NYSE session inside the calendar
            # (which ends about a year after today) for the overlap counts.
            pd.Timestamp("2025-01-02"),
            security.index[50],  # needs 129 rows of history, has 50
        ],
        ids=["good", "missing_day0", "too_early"],
    )
    results, abnormal = run_events(events, security, benchmark)

    assert results["error"].notna().sum() == 2
    assert results["status"].tolist() == ["ok", "failed", "failed"]
    by_id = results.set_index("event_id")
    assert pd.isna(by_id.loc["good", "error"])
    assert "not in the returns index" in by_id.loc["missing_day0", "error"]
    assert "estimation window needs" in by_id.loc["too_early", "error"]
    assert pd.isna(by_id.loc["too_early", "beta"])
    assert pd.isna(by_id.loc["too_early", "n"])
    # Day 0 is kept for failed events.
    assert by_id.loc["missing_day0", "day0"] == pd.Timestamp("2025-01-02")
    assert list(abnormal.index) == ["good"]


def test_nan_in_one_event_is_recorded_as_failed(sim):
    security, benchmark, day0 = sim
    security = security.copy()
    security.loc[day0] = np.nan
    # Row 140: estimation 11..130 and widest window 135..145 miss row 150.
    other = security.index[DAY0_POSITION - 10]
    results, _ = run_events(make_events([day0, other], ids=["nan", "fine"]), security, benchmark)
    by_id = results.set_index("event_id")
    assert by_id.loc["nan", "status"] == "failed"
    assert "NaN or infinite" in by_id.loc["nan", "error"]
    assert by_id.loc["fine", "status"] == "ok"


def test_plain_value_error_stops_the_run(sim):
    # A bad parameter is a problem with the whole run, not one event.
    security, benchmark, day0 = sim
    with pytest.raises(ValueError, match="gap must be at least 1") as info:
        run_events(make_events([day0]), security, benchmark, gap=0)
    assert not isinstance(info.value, EventDataError)


def test_broken_index_stops_the_run(sim):
    security, benchmark, day0 = sim
    duplicated = pd.concat([security, security.iloc[[10]]]).sort_index()
    with pytest.raises(ValueError, match="duplicate dates") as info:
        run_events(make_events([day0]), duplicated, benchmark)
    assert not isinstance(info.value, EventDataError)


def test_carried_columns_keep_values_and_types(sim):
    security, benchmark, day0 = sim
    events = make_events([day0])
    events["surprise_flag"] = pd.array([1], dtype="Int64")
    events["used_leak"] = True
    events["direction"] = "hold"
    results, _ = run_events(events, security, benchmark)
    assert list(results.columns) == result_columns(DEFAULT_EVENT_WINDOWS)
    assert results.loc[0, "surprise_flag"] == 1
    assert results["surprise_flag"].dtype == "Int64"
    assert bool(results.loc[0, "used_leak"])
    assert results.loc[0, "direction"] == "hold"


def test_empty_events(sim):
    security, benchmark, _ = sim
    results, abnormal = run_events(make_events([]), security, benchmark)
    assert len(results) == 0
    assert list(results.columns) == result_columns(DEFAULT_EVENT_WINDOWS)
    assert abnormal.shape == (0, 11)


def test_parameters_pass_through(sim):
    security, benchmark, day0 = sim
    # (0, 3) is the latest end and (-1, 1) the earliest start, so the widest
    # window (-1, 3) is not one of the configured windows.
    windows = ((-1, 1), (0, 3))
    results, abnormal = run_events(
        make_events([day0]), security, benchmark, est_length=60, gap=5, event_windows=windows
    )
    assert results.loc[0, "n"] == 60
    assert "car_[+0,+3]" in results.columns
    assert list(abnormal.columns) == [-1, 0, 1, 2, 3]


def test_missing_column_raises(sim):
    security, benchmark, day0 = sim
    events = make_events([day0]).drop(columns="direction")
    with pytest.raises(ValueError, match="missing column.*direction"):
        run_events(events, security, benchmark)


def test_duplicate_event_id_raises(sim):
    security, benchmark, day0 = sim
    events = make_events([day0, day0], ids=["same", "same"])
    with pytest.raises(ValueError, match="duplicate event_id"):
        run_events(events, security, benchmark)


# --- Overlap diagnostics ------------------------------------------------------

# Real NYSE sessions, since the diagnostics count session positions.
# SESSIONS[k] is k sessions after 2023-01-03.
SESSIONS = nyse_calendar().sessions_in_range("2023-01-03", "2025-12-31")


def diagnostics(day0s):
    """Diagnostics with the default estimation length, gap and windows."""
    return overlap_diagnostics(
        pd.Series(day0s), DEFAULT_EST_LENGTH, DEFAULT_GAP, DEFAULT_EVENT_WINDOWS
    )


def diagnostics_for(positions):
    """Diagnostics for events at these positions in SESSIONS."""
    return diagnostics([SESSIONS[p] for p in positions])


def test_overlap_counts():
    # Widest window is days -5..+5; estimation window is days -129..-10.
    # A at 150: widest 145..155, estimation 21..140.
    # B at 130: widest 125..135, estimation 1..120.
    # C at 158: widest 153..163, estimation 29..148.
    diag = diagnostics_for([150, 130, 158])
    # A's estimation window holds all 11 of B's days; A and C share 153..155.
    assert diag.loc[0].tolist() == [11, 1]
    # B's estimation window ends at 120, before A and C begin.
    assert diag.loc[1].tolist() == [0, 0]
    # C's estimation window holds B's 11 days plus A's 145..148.
    assert diag.loc[2].tolist() == [15, 1]


def test_same_day_events_are_nearby():
    diag = diagnostics_for([150, 150])
    assert diag["nearby_events"].tolist() == [1, 1]
    assert diag["est_overlap_days"].tolist() == [0, 0]


def test_event_after_the_data_end_still_counts():
    # Data is SESSIONS[0..199]. A's day 0 is row 197, so its widest window is
    # 192..202 and runs past the data. B's day 0 is two sessions after the
    # last row (position 201): widest window 196..206. They share 196..202.
    data = SESSIONS[:200]
    a, b = data[197], SESSIONS[201]
    assert b not in data
    diag = diagnostics([a, b])
    assert diag["nearby_events"].tolist() == [1, 1]
    # A's estimation window ends at 187, B's at 191: neither reaches 192.
    assert diag["est_overlap_days"].tolist() == [0, 0]


def test_event_before_the_data_start_still_counts():
    # Data starts at SESSIONS[10]. B's day 0 is SESSIONS[9], one session
    # before the first row: widest window 4..14. A is data row 129
    # (SESSIONS[139]): estimation window 10..129, which holds B's 10..14.
    data = SESSIONS[10:310]
    a, b = data[129], SESSIONS[9]
    assert b not in data
    diag = diagnostics([a, b])
    assert diag.loc[0].tolist() == [5, 0]
    assert diag.loc[1].tolist() == [0, 0]


def test_non_session_day0_raises():
    with pytest.raises(ValueError, match="not an NYSE session"):
        diagnostics([pd.Timestamp("2024-07-04")])  # Independence Day


def test_overlap_columns_in_results(sim):
    security, benchmark, day0 = sim
    events = make_events([day0, security.index[DAY0_POSITION + 3]])
    results, _ = run_events(events, security, benchmark)
    assert results["nearby_events"].tolist() == [1, 1]
    assert results["est_overlap_days"].dtype == "Int64"


# --- Data coverage ------------------------------------------------------------


def test_events_needing_later_data_uses_widest_end():
    last = SESSIONS[200]
    events = make_events([SESSIONS[195], SESSIONS[196]], ids=["fits", "too_late"])
    # Widest end +5: 195 + 5 = 200 is the last data day; 196 + 5 is not.
    assert events_needing_later_data(events, last, DEFAULT_EVENT_WINDOWS) == ["too_late"]
    # Widest end +3: both end on or before 200.
    assert events_needing_later_data(events, last, ((-1, 1), (0, 3))) == []
    # Widest end +8: both run past it.
    assert events_needing_later_data(events, last, ((-1, 8),)) == ["fits", "too_late"]


def test_events_needing_later_data_counts_sessions_not_calendar_days():
    # 2024-07-03 + 1 session is 2024-07-05 (July 4 is a holiday).
    events = make_events([pd.Timestamp("2024-07-03")])
    assert events_needing_later_data(events, pd.Timestamp("2024-07-05"), ((0, 1),)) == []
    assert events_needing_later_data(events, pd.Timestamp("2024-07-03"), ((0, 1),)) == [
        "test_event_0"
    ]


# --- End to end ---------------------------------------------------------------


def test_csv_to_results(sim, tmp_path):
    """A fake CSV row timed on the simulated day 0, through load and run."""
    security, benchmark, day0 = sim
    announced = f"{day0.date()} 10:00"
    events = load_events(write_events(tmp_path, [valid_row(announcement_datetime_et=announced)]))
    assert events.loc[0, "day0"] == day0

    results, abnormal = run_events(events, security, benchmark)
    assert list(results.columns[: len(CARRIED_COLUMNS)]) == list(CARRIED_COLUMNS)
    assert pd.isna(results.loc[0, "error"])
    assert results.loc[0, "t_[-1,+1]"] > 1.96
    assert abnormal.index.tolist() == ["test_event_1"]
