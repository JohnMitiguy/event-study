"""Run the supply-route attack study: XLE, ITA and GLD, each vs SPY.

Run from the project root:

    uv run python scripts/run_supply_route.py               # the full run
    uv run python scripts/run_supply_route.py --dates-only  # where each window falls; no returns

There is NO --refresh flag. The price cache has one file per ticker, shared
with scripts/run_opec.py, so refreshing XLE or SPY here would replace the
snapshot the OPEC+ results came from and change them. Prices are read only
through prices.load_cached: a ticker with no cache file yet (ITA and GLD
before their first use) is downloaded once, and every cached file is used
as it is.

Steps:
1. Load events/supply_route_events.csv (events.load_supply_route_events:
   leak time used where present, attacks at least 11 sessions apart).
   Unless --dates-only, STOP if it has fewer than aggregate.MIN_EVENTS rows,
   before any price is read, so no result can be seen early.
2. Build the mask day 0s (build_mask_day0s): every OPEC+ event, the OPEC+
   mask-only list and the supply-route mask-only list, with both the main
   and the shifted day 0 of time_assumed rows (DECISIONS.md). Their [-5,+5]
   days are skipped in every attack's estimation window; they are never
   tested.
3. Load SPY and each security from the cache, turn them into simple daily
   returns and trim each security and SPY to the dates they share. STOP if
   an event's widest window ends after the cached data ends.
4. Run the market model for every event on each security (runner.run_events,
   group columns route and escalation) and print a summary per security.
5. Save results/supply_route_results.csv and results/supply_route_abnormal.csv
   (long format: one `security` column, all securities in one file),
   results/supply_route_run_info.json and, per security with any "ok" event,
   charts/supply_route_events_{ticker}.png and charts/supply_route_caar_{ticker}.png.
6. Across-event tests per security, window and group ("all", each route,
   each escalation), saved to results/supply_route_across_event.csv. A group
   with fewer than 5 "ok" events is not tested. The one primary test
   (PRIMARY, DECISIONS.md) has role "primary" and is read unadjusted; every
   other row is "secondary". p_holm is the Holm-adjusted cs_p over the tested
   secondary "all" rows (the other five of 3 securities x 2 windows); the
   primary has no p_holm.

With --dates-only the script prints, per event, day 0, the estimation window
(est_start, est_end, skipped days, span) and nearby_events and
nearby_mask_events, then stops. No returns, regressions or CARs are computed,
and nothing is saved. It works with any number of events.

Assumptions:
- Every security has data on the same sessions as SPY over the events'
  windows, so --dates-only uses the dates all four tickers share. A real run
  trims each security with SPY separately (reporting.common_dates).
- OPEC+ events are masked at their main (leak-time) day 0 and the shifted
  day 0 of time_assumed rows, not at their official-time day 0.
"""

import argparse
import json
from pathlib import Path

import pandas as pd
import yfinance
from statsmodels.stats.multitest import multipletests

from event_study import reporting
from event_study.aggregate import MIN_EVENTS
from event_study.events import (
    ESCALATIONS,
    ROUTES,
    SUPPLY_ROUTE_MIN_SPACING,
    load_events,
    load_mask_events,
    load_supply_route_events,
)
from event_study.prices import load_cached, simple_returns
from event_study.runner import estimation_dates, events_needing_later_data, run_events
from event_study.windows import DEFAULT_EST_LENGTH, DEFAULT_GAP, window_label

SECURITIES = ("XLE", "ITA", "GLD")
BENCHMARK = "SPY"
EVENT_WINDOWS = ((0, 1), (-5, 5))
EST_LENGTH = DEFAULT_EST_LENGTH
GAP = DEFAULT_GAP
GROUP_COLUMNS = ("route", "escalation")

# Pre-stated expected sign of each security's reaction (DECISIONS.md). It
# only labels results; every test stays two-sided.
EXPECTED_SIGN = {"XLE": 1, "ITA": 1, "GLD": 1}
# The one primary test (DECISIONS.md): the cross-sectional t of this
# security, window and group. Every other row is secondary.
PRIMARY = ("XLE", (0, 1), "all")

EVENTS_PATH = Path("events") / "supply_route_events.csv"
MASK_PATH = Path("events") / "supply_route_mask_only.csv"
OPEC_EVENTS_PATH = Path("events") / "opec_events.csv"
OPEC_MASK_PATH = Path("events") / "opec_mask_only.csv"

