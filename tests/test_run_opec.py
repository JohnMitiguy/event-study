"""Tests for scripts/run_opec.py: output paths, dates-only, the across-event
table, the outlier sample and (v1.1) the supply-route attack masks.

Every event row is fake (example.com sources) and every return is simulated.

scripts/ is not a package, so the script is loaded from its file path.
Loading it runs only the module-level code (imports and constants), not
main(), so nothing is downloaded or written.
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# pytest puts the tests/ folder on the import path (see test_runner.py).
from test_events import mask_row, valid_row, write_events
from test_supply_route import supply_row

from event_study import reporting
from event_study.aggregate import across_event_tests
from event_study.event_days import nyse_calendar
from event_study.events import MASK_COLUMNS, SUPPLY_ROUTE_COLUMNS, load_events
from event_study.runner import run_events
from event_study.simulate import fake_returns

SCRIPT = Path(__file__).parents[1] / "scripts" / "run_opec.py"


def load_script():
    spec = importlib.util.spec_from_file_location("run_opec", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def point_attack_files(run_opec, monkeypatch, tmp_path, attacks, attack_masks) -> None:
    """Write fake supply-route events and mask-only files and point the script at them."""
    for name, rows, columns, attr in (
        ("attacks", attacks, SUPPLY_ROUTE_COLUMNS, "SUPPLY_ROUTE_EVENTS_PATH"),
        ("attack_masks", attack_masks, MASK_COLUMNS, "SUPPLY_ROUTE_MASK_PATH"),
    ):
        folder = tmp_path / name
        folder.mkdir()
        monkeypatch.setattr(run_opec, attr, write_events(folder, rows, columns))


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
    # No attacks: header-only supply-route files, so the real ones are not read.
    point_attack_files(run_opec, monkeypatch, tmp_path, [], [])

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


# --- Supply-route attacks in the OPEC+ masks (v1.1) ----------------------------------

# Simulated sessions (fake_returns uses the same ones), so a row number here
# is a day 0 in the simulated data.
SIM_DATES = fake_returns(np.random.default_rng(0), n_days=320)[0].index


def at(row: int, clock: str = "10:00") -> str:
    """announcement_datetime_et for simulated session `row` at this time."""
    return f"{SIM_DATES[row].date()} {clock}"


# Two counted attacks (the second after the close, so day 0 is the next
# session) and three mask-only attacks: one firm, one time_assumed (masked
# on its date and the next session), one on a counted attack's day (kept once).
ATTACKS = [
    supply_row(event_id="attack_a", announcement_datetime_et=at(140)),
    supply_row(event_id="attack_b", announcement_datetime_et=at(200, "17:30")),
]
ATTACK_MASKS = [
    mask_row(event_id="m_firm", announcement_datetime_et=at(170)),
    mask_row(event_id="m_assumed", announcement_datetime_et=at(250, "12:00"), time_assumed="1"),
    mask_row(event_id="m_same_day", announcement_datetime_et=at(140, "11:00")),
]
EXPECTED_ATTACK_DAY0S = pd.DatetimeIndex(SIM_DATES[[140, 170, 201, 250, 251]])
# The OPEC+ mask-only row: time_assumed, so --shift-assumed moves it a session.
OPEC_MASK = mask_row(
    event_id="opec_mask", announcement_datetime_et=at(60, "12:00"), time_assumed="1"
)


def point_opec_mask_file(run_opec, monkeypatch, tmp_path) -> None:
    folder = tmp_path / "opec_masks"
    folder.mkdir()
    monkeypatch.setattr(run_opec, "MASK_PATH", write_events(folder, [OPEC_MASK], MASK_COLUMNS))


def expected_mask_day0s(shift_assumed: bool) -> pd.DatetimeIndex:
    """The OPEC+ mask row (shifted or not) plus every attack day 0, sorted."""
    opec_day0 = SIM_DATES[61] if shift_assumed else SIM_DATES[60]
    return pd.DatetimeIndex([opec_day0]).append(EXPECTED_ATTACK_DAY0S).sort_values()


def test_attack_day0s_cover_counted_masked_and_shifted_rows(tmp_path, monkeypatch, capsys):
    run_opec = load_script()
    point_attack_files(run_opec, monkeypatch, tmp_path, ATTACKS, ATTACK_MASKS)
    day0s = run_opec.load_attack_masks()
    assert day0s.equals(EXPECTED_ATTACK_DAY0S)
    out = capsys.readouterr().out
    assert "Supply-route attacks masked (2 counted, 3 mask-only; 5 day 0s" in out
    for event_id in ("attack_a", "attack_b", "m_firm", "m_assumed", "m_same_day"):
        assert event_id in out
    assert f"and {SIM_DATES[251].date()} (time_assumed)" in out


def test_combined_mask_day0s_attack_part_ignores_the_shift_flag(tmp_path, monkeypatch):
    """--shift-assumed moves the OPEC+ mask row only; the attack day 0s stay put."""
    run_opec = load_script()
    point_attack_files(run_opec, monkeypatch, tmp_path, ATTACKS, ATTACK_MASKS)
    point_opec_mask_file(run_opec, monkeypatch, tmp_path)
    for shift in (False, True):
        combined, attacks = run_opec.load_mask_day0s(shift)
        assert attacks.equals(EXPECTED_ATTACK_DAY0S)
        assert combined.equals(expected_mask_day0s(shift))


def test_combined_mask_day0s_keeps_a_shared_day_once():
    run_opec = load_script()
    opec = pd.Series(pd.to_datetime(["2024-06-04", "2024-03-05"]))
    attacks = pd.DatetimeIndex(["2024-06-04", "2024-09-10"])
    combined = run_opec.combined_mask_day0s(opec, attacks)
    assert list(combined) == list(pd.to_datetime(["2024-03-05", "2024-06-04", "2024-09-10"]))


def spy_on(run_opec, monkeypatch, name: str, position: int, seen: dict) -> None:
    """Replace run_opec.<name> by a wrapper that records argument `position`
    (the mask day 0s) in seen[name], then calls the real function."""
    real = getattr(run_opec, name)

    def wrapper(*args, **kwargs):
        seen[name] = args[position]
        return real(*args, **kwargs)

    monkeypatch.setattr(run_opec, name, wrapper)


@pytest.mark.parametrize(
    "flags", [[], ["--official-time"], ["--shift-assumed"], ["--official-time", "--shift-assumed"]]
)
def test_dates_only_gets_the_combined_mask_day0s(tmp_path, monkeypatch, capsys, flags):
    """Every flag combination masks the same attack day 0s; only the OPEC+ mask row moves."""
    run_opec = load_script()
    # One OPEC+ event with a leak, so --official-time changes its day 0.
    event = valid_row(
        event_id="opec_a",
        announcement_datetime_et=at(230, "17:00"),
        leak_datetime_et=at(230, "11:00"),
        leak_source_url="https://example.com/leak",
    )
    folder = tmp_path / "opec_events"
    folder.mkdir()
    monkeypatch.setattr(run_opec, "EVENTS_PATH", write_events(folder, [event]))
    point_opec_mask_file(run_opec, monkeypatch, tmp_path)
    point_attack_files(run_opec, monkeypatch, tmp_path, ATTACKS, ATTACK_MASKS)
    prices = {t: pd.Series(float("nan"), index=SIM_DATES) for t in ("XLE", "SPY")}
    monkeypatch.setattr(run_opec, "load_cached", lambda ticker, refresh=False: prices[ticker])
    seen = {}
    # estimation_dates(dates, events, est_length, gap, event_windows, mask_day0s)
    spy_on(run_opec, monkeypatch, "estimation_dates", 5, seen)
    monkeypatch.setattr("sys.argv", ["run_opec.py", "--dates-only", *flags])
    run_opec.main()

    assert seen["estimation_dates"].equals(expected_mask_day0s("--shift-assumed" in flags))
    # attack_a (row 140), m_firm (170) and attack_b (201) are inside
    # opec_a's estimation window (about rows 101 to 220): 11 skipped days
    # each, whatever the flags.
    out = capsys.readouterr().out
    line = next(line.split() for line in out.splitlines() if line.startswith("opec_a "))
    assert line[4] == "33"


def test_main_passes_one_mask_set_to_run_events_and_estimation_days(
    tmp_path, monkeypatch, capsys
):
    """A full main() run on simulated prices: run_events (the results) and
    estimation_days (the no_outliers sample) get the same combined day 0s,
    and the run info records the supply-route files."""
    run_opec = load_script()
    security, benchmark = fake_returns(np.random.default_rng(21), n_days=320)
    prices = {"XLE": 100 * (1 + security).cumprod(), "SPY": 100 * (1 + benchmark).cumprod()}
    rows = [
        valid_row(event_id=f"opec_{row}", announcement_datetime_et=at(row))
        for row in (160, 200, 240, 280)
    ]
    folder = tmp_path / "opec_events"
    folder.mkdir()
    monkeypatch.setattr(run_opec, "EVENTS_PATH", write_events(folder, rows))
    point_opec_mask_file(run_opec, monkeypatch, tmp_path)
    point_attack_files(run_opec, monkeypatch, tmp_path, ATTACKS, ATTACK_MASKS)
    monkeypatch.setattr(run_opec, "load_cached", lambda ticker, refresh=False: prices[ticker])
    monkeypatch.setattr(reporting, "ticker_info", lambda ticker, series: {
        "first_date": "x", "last_date": "x", "rows": len(series), "cache_modified": "x",
        "dates_sha256": "0" * 64, "adj_close_sha256": "0" * 64,
    })  # fmt: skip
    seen = {}
    # run_events(events, security, benchmark, est_length, gap, event_windows, mask_day0s)
    spy_on(run_opec, monkeypatch, "run_events", 6, seen)
    # estimation_days(dates, events, est_length, gap, event_windows, mask_day0s)
    spy_on(run_opec, monkeypatch, "estimation_days", 5, seen)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["run_opec.py"])
    run_opec.main()

    expected = expected_mask_day0s(shift_assumed=False)
    assert seen["run_events"].equals(expected)
    assert seen["estimation_days"].equals(expected)

    results_path, run_info_path, _ = run_opec.output_paths(False)
    results = pd.read_csv(results_path).set_index("event_id")
    # opec_160's estimation window holds the OPEC+ mask row (row 60) and
    # attack_a (row 140): 11 skipped days each.
    assert results.loc["opec_160", "est_masked_days"] == 22

    info = json.loads(run_info_path.read_text(encoding="utf-8"))
    assert info["attack_mask_day0_count"] == len(EXPECTED_ATTACK_DAY0S)
    for key, path in (
        ("supply_route_events_file", run_opec.SUPPLY_ROUTE_EVENTS_PATH),
        ("supply_route_mask_file", run_opec.SUPPLY_ROUTE_MASK_PATH),
    ):
        assert info[key] == path.as_posix()
        assert info[f"{key}_sha256"] == reporting.file_sha256(path)
    # The keys from before v1.1 are all still there.
    for key in ("events_file_sha256", "mask_file_sha256", "use_leak", "shift_assumed", "est_length"):
        assert key in info
    assert "supply-route events sha256" in capsys.readouterr().out


def test_opec_confound_note_never_reaches_an_output(tmp_path):
    """Changing only confound_note leaves the results, abnormal returns and
    across-event table identical (DECISIONS.md: no output reads it)."""
    run_opec = load_script()
    security, benchmark = fake_returns(np.random.default_rng(9), n_days=320)
    windows = ((-1, 1), (-5, 5))
    outputs = []
    for i, note in enumerate(("", "2024-07-10 refinery outage (example.com), added after the run")):
        rows = [
            valid_row(event_id=f"opec_{row}", announcement_datetime_et=at(row), confound_note=note)
            for row in (150, 175, 200, 225, 250, 275)
        ]
        folder = tmp_path / f"notes_{i}"
        folder.mkdir()
        events = load_events(write_events(folder, rows))
        results, abnormal = run_events(events, security, benchmark, 120, 10, windows)
        outputs.append((results, abnormal, run_opec.across_event_table(results, windows)))
    first, second = outputs
    assert "confound_note" not in first[0].columns
    assert first[2]["tested"].any()
    for a, b in zip(first, second, strict=True):
        pd.testing.assert_frame_equal(a, b)
