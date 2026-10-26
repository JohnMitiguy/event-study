"""Tests for the supply-route loader and scripts/run_supply_route.py.

Every row here is fake (example.com sources) and every return is simulated.
The script is loaded from its file path, as in test_run_opec.py; loading it
runs only the imports and constants, so nothing is downloaded or written.
"""

import importlib.util
import itertools
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from statsmodels.stats.multitest import multipletests

# pytest puts the tests/ folder on the import path (see test_runner.py).
from test_events import mask_row, valid_row, write_events

from event_study import reporting
from event_study.aggregate import across_event_tests
from event_study.event_days import next_session, nyse_calendar
from event_study.events import (
    MASK_COLUMNS,
    SUPPLY_ROUTE_COLUMNS,
    load_supply_route_events,
)
from event_study.runner import run_events
from event_study.simulate import fake_returns

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
WINDOWS = ((0, 1), (-5, 5))


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def supply_row(**changes) -> dict:
    """A fake supply-route row that passes every check (Tuesday 2024-06-04, 10:00)."""
    row = {
        "event_id": "attack_1",
        "announcement_datetime_et": "2024-06-04 10:00",
        "leak_datetime_et": "",
        "leak_source_url": "",
        "event_type": "supply_route",
        "route": "red_sea",
        "escalation": "first_attack",
        "surprise_flag": "",
        "confound_note": "",
        "source_url": "https://example.com/attack",
        "notes": "fake row for tests",
        "time_assumed": "",
    }
    return row | changes


def write_supply(tmp_path: Path, rows: list[dict]) -> Path:
    return write_events(tmp_path, rows, SUPPLY_ROUTE_COLUMNS)


def session_date(start: str, offset: int) -> str:
    """The NYSE session `offset` sessions after `start` (itself a session), as YYYY-MM-DD."""
    sessions = nyse_calendar().sessions
    return str(sessions[sessions.get_loc(pd.Timestamp(start)) + offset].date())


# --- Loader -------------------------------------------------------------------


def test_real_supply_route_files_are_header_only():
    events = load_supply_route_events(ROOT / "events" / "supply_route_events.csv")
    assert events.empty
    with (ROOT / "events" / "supply_route_mask_only.csv").open(encoding="utf-8") as f:
        assert f.read().strip() == ",".join(MASK_COLUMNS)


def test_valid_two_row_file_loads(tmp_path):
    second = session_date("2024-06-04", 11)
    rows = [
        supply_row(),
        supply_row(
            event_id="attack_2",
            announcement_datetime_et=f"{second} 17:30",  # after the close: next session
            leak_datetime_et=f"{second} 15:00",  # the leak is before the close
            leak_source_url="https://example.com/leak",
            route="hormuz",
            escalation="named_escalation",
            surprise_flag="1",
            time_assumed="0",
        ),
    ]
    events = load_supply_route_events(write_supply(tmp_path, rows))
    assert list(events.columns[: len(SUPPLY_ROUTE_COLUMNS)]) == list(SUPPLY_ROUTE_COLUMNS)
    for column in ("event_time", "used_leak", "day0"):
        assert column in events.columns
    assert events["day0"].tolist() == [pd.Timestamp("2024-06-04"), pd.Timestamp(second)]
    assert events["used_leak"].tolist() == [False, True]
    assert events["time_assumed"].tolist() == [False, False]
    assert str(events["surprise_flag"].dtype) == "Int64"
    assert events["route"].tolist() == ["red_sea", "hormuz"]
    assert str(events["event_time"].dtype).endswith("America/New_York]")

    # Official time: the second event's day 0 rolls to the next session, still 12 apart.
    official = load_supply_route_events(write_supply(tmp_path, rows), use_leak=False)
    assert official["day0"].iloc[1] == next_session(pd.Timestamp(second))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"time_assumed": "1"}, "time_assumed applies to OPEC only"),
        ({"time_assumed": "x"}, "time_assumed is 'x', must be one of '', '0'"),
        ({"route": "suez"}, "route is 'suez', must be one of"),
        ({"escalation": "retaliation"}, "escalation is 'retaliation', must be one of"),
        ({"event_type": "opec"}, "event_type is 'opec', must be 'supply_route'"),
        ({"source_url": ""}, "source_url is blank"),
        ({"surprise_flag": "2"}, "surprise_flag is '2'"),
        ({"leak_datetime_et": "2024-06-04 09:00"}, "both be filled or both blank"),
    ],
)
def test_bad_rows_are_rejected(tmp_path, changes, message):
    with pytest.raises(ValueError, match=message):
        load_supply_route_events(write_supply(tmp_path, [supply_row(**changes)]))