# The average-CAR chart has one line, all attacks pooled. Its key is the
# line's label: draw_caar_chart writes it as "Attacks (N = ...)".
CAAR_GROUP = "attack"
CAAR_COLORS = {CAAR_GROUP: "#2a78d6"}

ACROSS_COLUMNS = [
    "security", "window", "group", "n_ok", "tested", "role", "expected_sign", "mean_car",
    "cross_sectional_t", "cs_p", "bmp_t", "wilcoxon_p", "sign_p", "p_holm", "note",
]  # fmt: skip
LEGEND = (
    f"* = primary result ({PRIMARY[0]}, {window_label(PRIMARY[1])}, cross-sectional t, "
    f"group '{PRIMARY[2]}'), fixed before the first run and read unadjusted; "
    "every other row is secondary."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the supply-route attack study (XLE, ITA, GLD vs SPY). "
        "There is no --refresh: see the module docstring."
    )
    parser.add_argument(
        "--dates-only",
        action="store_true",
        help="print each event's day 0, estimation window and nearby events, "
        "then stop: no returns, regressions or CARs, nothing saved",
    )
    return parser.parse_args()


def output_paths() -> dict[str, Path]:
    """Every file this script writes, by name.

    "results", "across_event", "abnormal", "run_info", then
    "events_{ticker}" and "caar_{ticker}" (charts) for each security. All
    start with "supply_route_", so none can overwrite an OPEC+ output.
    """
    paths = {
        "results": Path("results") / "supply_route_results.csv",
        "across_event": Path("results") / "supply_route_across_event.csv",
        "abnormal": Path("results") / "supply_route_abnormal.csv",
        "run_info": Path("results") / "supply_route_run_info.json",
    }
    for ticker in SECURITIES:
        paths[f"events_{ticker}"] = Path("charts") / f"supply_route_events_{ticker}.png"
        paths[f"caar_{ticker}"] = Path("charts") / f"supply_route_caar_{ticker}.png"
    return paths


def check_enough_events(events: pd.DataFrame) -> None:
    """Stop unless the events file has at least MIN_EVENTS rows.

    Called before any price is read, so no attack result can be seen before
    the list is complete enough to test.
    """
    if len(events) < MIN_EVENTS:
        raise SystemExit(
            f"{EVENTS_PATH} has {len(events)} event(s); the run needs at least {MIN_EVENTS}. "
            "Nothing was read or run. Use --dates-only to check the dates meanwhile."
        )


def _main_and_shifted(main: pd.DataFrame, shifted: pd.DataFrame) -> pd.Series:
    """Every row's day 0 from main, plus the shifted day 0 of its time_assumed rows.

    main and shifted are the same file loaded with shift_assumed False and
    True. .loc[mask, "day0"] keeps only the rows where mask is True.
    """
    return pd.concat([main["day0"], shifted.loc[shifted["time_assumed"], "day0"]])


def build_mask_day0s(
    opec_events_path: Path = OPEC_EVENTS_PATH,
    opec_mask_path: Path = OPEC_MASK_PATH,
    mask_path: Path = MASK_PATH,
) -> pd.DatetimeIndex:
    """Day 0s whose [-5,+5] days the attack estimation windows skip, sorted, each once.

    The union of: the OPEC+ events (load_events, leak time where present),
    the OPEC+ mask-only list and the supply-route mask-only list. For every
    time_assumed row both the main and the shifted day 0 are in
    (DECISIONS.md), since either could be the reaction day. A day 0 in more
    than one list is kept once.

    Note: runner's nearby_mask_events counts these day 0s, so a time_assumed
    row next to an attack counts twice (main and shifted).
    """
    parts = [
        _main_and_shifted(
            load_events(opec_events_path), load_events(opec_events_path, shift_assumed=True)
        ),
        _main_and_shifted(
            load_mask_events(opec_mask_path), load_mask_events(opec_mask_path, shift_assumed=True)
        ),
        _main_and_shifted(
            load_mask_events(mask_path), load_mask_events(mask_path, shift_assumed=True)
        ),
    ]
    day0s = pd.concat(parts, ignore_index=True)
    return pd.DatetimeIndex(day0s.drop_duplicates().sort_values())


