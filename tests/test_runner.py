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
    estimation_dates,
    estimation_days,
    events_needing_later_data,
    other_event_days,
    overlap_diagnostics,
    result_columns,
    run_events,
)
from event_study.simulate import DAY0_POSITION, planted_event
from event_study.windows import (
    DEFAULT_EST_LENGTH,
    DEFAULT_EVENT_WINDOWS,
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
            "time_assumed": False,
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
    # One event alone has nothing to skip: the plain 120-day window.
    assert row["est_start"] == sec_est.index[0]
    assert row["est_end"] == sec_est.index[-1]
    assert row["est_masked_days"] == 0
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


# --- Calendar check: the dates must be exactly the NYSE sessions --------------


def test_missing_session_raises(sim):
    security, benchmark, day0 = sim
    # Dropping a row from the middle would shift every later window by a day.
    short = security.drop(security.index[100])
    with pytest.raises(ValueError, match=r"(?s)security_returns.*Missing sessions \(1\)") as info:
        run_events(make_events([day0]), short, benchmark)
    assert not isinstance(info.value, EventDataError)


def test_non_session_date_raises(sim):
    security, benchmark, day0 = sim
    # 2024-07-04 is a weekday and an NYSE holiday. Replace the row after it
    # with the holiday so the row count stays the same.
    dates = benchmark.index.to_list()
    row = dates.index(pd.Timestamp("2024-07-05"))
    dates[row] = pd.Timestamp("2024-07-04")
    holiday = benchmark.set_axis(pd.DatetimeIndex(dates))
    with pytest.raises(ValueError, match=r"(?s)benchmark_returns.*Non-session dates \(1\)"):
        run_events(make_events([day0]), security, holiday)


def test_calendar_check_message_names_the_dates(sim):
    security, benchmark, day0 = sim
    short = benchmark.drop(benchmark.index[100])
    with pytest.raises(ValueError, match=str(benchmark.index[100].date())):
        run_events(make_events([day0]), security, short)


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


def test_default_column_order_is_unchanged():
    """The OPEC+ results columns, in the order they have always had."""
    assert result_columns(DEFAULT_EVENT_WINDOWS)[:8] == [
        "event_id", "decision_group", "direction", "surprise_flag",
        "event_time", "used_leak", "day0", "time_assumed",
    ]  # fmt: skip
    assert list(CARRIED_COLUMNS) == result_columns(DEFAULT_EVENT_WINDOWS)[:8]
    assert result_columns(DEFAULT_EVENT_WINDOWS)[8:] == [
        "alpha", "beta", "resid_std", "n", "est_start", "est_end", "est_masked_days",
        "car_[-1,+1]", "t_[-1,+1]", "car_[-5,+5]", "t_[-5,+5]",
        "nearby_events", "nearby_mask_events", "status", "error",
    ]  # fmt: skip


def test_other_group_columns_run_without_decision_group_or_direction(sim):
    """An event type with its own group column, and no OPEC+ columns, runs."""
    security, benchmark, day0 = sim
    events = make_events([day0]).drop(columns=["decision_group", "direction"])
    events["route"] = "red_sea"
    results, _ = run_events(events, security, benchmark, group_columns=("route",))
    assert list(results.columns) == result_columns(DEFAULT_EVENT_WINDOWS, ("route",))
    assert list(results.columns[:3]) == ["event_id", "route", "surprise_flag"]
    assert "direction" not in results.columns
    assert results.loc[0, "route"] == "red_sea"
    assert results.loc[0, "status"] == "ok"
    # Same numbers as the default run: group columns are only carried along.
    default, _ = run_events(make_events([day0]), security, benchmark)
    assert results.loc[0, "car_[-1,+1]"] == default.loc[0, "car_[-1,+1]"]
    # The date-only helpers take the same group_columns.
    dates = estimation_dates(security.index, events, group_columns=("route",))
    assert pd.isna(dates.loc[0, "error"])
    assert len(estimation_days(security.index, events, group_columns=("route",))) == 1
    # Without group_columns the OPEC+ columns are still required.
    with pytest.raises(ValueError, match="missing column.*decision_group"):
        run_events(events, security, benchmark)


def test_group_column_that_repeats_a_core_column_raises(sim):
    security, benchmark, day0 = sim
    with pytest.raises(ValueError, match="group_columns repeats"):
        run_events(make_events([day0]), security, benchmark, group_columns=("day0",))


def test_duplicate_event_id_raises(sim):
    security, benchmark, day0 = sim
    events = make_events([day0, day0], ids=["same", "same"])
    with pytest.raises(ValueError, match="duplicate event_id"):
        run_events(events, security, benchmark)


# --- Overlap: nearby events and skipped estimation days -----------------------

# Real NYSE sessions, since skipped days and nearby_events count session
# positions. SESSIONS[k] is k sessions after 2023-01-03.
SESSIONS = nyse_calendar().sessions_in_range("2023-01-03", "2025-12-31")


def diagnostics(day0s):
    """nearby_events with the default event windows."""
    return overlap_diagnostics(pd.Series(day0s), DEFAULT_EVENT_WINDOWS)


def diagnostics_for(positions):
    """Diagnostics for events at these positions in SESSIONS."""
    return diagnostics([SESSIONS[p] for p in positions])


def test_nearby_counts():
    # Widest window is days -5..+5. A at 150: 145..155. B at 130: 125..135.
    # C at 158: 153..163. A and C share 153..155; B shares nothing.
    diag = diagnostics_for([150, 130, 158])
    assert diag["nearby_events"].tolist() == [1, 0, 1]


def test_same_day_events_are_nearby():
    diag = diagnostics_for([150, 150])
    assert diag["nearby_events"].tolist() == [1, 1]


def test_event_after_the_data_end_still_counts():
    # Data is SESSIONS[0..199]. A's day 0 is row 197, so its widest window is
    # 192..202 and runs past the data. B's day 0 is two sessions after the
    # last row (position 201): widest window 196..206. They share 196..202.
    data = SESSIONS[:200]
    a, b = data[197], SESSIONS[201]
    assert b not in data
    diag = diagnostics([a, b])
    assert diag["nearby_events"].tolist() == [1, 1]


def test_event_before_the_data_start_still_counts():
    # Data starts at SESSIONS[10]. B's day 0 is SESSIONS[9], one session
    # before the first row: widest window 4..14, of which 10..14 are in the
    # data. A is SESSIONS[139]: widest window 134..144.
    data = SESSIONS[10:310]
    a, b = data[129], SESSIONS[9]
    assert b not in data
    skip_a, skip_b = other_event_days(pd.Series([a, b]), DEFAULT_EVENT_WINDOWS)
    # A skips all of B's days, inside the data or not.
    assert skip_a.equals(SESSIONS[4:15])
    assert skip_b.equals(SESSIONS[134:145])
    assert diagnostics([a, b])["nearby_events"].tolist() == [0, 0]


def test_non_session_day0_raises():
    with pytest.raises(ValueError, match="not an NYSE session"):
        diagnostics([pd.Timestamp("2024-07-04")])  # Independence Day


def test_overlap_columns_in_results(sim):
    security, benchmark, day0 = sim
    events = make_events([day0, security.index[DAY0_POSITION + 3]])
    results, _ = run_events(events, security, benchmark)
    assert results["nearby_events"].tolist() == [1, 1]
    assert results["est_masked_days"].dtype == "Int64"
    # kind "M" means a datetime64 (date) column.
    assert results["est_start"].dtype.kind == "M"
    assert results["est_end"].dtype.kind == "M"


def session_returns(n: int = 300) -> tuple[pd.Series, pd.Series]:
    """Clean (security, benchmark) returns on SESSIONS[0..n-1].

    Data row k is SESSIONS[k], so row numbers and session positions agree.
    """
    dates = SESSIONS[:n]
    rng = np.random.default_rng(11)
    benchmark = rng.normal(0.0, 0.01, n)
    security = 1.2 * benchmark + rng.normal(0.0, 0.01, n)
    return pd.Series(security, index=dates), pd.Series(benchmark, index=dates)


def run_at(positions, event_windows=DEFAULT_EVENT_WINDOWS) -> pd.DataFrame:
    """Results for events at these SESSIONS positions, indexed by id "e<position>"."""
    security, benchmark = session_returns()
    events = make_events([SESSIONS[p] for p in positions], ids=[f"e{p}" for p in positions])
    results, _ = run_events(events, security, benchmark, event_windows=event_windows)
    return results.set_index("event_id")


def est_rows(row) -> tuple:
    """(first row, last row, masked days) of one event's estimation window."""
    return (
        SESSIONS.get_loc(row["est_start"]),
        SESSIONS.get_loc(row["est_end"]),
        row["est_masked_days"],
    )


def test_estimation_skips_other_events_days():
    # Defaults: widest window -5..+5, 120 estimation days up to day -10.
    # B at 130: rows up to 120, nothing to skip: rows 1..120.
    # A at 150: rows up to 140, skipping B's 125..135 (11 days), so it
    #   reaches 11 rows further back: 10..140.
    # C at 158: rows up to 148, but A's window covers 145..148, so it ends
    #   on 144; with B's 125..135 that is 15 days skipped: 14..144.
    results = run_at([150, 130, 158])
    assert est_rows(results.loc["e130"]) == (1, 120, 0)
    assert est_rows(results.loc["e150"]) == (10, 140, 11)
    assert est_rows(results.loc["e158"]) == (14, 144, 15)
    assert (results["n"] == DEFAULT_EST_LENGTH).all()
    assert (results["status"] == "ok").all()


def test_fit_uses_exactly_the_unskipped_days():
    # A at 150 with B at 130: refit by hand on rows 10..140 without 125..135.
    security, benchmark = session_returns()
    results = run_at([150, 130])
    used = SESSIONS[[*range(10, 125), *range(136, 141)]]
    fit = fit_market_model(security.loc[used], benchmark.loc[used], min_obs=DEFAULT_EST_LENGTH)
    row = results.loc["e150"]
    assert row["alpha"] == pytest.approx(fit.alpha)
    assert row["beta"] == pytest.approx(fit.beta)
    assert row["resid_std"] == pytest.approx(fit.resid_std)


def test_skipped_day_minus_gap_ends_the_window_earlier():
    # B at 145: widest window 140..150 covers A's day -10 (row 140), so A's
    # window ends on row 139 instead and runs 20..139. B's own window (rows
    # 16..135) has nothing to skip.
    results = run_at([150, 145])
    assert est_rows(results.loc["e150"]) == (20, 139, 1)
    assert est_rows(results.loc["e145"]) == (16, 135, 0)


def test_skipped_days_come_from_the_widest_configured_window():
    # B at 120. With windows (-1, +1) and (0, +3) the widest is -1..+3, so A
    # skips B's 119..123 (5 days); with the defaults, 115..125 (11 days).
    narrow = run_at([150, 120], event_windows=((-1, 1), (0, 3)))
    assert est_rows(narrow.loc["e150"]) == (16, 140, 5)
    assert est_rows(run_at([150, 120]).loc["e150"]) == (10, 140, 11)


def test_failed_event_still_masks():
    # B at 120 fails: its window would start at row 120 - 129 = -9. Its
    # reaction still happened, so A still skips its days.
    results = run_at([150, 120])
    assert results.loc["e120", "status"] == "failed"
    assert est_rows(results.loc["e150"]) == (10, 140, 11)


def test_reaching_back_past_the_first_row_fails_the_event():
    # A at 135 alone: rows 6..125. With B at 120 it skips B's 115..125
    # (11 days) and would have to start at row -5: 5 rows short.
    assert run_at([135]).loc["e135", "status"] == "ok"
    row = run_at([135, 120]).loc["e135"]
    assert row["status"] == "failed"
    assert "estimation window needs 5 more row(s)" in row["error"]
    assert "11 day(s) were skipped as inside other events' windows" in row["error"]
    assert pd.isna(row["est_start"])
    assert pd.isna(row["est_end"])
    assert pd.isna(row["est_masked_days"])


@pytest.mark.parametrize("earlier", [[], [130]], ids=["alone", "with_earlier_event"])
def test_later_event_never_changes_an_earlier_events_row(earlier):
    """A at 150, run with and without C at 158, a later event whose widest
    window (153..163) overlaps A's own (145..155).

    Only nearby_events may differ: it counts neighbours on both sides on
    purpose. With an earlier B at 130, A skips B's 11 days in both runs.
    """
    without = run_at([*earlier, 150]).drop(columns="nearby_events")
    with_later = run_at([*earlier, 150, 158]).drop(columns="nearby_events")
    # loc[["e150"]] (a list) keeps a one-row table, so each column keeps its type.
    pd.testing.assert_frame_equal(with_later.loc[["e150"]], without.loc[["e150"]], check_exact=True)
    assert without.loc["e150", "est_masked_days"] == 11 * len(earlier)


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


# --- estimation_dates: the windows without any returns -------------------------


def test_estimation_dates_match_a_real_run(sim):
    security, benchmark, _ = sim
    # Row 150 skips row 50's 11 days (event 50 itself fails: too little
    # history). Row 160's estimation window ends at row 150, where row 150's
    # own days 145..150 begin, so it skips those 6 plus row 50's 11.
    events = make_events([security.index[p] for p in (150, 160, 50)])
    results, _ = run_events(events, security, benchmark)
    table = estimation_dates(security.index, events)

    for column in ("est_start", "est_end", "est_masked_days", "nearby_events"):
        pd.testing.assert_series_equal(table[column], results[column], check_names=False)
    assert table["est_masked_days"].tolist()[:2] == [11, 17]
    assert table["error"].isna().tolist() == [True, True, False]
    assert table.loc[2, "error"] == results.loc[2, "error"]
    assert table.loc[2, ["est_start", "est_end", "est_masked_days", "est_span_days"]].isna().all()


def test_estimation_span_counts_trading_days_from_start_to_end(sim):
    security, _, _ = sim
    events = make_events([security.index[150], security.index[175]])
    table = estimation_dates(security.index, events, est_length=60, gap=6)
    # No skipped days: the span is est_length. Skipped days add to it.
    assert table["est_span_days"].tolist() == [60, 60 + 11]
    first = security.index.get_loc(table.loc[1, "est_start"])
    last = security.index.get_loc(table.loc[1, "est_end"])
    assert last - first + 1 == 71


def test_estimation_dates_need_only_dates_and_check_the_calendar(sim):
    security, _, day0 = sim
    events = make_events([day0])
    # A date index is enough: no returns are passed in.
    assert pd.isna(estimation_dates(security.index, events).loc[0, "error"])
    with pytest.raises(ValueError, match=r"(?s)dates.*Missing sessions \(1\)"):
        estimation_dates(security.index.delete(100), events)


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


# --- Mask-only events ----------------------------------------------------------


def test_mask_days_are_skipped_and_counted_as_nearby():
    # Event at 150 (widest window 145..155). Mask at 130 (125..135) falls in
    # its estimation window; mask at 158 (153..163) overlaps its own window.
    (skip,) = other_event_days(pd.Series([SESSIONS[150]]), DEFAULT_EVENT_WINDOWS, [SESSIONS[130]])
    assert skip.equals(SESSIONS[125:136])
    diag = overlap_diagnostics(
        pd.Series([SESSIONS[150]]), DEFAULT_EVENT_WINDOWS, [SESSIONS[130], SESSIONS[158]]
    )
    assert diag["nearby_events"].tolist() == [0]
    assert diag["nearby_mask_events"].tolist() == [1]


def test_a_mask_acts_like_an_event_with_no_results_row():
    """Masking row 140 gives the same numbers as running it as a second event."""
    security, benchmark = session_returns()
    masked, _ = run_events(make_events([SESSIONS[170]]), security, benchmark, mask_day0s=[SESSIONS[140]])
    both, _ = run_events(make_events([SESSIONS[140], SESSIONS[170]]), security, benchmark)
    assert len(masked) == 1
    assert masked.loc[0, "est_masked_days"] == 11
    same = [c for c in masked.columns if c not in ("event_id", "nearby_events", "nearby_mask_events")]
    pd.testing.assert_frame_equal(masked[same], both.iloc[[1]][same].reset_index(drop=True))
    table = estimation_dates(security.index, make_events([SESSIONS[170]]), mask_day0s=[SESSIONS[140]])
    assert table.loc[0, "est_start"] == masked.loc[0, "est_start"]
    assert table.loc[0, "est_masked_days"] == 11


def test_no_masks_changes_nothing():
    security, benchmark = session_returns()
    events = make_events([SESSIONS[150], SESSIONS[200]])
    default, _ = run_events(events, security, benchmark)
    empty, _ = run_events(events, security, benchmark, mask_day0s=[])
    pd.testing.assert_frame_equal(default, empty)
    assert default["nearby_mask_events"].tolist() == [0, 0]


def test_estimation_days_are_the_fitted_days():
    """120 days per event, none inside another event's or a mask's window."""
    security, benchmark = session_returns()
    events = make_events([SESSIONS[150], SESSIONS[200]], ids=["a", "b"])
    days = estimation_days(security.index, events, mask_day0s=[SESSIONS[120]])
    results, _ = run_events(events, security, benchmark, mask_day0s=[SESSIONS[120]])
    for i, event_id in enumerate(["a", "b"]):
        assert len(days[event_id]) == DEFAULT_EST_LENGTH
        assert days[event_id][0] == results.loc[i, "est_start"]
        assert days[event_id][-1] == results.loc[i, "est_end"]
    assert not days["a"].isin(SESSIONS[115:126]).any()  # the mask's window
    assert not days["b"].isin(SESSIONS[145:156]).any()  # a's window
    # An event with too little history is left out, as run_events would fail it.
    short = estimation_days(security.index, make_events([SESSIONS[50]], ids=["c"]))
    assert short == {}