def test_spacing_of_ten_sessions_names_both_events(tmp_path):
    rows = [
        supply_row(event_id="early"),
        supply_row(event_id="late", announcement_datetime_et=f"{session_date('2024-06-04', 10)} 10:00"),
    ]
    with pytest.raises(ValueError) as err:
        load_supply_route_events(write_supply(tmp_path, rows))
    message = str(err.value)
    assert "1 problem(s)" in message
    assert "(early, late)" in message
    assert "10 trading day(s) apart" in message
    assert "at least 11" in message


def test_spacing_of_eleven_sessions_is_fine(tmp_path):
    rows = [
        supply_row(event_id="early"),
        supply_row(event_id="late", announcement_datetime_et=f"{session_date('2024-06-04', 11)} 10:00"),
    ]
    assert len(load_supply_route_events(write_supply(tmp_path, rows))) == 2


def test_spacing_is_checked_in_day0_order_not_file_order(tmp_path):
    """Rows out of date order are sorted first, so a close pair is found anyway."""
    rows = [
        supply_row(event_id="c", announcement_datetime_et=f"{session_date('2024-06-04', 30)} 10:00"),
        supply_row(event_id="a"),
        supply_row(event_id="b", announcement_datetime_et=f"{session_date('2024-06-04', 3)} 10:00"),
    ]
    with pytest.raises(ValueError, match=r"lines 3 and 4 \(a, b\).*3 trading day"):
        load_supply_route_events(write_supply(tmp_path, rows))


def test_all_errors_are_reported_together(tmp_path):
    rows = [
        supply_row(event_id="a", route="suez"),
        supply_row(event_id="b", announcement_datetime_et=f"{session_date('2024-06-04', 2)} 10:00"),
        supply_row(event_id="c", announcement_datetime_et="2024-07-01 10:00", time_assumed="1"),
        supply_row(event_id="c", announcement_datetime_et="2024-09-03 10:00", source_url=""),
    ]
    with pytest.raises(ValueError) as err:
        load_supply_route_events(write_supply(tmp_path, rows))
    message = str(err.value)
    assert "5 problem(s)" in message
    assert "event_id 'c' is used more than once" in message
    assert "line 2 (a): route is 'suez'" in message
    assert "line 4 (c): time_assumed is '1'" in message
    assert "line 5 (c): source_url is blank" in message
    assert "(a, b)" in message


def test_min_spacing_is_a_parameter(tmp_path):
    rows = [
        supply_row(event_id="a"),
        supply_row(event_id="b", announcement_datetime_et=f"{session_date('2024-06-04', 5)} 10:00"),
    ]
    path = write_supply(tmp_path, rows)
    with pytest.raises(ValueError, match="at least 11"):
        load_supply_route_events(path)
    assert len(load_supply_route_events(path, min_spacing=5)) == 2


# --- Masks ----------------------------------------------------------------------


def test_build_mask_day0s_includes_main_and_shifted_day0s(tmp_path):
    run = load_script("run_supply_route")
    opec_dir, opec_mask_dir, mask_dir = (tmp_path / d for d in ("opec", "opec_mask", "mask"))
    for d in (opec_dir, opec_mask_dir, mask_dir):
        d.mkdir()
    opec = write_events(
        opec_dir,
        [
            valid_row(event_id="firm"),  # 2024-06-04 10:00
            valid_row(event_id="assumed", announcement_datetime_et="2024-09-10 12:00", time_assumed="1"),
        ],
    )
    opec_mask = write_events(
        opec_mask_dir,
        [mask_row(announcement_datetime_et="2024-03-05 12:00", time_assumed="1")],
        MASK_COLUMNS,
    )
    # The same day as the firm OPEC row: kept once.
    attack_mask = write_events(
        mask_dir,
        [mask_row(event_id="attack_mask", announcement_datetime_et="2024-06-04 10:00")],
        MASK_COLUMNS,
    )
    day0s = run.build_mask_day0s(opec, opec_mask, attack_mask)
    assert list(day0s) == [
        pd.Timestamp("2024-03-05"),
        pd.Timestamp("2024-03-06"),  # the OPEC mask row's shifted day 0
        pd.Timestamp("2024-06-04"),
        pd.Timestamp("2024-09-10"),
        pd.Timestamp("2024-09-11"),  # the time_assumed OPEC event's shifted day 0
    ]