def load_all_prices() -> dict[str, pd.Series]:
    """Adjusted closes of every security and the benchmark, from the cache only."""
    return {ticker: load_cached(ticker) for ticker in (*SECURITIES, BENCHMARK)}


def returns_by_security(prices: dict[str, pd.Series]) -> dict[str, tuple[pd.Series, pd.Series]]:
    """{ticker: (security returns, SPY returns)}, each pair trimmed to shared dates."""
    benchmark = simple_returns(prices[BENCHMARK])
    return {
        ticker: reporting.common_dates(
            simple_returns(prices[ticker]), benchmark, (ticker, BENCHMARK)
        )
        for ticker in SECURITIES
    }


def stop_if_data_too_short(events: pd.DataFrame, returns: dict) -> None:
    """Stop if any event's widest window ends after a security's data ends.

    Like reporting.stop_if_data_too_short, but without a --refresh command
    to suggest (this script has none; see the module docstring).
    """
    for ticker, (security, _) in returns.items():
        last_date = security.index[-1]
        needing = events_needing_later_data(events, last_date, EVENT_WINDOWS)
        if needing:
            raise SystemExit(
                f"{len(needing)} event(s) need {ticker} prices after the cached data ends "
                f"({last_date.date()}): {', '.join(needing)}\n"
                "This script cannot refresh prices: refreshing the shared XLE or SPY "
                "cache would change the OPEC+ results."
            )


def run_all(events: pd.DataFrame, returns: dict, mask_day0s) -> dict:
    """{ticker: (results, abnormal)} from runner.run_events, one run per security.

    Every run uses the same events, masks and settings; only the security
    changes.
    """
    runs = {}
    for ticker, (security, benchmark) in returns.items():
        runs[ticker] = run_events(
            events,
            security,
            benchmark,
            EST_LENGTH,
            GAP,
            EVENT_WINDOWS,
            mask_day0s,
            group_columns=GROUP_COLUMNS,
        )
    return runs


