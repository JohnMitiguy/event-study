"""Tests for the output paths in scripts/run_opec.py.

scripts/ is not a package, so the script is loaded from its file path.
Loading it runs only the module-level code (imports and constants), not
main(), so nothing is downloaded or written.
"""

import importlib.util
from pathlib import Path

import pandas as pd

# pytest puts the tests/ folder on the import path (see test_runner.py).
from test_events import valid_row, write_events

from event_study.event_days import nyse_calendar

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

    def must_not_run(*args, **kwargs):
        raise AssertionError("dates-only must not compute returns or run the model")

    monkeypatch.setattr(run_opec, "simple_returns", must_not_run)
    monkeypatch.setattr(run_opec, "run_events", must_not_run)

    run_opec.dates_only(prices, use_leak=True)

    out = capsys.readouterr().out
    assert "no returns, regressions or CARs computed" in out
    lines = {line.split()[0]: line.split() for line in out.splitlines() if line[:2] in ("a ", "b ")}
    # Row 330's estimation window (ends at row 320) skips row 300's 11 days:
    # masked 11, span 120 + 11. The windows themselves do not touch: nearby 0.
    assert lines["a"][1] == str(day_a.date())
    assert lines["a"][4:] == ["0", "120", "0"]
    assert lines["b"][4:] == ["11", "131", "0"]
    # est_end is day -10 for both (no skipped day there).
    assert lines["b"][3] == str(sessions[330 - 10].date())


def test_dates_only_flag_is_parsed(monkeypatch):
    run_opec = load_script()
    monkeypatch.setattr("sys.argv", ["run_opec.py", "--dates-only"])
    assert run_opec.parse_args().dates_only is True
    monkeypatch.setattr("sys.argv", ["run_opec.py"])
    assert run_opec.parse_args().dates_only is False