def test_mask_day0s_reach_the_attack_estimation_windows():
    """An OPEC mask inside an attack's estimation window is skipped there."""
    run = load_script("run_supply_route")
    security, benchmark = fake_returns(np.random.default_rng(1), n_days=300)
    events = simulated_events(security.index, [200])
    mask = pd.DatetimeIndex([security.index[150]])
    results, _ = run_events(
        events, security, benchmark, 120, 10, WINDOWS, mask, group_columns=run.GROUP_COLUMNS
    )
    assert results.loc[0, "est_masked_days"] == 11
    assert results.loc[0, "nearby_mask_events"] == 0


# --- Runs on simulated returns -----------------------------------------------------


def simulated_events(dates: pd.DatetimeIndex, rows, routes=None, escalations=None) -> pd.DataFrame:
    """An events table like load_supply_route_events returns, day 0 at these rows of dates."""
    n = len(rows)
    return pd.DataFrame(
        {
            "event_id": [f"sim_{i}" for i in range(n)],
            "route": routes or ["red_sea"] * n,
            "escalation": escalations or ["first_attack"] * n,
            "surprise_flag": pd.array([pd.NA] * n, dtype="Int64"),
            "event_time": pd.NaT,
            "used_leak": False,
            "day0": dates[list(rows)],
            "time_assumed": False,
        }
    )


def gld_like(seed: int, n_days: int) -> tuple[pd.Series, pd.Series]:
    """(security, benchmark) where the security ignores the benchmark (beta 0)."""
    _, benchmark = fake_returns(np.random.default_rng(seed), n_days=n_days)
    noise = np.random.default_rng(seed + 100).normal(0.0003, 0.009, n_days)
    return pd.Series(noise, index=benchmark.index), benchmark


def test_near_zero_beta_security_fits(tmp_path):
    run = load_script("run_supply_route")
    security, benchmark = gld_like(4, 400)
    events = simulated_events(security.index, [150, 200, 250])
    results, abnormal = run_events(
        events, security, benchmark, 120, 10, WINDOWS, (), group_columns=run.GROUP_COLUMNS
    )
    assert (results["status"] == "ok").all()
    assert results["beta"].abs().max() < 0.3
    assert list(results.columns[:3]) == ["event_id", "route", "escalation"]
    assert len(abnormal) == 3


def simulated_runs(n_events: int = 7) -> dict[str, pd.DataFrame]:
    """{ticker: results} on simulated returns, the same events for each ticker.

    Routes: 5 red_sea and the rest hormuz (none gulf_facility). Escalations:
    4 first_attack and the rest named_escalation.
    """
    routes = ["red_sea"] * 5 + ["hormuz"] * (n_events - 5)
    escalations = ["first_attack"] * 4 + ["named_escalation"] * (n_events - 4)
    runs = {}
    for seed, ticker in enumerate(("XLE", "ITA", "GLD")):
        if ticker == "GLD":
            security, benchmark = gld_like(seed, 150 + 20 * n_events)
        else:
            security, benchmark = fake_returns(np.random.default_rng(seed), n_days=150 + 20 * n_events)
        events = simulated_events(
            security.index, [140 + 20 * i for i in range(n_events)], routes, escalations
        )
        runs[ticker], _ = run_events(
            events, security, benchmark, 120, 10, WINDOWS, (), group_columns=("route", "escalation")
        )
    return runs