def long_format(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Stack {ticker: table} into one table with a `security` column first.

    The tables keep their index (event_id for the abnormal returns).
    .assign adds the column without changing the original table.
    """
    stacked = pd.concat([t.assign(security=ticker) for ticker, t in tables.items()])
    return stacked[["security", *stacked.columns.drop("security")]]


def security_groups(results: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """{group name: rows of results}: "all", each route, then each escalation.

    Filters of the finished results, never of the events table
    (DECISIONS.md: dropping an event beforehand would change its
    neighbours' estimation windows).
    """
    return (
        {"all": results}
        | {route: results[results["route"] == route] for route in ROUTES}
        | {esc: results[results["escalation"] == esc] for esc in ESCALATIONS}
    )


def holm_p(table: pd.DataFrame) -> pd.Series:
    """Holm-adjusted cs_p for the tested secondary "all" rows, NaN elsewhere.

    The family is the other five "all" rows of 3 securities x 2 windows
    (DECISIONS.md): the primary is named in advance and read unadjusted, so
    it is left out, and so is an "all" row that was not tested.
    """
    family = table["tested"] & (table["group"] == "all") & (table["role"] == "secondary")
    adjusted = pd.Series(float("nan"), index=table.index)
    if family.any():
        # multipletests returns (reject, adjusted p-values, ...); [1] is the p-values.
        adjusted[family] = multipletests(table.loc[family, "cs_p"], method="holm")[1]
    return adjusted


def across_event_table(
    results_by_security: dict[str, pd.DataFrame], windows=EVENT_WINDOWS
) -> pd.DataFrame:
    """One row per security, window and group, with columns ACROSS_COLUMNS.

    results_by_security: {ticker: its results table}. Numbers come from
    reporting.across_event_table (N counts "ok" rows only, fewer than
    MIN_EVENTS is "too few events"). role is "primary" for PRIMARY only.
    """
    primary_ticker, primary_window, primary_group = PRIMARY
    parts = []
    for ticker, results in results_by_security.items():
        primary_groups = (primary_group,) if ticker == primary_ticker else ()
        table = reporting.across_event_table(
            security_groups(results), windows, primary_window, primary_groups, include_cs_p=True
        )
        table["role"] = table["headline"].map({True: "primary", False: "secondary"})
        parts.append(table.assign(security=ticker, expected_sign=EXPECTED_SIGN[ticker]))
    table = pd.concat(parts, ignore_index=True)
    table["p_holm"] = holm_p(table)
    return table[ACROSS_COLUMNS]


def print_across_event(table: pd.DataFrame, results_by_security: dict[str, pd.DataFrame]) -> None:
    """Per security: reporting.print_across_event with the primary marked "*",
    then the cross-sectional p-values of the "all" rows with Holm.
    """
    for ticker, results in results_by_security.items():
        print(f"\n=== {ticker} vs {BENCHMARK} (expected sign {EXPECTED_SIGN[ticker]:+d}) ===")
        part = table[table["security"] == ticker]
        # reporting marks rows whose headline is True.
        marked = part.assign(headline=part["role"] == "primary")
        reporting.print_across_event(marked, results, "route", LEGEND)
    print_holm(table)


def print_holm(table: pd.DataFrame) -> None:
    """The cross-sectional p-values of the "all" rows, unadjusted and Holm-adjusted."""
    print(
        "\nCross-sectional t, group 'all' (two-sided). The primary (*) is read from "
        "cs p, unadjusted, and has no Holm p; the rest are secondary, with Holm p over "
        "the tested secondary rows."
    )
    print(f"    {'security':<8} {'window':<8} {'cs p':>7} {'Holm p':>7}")
    for _, row in table[table["group"] == "all"].iterrows():
        mark = "*" if row["role"] == "primary" else " "
        line = f"  {mark} {row['security']:<8} {row['window']:<8} "
        if row["tested"]:
            holm = "-" if pd.isna(row["p_holm"]) else f"{row['p_holm']:.3f}"
            line += f"{row['cs_p']:>7.3f} {holm:>7}"
        else:
            line += row["note"]
        print(line)


def build_run_info(prices: dict, returns: dict, git: tuple, mask_day0s) -> dict:
    """Everything needed to tell whether two runs used the same inputs."""
    commit, dirty = git
    return {
        "tickers": {
            ticker: reporting.ticker_info(ticker, series) for ticker, series in prices.items()
        },
        "returns_used": {
            ticker: {
                "first_date": str(security.index[0].date()),
                "last_date": str(security.index[-1].date()),
                "rows": len(security),
            }
            for ticker, (security, _) in returns.items()
        },
        "securities": list(SECURITIES),
        "benchmark": BENCHMARK,
        "expected_sign": EXPECTED_SIGN,
        "primary": {
            "security": PRIMARY[0],
            "window": list(PRIMARY[1]),
            "group": PRIMARY[2],
            "test": "cross_sectional_t",
        },
        "group_columns": list(GROUP_COLUMNS),
        "est_length": EST_LENGTH,
        "gap": GAP,
        "event_windows": [list(w) for w in EVENT_WINDOWS],
        "use_leak": True,
        "min_spacing": SUPPLY_ROUTE_MIN_SPACING,
        "mask_day0_count": len(mask_day0s),
        "events_file": EVENTS_PATH.as_posix(),
        "events_file_sha256": reporting.file_sha256(EVENTS_PATH),
        "mask_file": MASK_PATH.as_posix(),
        "mask_file_sha256": reporting.file_sha256(MASK_PATH),
        "opec_events_file": OPEC_EVENTS_PATH.as_posix(),
        "opec_events_file_sha256": reporting.file_sha256(OPEC_EVENTS_PATH),
        "opec_mask_file": OPEC_MASK_PATH.as_posix(),
        "opec_mask_file_sha256": reporting.file_sha256(OPEC_MASK_PATH),
        "yfinance_version": yfinance.__version__,
        "pandas_version": pd.__version__,
        "git_commit": commit,
        "git_dirty": dirty,
    }


def print_run_info(info: dict) -> None:
    """The key run-info items, with hashes shortened to 12 characters."""
    print("\nData and code for this run:")
    for ticker, t in info["tickers"].items():
        print(
            f"  {ticker}: {t['first_date']} to {t['last_date']}, {t['rows']} rows, "
            f"dates {t['dates_sha256'][:12]}, adj close {t['adj_close_sha256'][:12]}"
        )
    print(
        f"  events file sha256 {info['events_file_sha256'][:12]}, "
        f"mask file sha256 {info['mask_file_sha256'][:12]}, "
        f"OPEC+ events {info['opec_events_file_sha256'][:12]}, "
        f"OPEC+ masks {info['opec_mask_file_sha256'][:12]}"
    )
    commit = info["git_commit"][:12] if info["git_commit"] else "unavailable"
    print(f"  git commit {commit}, uncommitted changes: {info['git_dirty']}")


def dates_only(prices: dict[str, pd.Series], events: pd.DataFrame, mask_day0s) -> None:
    """--dates-only: print where each event's windows fall, from dates alone.

    Zeros stand in for returns (simple_returns would drop the first price
    row, so the dates are prices.index[1:]). The dates are the ones every
    ticker shares: SPY is trimmed against each security in turn.
    """
    placeholders = {t: pd.Series(0.0, index=p.index[1:]) for t, p in prices.items()}
    shared = placeholders[BENCHMARK]
    for ticker in SECURITIES:
        _, shared = reporting.common_dates(placeholders[ticker], shared, (ticker, BENCHMARK))
    table = estimation_dates(
        shared.index,
        events,
        EST_LENGTH,
        GAP,
        EVENT_WINDOWS,
        mask_day0s,
        group_columns=GROUP_COLUMNS,
    )
    reporting.print_dates_only(table)


def save_charts(runs: dict, returns: dict, paths: dict[str, Path]) -> None:
    """Per security with any "ok" event: the per-event chart and the average-CAR chart."""
    for ticker, (results, abnormal) in runs.items():
        if not (results["status"] == "ok").any():
            print(f"No {ticker} events ran, so no {ticker} charts.")
            continue
        data_end = returns[ticker][0].index[-1]
        reporting.draw_chart(
            results,
            abnormal,
            data_end,
            paths[f"events_{ticker}"],
            paths["results"],
            security=ticker,
            benchmark=BENCHMARK,
            est_length=EST_LENGTH,
            gap=GAP,
            event_windows=EVENT_WINDOWS,
        )
        reporting.draw_caar_chart(
            {CAAR_GROUP: results},
            abnormal,
            data_end,
            paths[f"caar_{ticker}"],
            colors=CAAR_COLORS,
            security=ticker,
            benchmark=BENCHMARK,
            title=f"{ticker} average cumulative abnormal return around supply-route attacks",
            xlabel="Trading days from the attack (day 0)",
            est_length=EST_LENGTH,
            gap=GAP,
        )


def main() -> None:
    args = parse_args()
    paths = output_paths()
    # Read git first, before this run writes anything.
    git = reporting.git_state()

    # 1-2. Events (stop if too few, before any price is read) and masks.
    events = load_supply_route_events(EVENTS_PATH)
    if not args.dates_only:
        check_enough_events(events)
    # Paths passed explicitly: default arguments are fixed when the function
    # is defined, so they would not follow a changed module constant.
    mask_day0s = build_mask_day0s(OPEC_EVENTS_PATH, OPEC_MASK_PATH, MASK_PATH)
    print(
        f"{len(events)} supply-route event(s); {len(mask_day0s)} mask day 0(s) skipped in "
        "estimation windows (OPEC+ events and both mask-only lists, never tested)."
    )

    # 3. Prices from the cache only, then returns.
    prices = load_all_prices()
    if args.dates_only:
        dates_only(prices, events, mask_day0s)
        return
    returns = returns_by_security(prices)
    stop_if_data_too_short(events, returns)

    # 4. The market model, once per security.
    runs = run_all(events, returns, mask_day0s)
    for ticker, (results, _) in runs.items():
        print(f"\n=== {ticker} vs {BENCHMARK} ===")
        reporting.print_summary(results, EVENT_WINDOWS)

    # 5. Save.
    paths["results"].parent.mkdir(parents=True, exist_ok=True)
    results_by_security = {ticker: results for ticker, (results, _) in runs.items()}
    long_format(results_by_security).to_csv(paths["results"], index=False)
    print(f"Saved {paths['results']}")
    long_format({ticker: abnormal for ticker, (_, abnormal) in runs.items()}).to_csv(
        paths["abnormal"]
    )
    print(f"Saved {paths['abnormal']}")
    info = build_run_info(prices, returns, git, mask_day0s)
    paths["run_info"].write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print_run_info(info)
    print(f"Saved {paths['run_info']}")

    # 6. Across-event tests, filtered from the results above.
    across = across_event_table(results_by_security)
    print_across_event(across, results_by_security)
    across.to_csv(paths["across_event"], index=False)
    print(f"Saved {paths['across_event']}")

    save_charts(runs, returns, paths)


if __name__ == "__main__":
    main()
