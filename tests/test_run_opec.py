"""Tests for the output paths in scripts/run_opec.py.

scripts/ is not a package, so the script is loaded from its file path.
Loading it runs only the module-level code (imports and constants), not
main(), so nothing is downloaded or written.
"""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

# pytest puts the tests/ folder on the import path (see test_runner.py).
from test_events import mask_row, valid_row, write_events

from event_study.aggregate import across_event_tests
from event_study.event_days import nyse_calendar
from event_study.events import MASK_COLUMNS

SCRIPT = Path(__file__).parents[1] / "scripts" / "run_opec.py"


def load_script():
    spec = importlib.util.spec_from_file_location("run_opec", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_output_paths():
    run_opec = load_script()
    assert run_opec.output_paths(official_time=False) == (
        Path("results") / "opec_results.csv",
        Path("results") / "opec_run_info.json",
        Path("charts") / "opec_events.png",
    )


def test_official_time_output_paths():
    run_opec = load_script()
    assert run_opec.output_paths(official_time=True) == (
        Path("results") / "opec_results_official_time.csv",
        Path("results") / "opec_run_info_official_time.json",
        Path("charts") / "opec_events_official_time.png",
    )


def test_official_time_never_overwrites_main_outputs():
    run_opec = load_script()
    main = set(run_opec.output_paths(official_time=False))
    official = set(run_opec.output_paths(official_time=True))
    assert main.isdisjoint(official)


def test_dates_only_prints_windows_and_computes_nothing(tmp_path, monkeypatch, capsys):
    run_opec = load_script()
    sessions = nyse_calendar().sessions_in_range("2023-01-03", "2025-12-31")
    # Prices are all NaN: if any return were computed there would be NaNs to
    # trip over, and the two calls below are made to fail if reached.
    prices = {t: pd.Series(float("nan"), index=sessions) for t in ("XLE", "SPY")}
    day_a, day_b = sessions[300], sessions[330]
    rows = [
        valid_row(event_id="a", announcement_datetime_et=f"{day_a.date()} 10:00"),
        valid_row(event_id="b", announcement_datetime_et=f"{day_b.date()} 10:00"),
    ]
    monkeypatch.setattr(run_opec, "EVENTS_PATH", write_events(tmp_path, rows))
    # One mask-only event at row 200, inside both estimation windows.
    mask_dir = tmp_path / "masks"
    mask_dir.mkdir()
    mask = mask_row(announcement_datetime_et=f"{sessions[200].date()} 10:00")
    monkeypatch.setattr(run_opec, "MASK_PATH", write_events(mask_dir, [mask], MASK_COLUMNS))

    def must_not_run(*args, **kwargs):
        raise AssertionError("dates-only must not compute returns or run the model")

    monkeypatch.setattr(run_opec, "simple_returns", must_not_run)
    monkeypatch.setattr(run_opec, "run_events", must_not_run)

    run_opec.dates_only(prices, use_leak=True)

    out = capsys.readouterr().out
    assert "no returns, regressions or CARs computed" in out
    lines = {line.split()[0]: line.split() for line in out.splitlines() if line[:2] in ("a ", "b ")}
    # Row 300's estimation window skips the mask's 11 days (195..205): masked
    # 11, span 120 + 11. Row 330's (ends at row 320) skips row 300's 11 days
    # and the mask's: masked 22, span 142. No window touches another event's
    # or the mask's: nearby 0, n_mask 0.
    assert "Mask-only events (1;" in out
    assert lines["a"][1] == str(day_a.date())
    assert lines["a"][4:] == ["11", "131", "0", "0"]
    assert lines["b"][4:] == ["22", "142", "0", "0"]
    # est_end is day -10 for both (no skipped day there).
    assert lines["b"][3] == str(sessions[330 - 10].date())


def test_dates_only_flag_is_parsed(monkeypatch):
    run_opec = load_script()
    monkeypatch.setattr("sys.argv", ["run_opec.py", "--dates-only"])
    assert run_opec.parse_args().dates_only is True
    monkeypatch.setattr("sys.argv", ["run_opec.py"])
    assert run_opec.parse_args().dates_only is False


def simulated_results(directions, failed_row=None):
    """run_events results on long simulated returns, one event per direction.

    Events are 25 sessions apart starting at row 150, so each has a full
    estimation window and none overlaps another. failed_row adds one more
    event at that row (row 20 has too little history, so it fails).
    """
    from event_study.runner import run_events
    from event_study.simulate import fake_returns

    security, benchmark = fake_returns(np.random.default_rng(7), n_days=150 + 25 * len(directions) + 20)
    rows = [150 + 25 * i for i in range(len(directions))]
    ids = [f"sim_{i}" for i in range(len(directions))]
    if failed_row is not None:
        rows, ids, directions = [*rows, failed_row], [*ids, "sim_failed"], [*directions, "cut"]
    events = pd.DataFrame(
        {
            "event_id": ids,
            "decision_group": "ministerial",
            "direction": directions,
            "surprise_flag": pd.array([pd.NA] * len(ids), dtype="Int64"),
            "event_time": pd.NaT,
            "used_leak": False,
            "day0": security.index[rows],
            "time_assumed": False,
        }
    )
    results, _ = run_events(events, security, benchmark, 120, 10, ((-1, 1), (-5, 5)))
    return results


def test_across_event_table_on_simulated_data():
    run_opec = load_script()
    directions = ["cut"] * 6 + ["increase"] * 5 + ["hold"] * 4
    results = simulated_results(directions, failed_row=20)
    assert (results["status"] == "failed").sum() == 1
    table = run_opec.across_event_table(results, ((-1, 1), (-5, 5)))

    assert list(table["window"].unique()) == ["[-1,+1]", "[-5,+5]"]
    wide = table[table["window"] == "[-1,+1]"].set_index("group")
    # The failed event is a cut and is not counted: 6 cuts ok, not 7.
    assert wide["n_ok"].to_dict() == {
        "all": 15, "cut": 6, "increase": 5, "hold": 4, "saudi_unilateral": 0
    }  # fmt: skip
    assert wide["tested"].to_dict() == {
        "all": True, "cut": True, "increase": True, "hold": False, "saudi_unilateral": False
    }  # fmt: skip
    # Headline: [-1,+1], cut and increase only.
    headline = table[table["headline"]]
    assert list(zip(headline["window"], headline["group"], strict=True)) == [
        ("[-1,+1]", "cut"),
        ("[-1,+1]", "increase"),
    ]
    assert wide.loc["hold", "note"] == "too few events (N < 5)"
    assert wide.loc["hold", ["mean_car", "bmp_t", "sign_p"]].isna().all()

    # Numbers are exactly what aggregate.across_event_tests gives on the same rows.
    direct = across_event_tests(results[results["direction"] == "cut"], (-1, 1))
    assert wide.loc["cut", "mean_car"] == direct.mean_car
    assert wide.loc["cut", "cross_sectional_t"] == direct.tests.loc["cross_sectional_t", "statistic"]
    assert wide.loc["cut", "bmp_t"] == direct.tests.loc["bmp", "statistic"]
    assert wide.loc["cut", "wilcoxon_p"] == direct.tests.loc["wilcoxon", "p_value"]
    assert wide.loc["cut", "sign_p"] == direct.tests.loc["sign", "p_value"]


def test_pilot_sized_results_are_not_tested(capsys):
    run_opec = load_script()
    results = simulated_results(["cut", "hold", "cut"])
    table = run_opec.across_event_table(results, ((-1, 1), (-5, 5)))
    assert not table["tested"].any()
    assert (table["note"] == "too few events (N < 5)").all()
    run_opec.print_across_event(table, results)
    out = capsys.readouterr().out
    assert out.count("too few events (N < 5)") == 10  # 5 groups x 2 windows
    assert "excluded from the across-event tests: none" in out


def test_print_lists_every_excluded_event_with_reason(capsys):
    run_opec = load_script()
    results = simulated_results(["cut"] * 5, failed_row=20)
    table = run_opec.across_event_table(results, ((-1, 1),))
    run_opec.print_across_event(table, results)
    out = capsys.readouterr().out
    assert "excluded from the across-event tests (1)" in out
    failed_line = next(line for line in out.splitlines() if "sim_failed" in line)
    assert "failed" in failed_line
    assert results.loc[results["event_id"] == "sim_failed", "error"].iloc[0] in failed_line


def test_across_event_path_keeps_official_time_separate():
    run_opec = load_script()
    assert run_opec.across_event_path(False) == Path("results") / "opec_across_event.csv"
    assert run_opec.across_event_path(True) == Path("results") / "opec_across_event_official_time.csv"


def test_shift_assumed_output_paths_are_separate():
    run_opec = load_script()
    main = set(run_opec.output_paths(official_time=False))
    shifted = set(run_opec.output_paths(official_time=False, shift_assumed=True))
    assert main.isdisjoint(shifted)
    assert run_opec.across_event_path(False, True) == (
        Path("results") / "opec_across_event_day0_shifted.csv"
    )


def test_shift_assumed_flag_is_parsed(monkeypatch):
    run_opec = load_script()
    monkeypatch.setattr("sys.argv", ["run_opec.py", "--shift-assumed"])
    assert run_opec.parse_args().shift_assumed is True


def test_firm_only_cut_group_with_three_events_says_too_few(capsys):
    """Without time_assumed rows only 3 cuts remain: shown as too few, no crash."""
    run_opec = load_script()
    results = simulated_results(["cut"] * 6 + ["increase"] * 6)
    results["time_assumed"] = [False, False, False, True, True, True] + [False] * 6
    firm = run_opec.firm_only(results)
    table = run_opec.across_event_table(firm, ((-1, 1),))
    by_group = table.set_index("group")
    assert by_group.loc["cut", "n_ok"] == 3
    assert not by_group.loc["cut", "tested"]
    assert by_group.loc["cut", "note"] == "too few events (N < 5)"
    assert by_group.loc["all", "tested"]
    run_opec.print_across_event(table, firm)
    run_opec.print_time_assumed_excluded(results)
    out = capsys.readouterr().out
    assert "too few events (N < 5)" in out
    assert "Left out of the firm_only sample (3)" in out
    assert out.count("time_assumed: announcement time not sourced") == 3


def test_saudi_rows_are_kept_out_of_the_group_results():
    """saudi_unilateral rows are their own group, never in all/cut (DECISIONS.md)."""
    run_opec = load_script()
    results = simulated_results(["cut"] * 11)
    results.loc[5:, "decision_group"] = "saudi_unilateral"
    table = run_opec.across_event_table(results, ((-1, 1),)).set_index("group")
    assert table["n_ok"].to_dict() == {
        "all": 5, "cut": 5, "increase": 0, "hold": 0, "saudi_unilateral": 6
    }  # fmt: skip
    direct = across_event_tests(results.iloc[:5], (-1, 1))
    assert table.loc["cut", "mean_car"] == direct.mean_car
    assert table.loc["saudi_unilateral", "tested"]


def test_caar_paths_are_separate_per_run():
    run_opec = load_script()
    assert run_opec.caar_paths(False) == (
        Path("results") / "opec_abnormal.csv",
        Path("charts") / "opec_caar.png",
    )
    assert set(run_opec.caar_paths(False)).isdisjoint(run_opec.caar_paths(True, True))


def test_average_car_path_ends_at_the_mean_wide_car():
    """The last point of the average path is the group's mean [-5,+5] CAR."""
    from event_study.runner import run_events
    from event_study.simulate import fake_returns

    run_opec = load_script()
    security, benchmark = fake_returns(np.random.default_rng(3), n_days=320)
    events = pd.DataFrame(
        {
            "event_id": ["a", "b", "c"],
            "decision_group": "ministerial",
            "direction": ["cut", "cut", "increase"],
            "surprise_flag": pd.array([pd.NA] * 3, dtype="Int64"),
            "event_time": pd.NaT,
            "used_leak": False,
            "day0": security.index[[150, 200, 250]],
            "time_assumed": False,
        }
    )
    results, abnormal = run_events(events, security, benchmark)
    path = run_opec.average_car_path(results, abnormal, "cut")
    assert list(path.index) == list(range(-5, 6))
    expected = results.loc[results["direction"] == "cut", "car_[-5,+5]"].mean()
    assert np.isclose(path.iloc[-1], expected)


def test_largest_residual_days_rank_by_residual_not_raw_return():
    run_opec = load_script()
    dates = nyse_calendar().sessions_in_range("2024-01-02", "2024-03-29")
    rng = np.random.default_rng(5)
    benchmark = pd.Series(rng.normal(0, 0.01, len(dates)), index=dates)
    security = 1.5 * benchmark + pd.Series(rng.normal(0, 0.002, len(dates)), index=dates)
    # Day 10: a market-wide crash (big raw return, small residual).
    # Day 20: an energy-only jump (residual +6%).
    benchmark.iloc[10] -= 0.08
    security.iloc[10] -= 1.5 * 0.08
    security.iloc[20] += 0.06
    top = run_opec.largest_residual_days(security, benchmark, 1)
    assert top.index[0] == dates[20]


def test_outlier_filter_drops_only_events_fitted_on_an_outlier_day():
    run_opec = load_script()
    results = simulated_results(["cut"] * 3)
    est = {
        "sim_0": pd.DatetimeIndex(["2020-01-02", "2020-01-03"]),
        "sim_1": pd.DatetimeIndex(["2020-01-06"]),
        "sim_2": pd.DatetimeIndex(["2020-01-07"]),
    }
    hits = run_opec.outlier_hits(est, pd.DatetimeIndex(["2020-01-03", "2020-01-08"]))
    assert hits == {"sim_0": [pd.Timestamp("2020-01-03")]}
    assert run_opec.without_outliers(results, hits)["event_id"].tolist() == ["sim_1", "sim_2"]