def test_across_table_has_one_primary_and_holm_over_all_rows(capsys):
    run = load_script("run_supply_route")
    runs = simulated_runs()
    table = run.across_event_table(runs)
    assert list(table.columns) == run.ACROSS_COLUMNS
    # 3 securities x 2 windows x 6 groups (all, 3 routes, 2 escalations).
    assert len(table) == 36

    primary = table[table["role"] == "primary"]
    assert len(primary) == 1
    assert primary[["security", "window", "group"]].iloc[0].tolist() == ["XLE", "[+0,+1]", "all"]
    assert set(table["role"]) == {"primary", "secondary"}
    assert (table["expected_sign"] == 1).all()

    # cs_p is the cross-sectional t's two-sided p from aggregate.
    first = table.iloc[0]
    direct = across_event_tests(runs["XLE"], (0, 1))
    assert first["cs_p"] == direct.tests.loc["cross_sectional_t", "p_value"]

    # Holm over the 5 tested secondary "all" rows; blank everywhere else,
    # the primary included (it is read unadjusted).
    family = table["tested"] & (table["group"] == "all") & (table["role"] == "secondary")
    assert family.sum() == 5
    expected = multipletests(table.loc[family, "cs_p"], method="holm")[1]
    assert np.allclose(table.loc[family, "p_holm"], expected)
    assert table.loc[~family, "p_holm"].isna().all()

    # Groups below 5 ok events are not tested.
    by_group = table[(table["security"] == "XLE") & (table["window"] == "[+0,+1]")].set_index("group")
    assert by_group["n_ok"].to_dict() == {
        "all": 7, "gulf_facility": 0, "red_sea": 5, "hormuz": 2,
        "first_attack": 4, "named_escalation": 3,
    }  # fmt: skip
    for group in ("gulf_facility", "hormuz", "first_attack", "named_escalation"):
        assert not by_group.loc[group, "tested"]
        assert by_group.loc[group, "note"] == "too few events (N < 5)"
        assert pd.isna(by_group.loc[group, "cs_p"])
    assert by_group.loc["red_sea", "tested"]

    run.print_across_event(table, runs)
    out = capsys.readouterr().out
    assert "read unadjusted" in out and "secondary" in out
    assert "'all' is descriptive only" not in out
    starred = [line for line in out.splitlines() if line.startswith("  * ")]
    # The primary row in the XLE table, then in the Holm list.
    assert len(starred) == 2
    assert starred[0].split()[1] == "all"
    assert starred[1].split()[1:3] == ["XLE", "[+0,+1]"]


def test_holm_family_shrinks_to_tested_rows():
    """With 4 events nothing is tested, so p_holm is blank everywhere."""
    run = load_script("run_supply_route")
    table = run.across_event_table({t: r.iloc[:4] for t, r in simulated_runs().items()})
    assert not table["tested"].any()
    assert table["p_holm"].isna().all()
    assert (table["role"] == "primary").sum() == 1


# --- Guard and output paths ----------------------------------------------------------


def test_fewer_than_five_events_stops_before_any_price_is_read(tmp_path, monkeypatch):
    run = load_script("run_supply_route")
    rows = [
        supply_row(event_id=f"a{i}", announcement_datetime_et=f"{session_date('2024-06-04', 20 * i)} 10:00")
        for i in range(4)
    ]
    monkeypatch.setattr(run, "EVENTS_PATH", write_supply(tmp_path, rows))

    def must_not_run(*args, **kwargs):
        raise AssertionError("no price may be read with fewer than 5 events")

    monkeypatch.setattr(run, "load_cached", must_not_run)
    monkeypatch.setattr("sys.argv", ["run_supply_route.py"])
    with pytest.raises(SystemExit, match="has 4 event\\(s\\); the run needs at least 5"):
        run.main()


def test_no_refresh_flag(monkeypatch):
    run = load_script("run_supply_route")
    monkeypatch.setattr("sys.argv", ["run_supply_route.py", "--refresh"])
    with pytest.raises(SystemExit):
        run.parse_args()


def test_output_paths_never_collide_with_opec():
    run = load_script("run_supply_route")
    run_opec = load_script("run_opec")
    opec = set()
    for official, shift in itertools.product((False, True), repeat=2):
        opec |= set(run_opec.output_paths(official, shift))
        opec |= set(run_opec.caar_paths(official, shift))
        opec.add(run_opec.across_event_path(official, shift))
    ours = list(run.output_paths().values())
    assert len(ours) == len(set(ours)) == 4 + 2 * len(run.SECURITIES)
    assert set(ours).isdisjoint(opec)
    assert all(p.name.startswith("supply_route_") for p in ours)


# --- The whole script on simulated prices ----------------------------------------------


def test_main_runs_end_to_end_on_simulated_prices(tmp_path, monkeypatch, capsys):
    """main() with fake events, header-only OPEC files and simulated prices."""
    run = load_script("run_supply_route")
    xle, spy = fake_returns(np.random.default_rng(11), n_days=320)
    ita, _ = fake_returns(np.random.default_rng(12), n_days=320)
    gld, _ = gld_like(13, 320)
    # Prices from returns: the first row is the starting price.
    prices = {
        t: 100 * (1 + r).cumprod() for t, r in {"XLE": xle, "ITA": ita, "GLD": gld, "SPY": spy}.items()
    }
    dates = spy.index
    rows = [
        supply_row(event_id=f"a{i}", announcement_datetime_et=f"{dates[150 + 20 * i].date()} 10:00")
        for i in range(6)
    ]
    inputs = tmp_path / "inputs"
    for name in ("events", "opec", "opec_mask", "mask"):
        (inputs / name).mkdir(parents=True)
    monkeypatch.setattr(run, "EVENTS_PATH", write_supply(inputs / "events", rows))
    monkeypatch.setattr(run, "OPEC_EVENTS_PATH", write_events(inputs / "opec", []))
    monkeypatch.setattr(run, "OPEC_MASK_PATH", write_events(inputs / "opec_mask", [], MASK_COLUMNS))
    monkeypatch.setattr(run, "MASK_PATH", write_events(inputs / "mask", [], MASK_COLUMNS))
    monkeypatch.setattr(run, "load_cached", lambda ticker: prices[ticker])
    monkeypatch.setattr(reporting, "ticker_info", lambda ticker, series: {
        "first_date": "x", "last_date": "x", "rows": len(series),
        "dates_sha256": "0" * 64, "adj_close_sha256": "0" * 64,
    })  # fmt: skip
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["run_supply_route.py"])
    run.main()

    for path in run.output_paths().values():
        assert path.exists(), path
    results = pd.read_csv(run.output_paths()["results"])
    assert results.columns[0] == "security"
    assert results.groupby("security").size().to_dict() == {"GLD": 6, "ITA": 6, "XLE": 6}
    assert (results["status"] == "ok").all()
    abnormal = pd.read_csv(run.output_paths()["abnormal"])
    assert list(abnormal.columns[:2]) == ["event_id", "security"]
    assert len(abnormal) == 18
    across = pd.read_csv(run.output_paths()["across_event"])
    assert (across["role"] == "primary").sum() == 1
    out = capsys.readouterr().out
    assert "6 supply-route event(s); 0 mask day 0(s)" in out


def test_dates_only_works_with_few_events(tmp_path, monkeypatch, capsys):
    run = load_script("run_supply_route")
    sessions = nyse_calendar().sessions_in_range("2023-01-03", "2025-12-31")
    # All NaN prices: dates-only must use the dates alone.
    prices = {t: pd.Series(float("nan"), index=sessions) for t in ("XLE", "ITA", "GLD", "SPY")}
    rows = [supply_row(event_id="a", announcement_datetime_et=f"{sessions[300].date()} 10:00")]
    inputs = tmp_path / "inputs"
    for name in ("events", "opec", "opec_mask", "mask"):
        (inputs / name).mkdir(parents=True)
    monkeypatch.setattr(run, "EVENTS_PATH", write_supply(inputs / "events", rows))
    monkeypatch.setattr(
        run, "OPEC_EVENTS_PATH",
        write_events(inputs / "opec", [valid_row(announcement_datetime_et=f"{sessions[200].date()} 10:00")]),
    )  # fmt: skip
    monkeypatch.setattr(run, "OPEC_MASK_PATH", write_events(inputs / "opec_mask", [], MASK_COLUMNS))
    monkeypatch.setattr(run, "MASK_PATH", write_events(inputs / "mask", [], MASK_COLUMNS))
    monkeypatch.setattr(run, "load_cached", lambda ticker: prices[ticker])

    def must_not_run(*args, **kwargs):
        raise AssertionError("dates-only must not compute returns or run the model")

    monkeypatch.setattr(run, "simple_returns", must_not_run)
    monkeypatch.setattr(run, "run_events", must_not_run)
    monkeypatch.setattr("sys.argv", ["run_supply_route.py", "--dates-only"])
    run.main()
    out = capsys.readouterr().out
    assert "no returns, regressions or CARs computed" in out
    line = next(line.split() for line in out.splitlines() if line.startswith("a "))
    # The OPEC event at session 200 is inside the estimation window: 11 days skipped.
    assert line[1] == str(sessions[300].date())
    assert line[4:] == ["11", "131", "0", "0"]
