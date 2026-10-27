"""Run the OPEC+ event study: XLE (security) vs SPY (benchmark).

Run from the project root:

    uv run python scripts/run_opec.py            # use the cached prices as they are
    uv run python scripts/run_opec.py --refresh  # re-download prices first
    uv run python scripts/run_opec.py --official-time  # robustness check: ignore leak times
    uv run python scripts/run_opec.py --dates-only  # where each window falls; no returns
    uv run python scripts/run_opec.py --shift-assumed  # time_assumed rows: day 0 one day later

Steps:
1. Load XLE and SPY adjusted closes from the cache in data/prices/. Nothing
   is downloaded unless a cache file is missing or --refresh is passed, so
   re-running gives the same numbers. Turn them into simple daily returns.
2. Line the two return series up date for date. run_events checks both
   against the NYSE trading calendar and STOPS with a ValueError on a
   failure: windows count rows, so a missing day would shift every window
   without any error.
3. Load events/opec_events.csv (leak time used where present) and the mask
   day 0s (load_mask_day0s): real news that is not tested here, whose
   [-5,+5] days are skipped in the estimation windows, nothing more. They
   are events/opec_mask_only.csv, plus (from v1.1, DECISIONS.md) every
   counted supply-route attack in events/supply_route_events.csv and every
   row of events/supply_route_mask_only.csv, with the next session too for
   its time_assumed rows. The attack day 0s are the same in every run: the
   --official-time and --shift-assumed flags only move OPEC+ rows. The one
   combined set goes to run_events, to estimation_days (no_outliers sample)
   and, with --dates-only, to estimation_dates. If any event's widest
   window ends after the cached data ends, STOP and ask for --refresh rather
   than recording those events as failed.
4. Run the market model for every event and print a summary, including each
   failed event and why.
5. Save results/opec_results.csv, results/opec_run_info.json (which data,
   settings, events and mask files, including the supply-route files, and
   code produced the results),
   results/opec_abnormal.csv (each event's abnormal return on days -5 to +5)
   and, if any event ran, charts/opec_events.png (one small panel per event)
   and charts/opec_caar.png (average cumulative abnormal return by event
   day for the headline groups).
6. Across-event tests (aggregate.across_event_tests) for each event window,
   on all "ok" group decisions and separately for cut, increase and hold,
   with saudi_unilateral rows kept out of those groups and tested as their
   own group (DECISIONS.md). Printed and saved to
   results/opec_across_event.csv; the headline rows (HEADLINE_WINDOW and
   HEADLINE_GROUPS) have headline True. A group with fewer than 5 "ok"
   events is not tested and shows "too few events". Every event that is not
   "ok" is listed with its reason. This is done for two samples (the
   `sample` column): "all" events, and "firm_only", which leaves out the
   time_assumed rows (filtered from the same results, never cut from the
   events table). The time_assumed rows left out are listed too. A third
   sample, "no_outliers", leaves out every event whose fitted estimation
   days include one of the OUTLIER_DAYS largest absolute residual days
   (DECISIONS.md: the outlier-exclusion robustness run).

With --dates-only the script prints, per event, day 0, the estimation window
(est_start, est_end, skipped days, span in trading days) and nearby_events,
then stops. No returns, regressions or CARs are computed, and nothing is
saved. It uses the same events, skipping rule and calendar check as a real run,
so it can be run before reading any CAR (DECISIONS.md: the look-back limit
is chosen from event dates).

With --official-time, events use the official announcement time even where
a leak time exists, and every output name gets "_official_time" added (see
output_paths), so this run can never overwrite the main results.

With --shift-assumed, day 0 of every time_assumed row moves one trading day
later (the third report in DECISIONS.md); outputs get "_day0_shifted". It is a
complete run of its own, so its skipped estimation days come from its own day 0s
(OPEC+ events and OPEC+ mask rows; the attack day 0s do not move).

Printing, run-info and chart helpers that are not OPEC-specific live in
event_study.reporting; this script passes them its tickers, groups,
headline and colors.
"""

import argparse
import json
from pathlib import Path

import pandas as pd
import yfinance

from event_study import reporting
from event_study.events import (
    DIRECTIONS,
    load_events,
    load_mask_events,
    load_supply_route_events,
    main_and_shifted_day0s,
)
from event_study.prices import load_cached, simple_returns
from event_study.runner import estimation_dates, estimation_days, run_events
from event_study.windows import DEFAULT_EST_LENGTH, DEFAULT_EVENT_WINDOWS, DEFAULT_GAP

SECURITY = "XLE"
BENCHMARK = "SPY"
EVENTS_PATH = Path("events") / "opec_events.csv"
MASK_PATH = Path("events") / "opec_mask_only.csv"
# Supply-route attacks (from v1.1): their days are skipped in the OPEC+
# estimation windows, nothing more; they are never run or tested here.
SUPPLY_ROUTE_EVENTS_PATH = Path("events") / "supply_route_events.csv"
SUPPLY_ROUTE_MASK_PATH = Path("events") / "supply_route_mask_only.csv"

# The headline result, fixed before the first full run (DECISIONS.md): the
# cross-sectional t on [-1,+1], for cuts and increases separately. They
# predict opposite signs, so the pooled "all" row is descriptive only.
HEADLINE_WINDOW = (-1, 1)
HEADLINE_GROUPS = ("cut", "increase")
SAUDI = "saudi_unilateral"

# One color per headline group (categorical slots 1 and 2, as in plot_prices.py).
GROUP_COLORS = {"cut": "#2a78d6", "increase": "#eb6834"}
REFRESH_COMMAND = "uv run python scripts/run_opec.py --refresh"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the OPEC+ event study (XLE vs SPY).")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="re-download XLE and SPY prices before running (otherwise the cache is used as is)",
    )
    parser.add_argument(
        "--official-time",
        action="store_true",
        help="robustness check: use official announcement times, not leak times, "
        "and write to separate *_official_time output files",
    )
    parser.add_argument(
        "--dates-only",
        action="store_true",
        help="print each event's day 0, estimation window and nearby_events, "
        "then stop: no returns, regressions or CARs, nothing saved",
    )
    parser.add_argument(
        "--shift-assumed",
        action="store_true",
        help="robustness check: move day 0 of time_assumed rows one trading day later "
        "and write to separate *_day0_shifted output files",
    )
    return parser.parse_args()


def run_suffix(official_time: bool, shift_assumed: bool) -> str:
    """Added to every output name so a robustness run never overwrites the main one."""
    return ("_official_time" if official_time else "") + ("_day0_shifted" if shift_assumed else "")


def output_paths(official_time: bool, shift_assumed: bool = False) -> tuple[Path, Path, Path]:
    """(results CSV, run info JSON, chart PNG) for this run.

    Main results use the leak time where present (DECISIONS.md). The
    official-time robustness run adds "_official_time" to every file name,
    so it can never overwrite the main outputs.
    """
    suffix = run_suffix(official_time, shift_assumed)
    return (
        Path("results") / f"opec_results{suffix}.csv",
        Path("results") / f"opec_run_info{suffix}.json",
        Path("charts") / f"opec_events{suffix}.png",
    )


def caar_paths(official_time: bool, shift_assumed: bool = False) -> tuple[Path, Path]:
    """(abnormal returns CSV, average-CAR chart PNG); the run suffix keeps runs apart."""
    suffix = run_suffix(official_time, shift_assumed)
    return (
        Path("results") / f"opec_abnormal{suffix}.csv",
        Path("charts") / f"opec_caar{suffix}.png",
    )


def across_event_path(official_time: bool, shift_assumed: bool = False) -> Path:
    """Where the across-event table goes; the run suffix keeps runs apart."""
    suffix = run_suffix(official_time, shift_assumed)
    return Path("results") / f"opec_across_event{suffix}.csv"


def build_run_info(
    prices: dict[str, pd.Series],
    returns_used: pd.Series,
    git: tuple,
    use_leak: bool,
    shift_assumed: bool = False,
    *,
    attack_mask_day0_count: int,
) -> dict:
    """Everything needed to tell whether two runs used the same inputs.

    attack_mask_day0_count: how many distinct supply-route day 0s the
    estimation windows skipped (load_attack_masks). The supply-route files
    and their hashes are recorded because they set those skipped days.
    """
    commit, dirty = git
    return {
        "tickers": {
            ticker: reporting.ticker_info(ticker, series) for ticker, series in prices.items()
        },
        "returns_used": {
            "first_date": str(returns_used.index[0].date()),
            "last_date": str(returns_used.index[-1].date()),
            "rows": len(returns_used),
        },
        "est_length": DEFAULT_EST_LENGTH,
        "gap": DEFAULT_GAP,
        "event_windows": [list(w) for w in DEFAULT_EVENT_WINDOWS],
        "use_leak": use_leak,
        "shift_assumed": shift_assumed,
        "events_file": EVENTS_PATH.as_posix(),
        "events_file_sha256": reporting.file_sha256(EVENTS_PATH),
        "mask_file": MASK_PATH.as_posix(),
        "mask_file_sha256": reporting.file_sha256(MASK_PATH),
        "supply_route_events_file": SUPPLY_ROUTE_EVENTS_PATH.as_posix(),
        "supply_route_events_file_sha256": reporting.file_sha256(SUPPLY_ROUTE_EVENTS_PATH),
        "supply_route_mask_file": SUPPLY_ROUTE_MASK_PATH.as_posix(),
        "supply_route_mask_file_sha256": reporting.file_sha256(SUPPLY_ROUTE_MASK_PATH),
        "attack_mask_day0_count": attack_mask_day0_count,
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
            f"cache written {t['cache_modified']}, "
            f"dates {t['dates_sha256'][:12]}, adj close {t['adj_close_sha256'][:12]}"
        )
    used = info["returns_used"]
    print(f"  returns used: {used['first_date']} to {used['last_date']}, {used['rows']} rows")
    print(
        f"  events file sha256 {info['events_file_sha256'][:12]}, "
        f"mask file sha256 {info['mask_file_sha256'][:12]}, use_leak {info['use_leak']}, "
        f"shift_assumed {info['shift_assumed']}"
    )
    print(
        f"  supply-route events sha256 {info['supply_route_events_file_sha256'][:12]}, "
        f"supply-route masks sha256 {info['supply_route_mask_file_sha256'][:12]}, "
        f"attack mask day 0s {info['attack_mask_day0_count']}"
    )
    commit = info["git_commit"][:12] if info["git_commit"] else "unavailable"
    print(f"  git commit {commit}, uncommitted changes: {info['git_dirty']}")


def opec_groups(results: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """{group name: rows of results} for the across-event tests.

    "all" and then each direction (cut, increase, hold), all without
    saudi_unilateral rows, and then saudi_unilateral on its own
    (DECISIONS.md: a separate subsample, never averaged into the main
    result). Each group is a filter on the finished results table, never on
    the events table (DECISIONS.md: dropping an event beforehand would
    change its neighbours' estimation windows).
    """
    saudi = results["decision_group"] == SAUDI
    group_rows = results[~saudi]
    return (
        {"all": group_rows}
        | {d: group_rows[group_rows["direction"] == d] for d in DIRECTIONS}
        | {SAUDI: results[saudi]}
    )


def across_event_table(results: pd.DataFrame, windows) -> pd.DataFrame:
    """reporting.across_event_table with the OPEC+ groups (opec_groups) and
    headline (HEADLINE_WINDOW and HEADLINE_GROUPS).

    One row per window and group: N ok, mean CAR and the four tests. A group
    with fewer than aggregate.MIN_EVENTS "ok" rows is not tested and shows
    "too few events".
    """
    return reporting.across_event_table(
        opec_groups(results), windows, HEADLINE_WINDOW, HEADLINE_GROUPS
    )


FIRM_ONLY = "firm_only"
NO_OUTLIERS = "no_outliers"
OUTLIER_DAYS = 5


def firm_only(results: pd.DataFrame) -> pd.DataFrame:
    """The results without time_assumed rows (a filter, not a rerun)."""
    return results[~results["time_assumed"]]


def time_assumed_excluded(results: pd.DataFrame) -> pd.DataFrame:
    """The time_assumed rows the firm_only sample leaves out, as event_id, status, reason."""
    rows = results.loc[results["time_assumed"], ["event_id", "status"]]
    return rows.assign(reason="time_assumed: announcement time not sourced").reset_index(drop=True)


def largest_residual_days(security: pd.Series, benchmark: pd.Series, k: int) -> pd.Series:
    """The k days with the largest absolute residual, security minus beta times benchmark.

    Assumption (DECISIONS.md does not say which beta): one OLS slope fitted
    on the whole return series passed in. Ranking by this residual instead
    of the raw return leaves out market-wide days that beta already explains.
    Returns the residuals of those days, largest absolute value first.
    """
    beta = security.cov(benchmark) / benchmark.var()
    residual = security - beta * benchmark
    return residual.loc[residual.abs().sort_values(ascending=False).index[:k]]


def outlier_hits(est_days: dict, outlier_dates: pd.DatetimeIndex) -> dict[str, list]:
    """{event_id: the outlier dates among its fitted estimation days}, hits only."""
    hits = {}
    for event_id, days in est_days.items():
        found = days.intersection(outlier_dates)
        if len(found):
            hits[event_id] = list(found)
    return hits


def without_outliers(results: pd.DataFrame, hits: dict) -> pd.DataFrame:
    """The results without the events in hits (a filter, not a rerun)."""
    return results[~results["event_id"].isin(list(hits))]


def print_outliers(outliers: pd.Series, hits: dict, results: pd.DataFrame) -> None:
    """The outlier days, then each event left out of no_outliers and why."""
    print(f"\nLargest absolute residual days ({len(outliers)}, XLE minus beta x SPY):")
    for day, value in outliers.items():
        print(f"  {day.date()}: {value:+.2%}")
    print(f"\nLeft out of the {NO_OUTLIERS} sample ({len(hits)}):")
    directions = results.set_index("event_id")["direction"]
    for event_id, days in hits.items():
        shown = ", ".join(str(d.date()) for d in days)
        print(f"  {event_id} ({directions[event_id]}): estimation days include {shown}")


def print_across_event(table: pd.DataFrame, results: pd.DataFrame) -> None:
    """reporting.print_across_event, showing each excluded event's direction."""
    reporting.print_across_event(table, results, "direction")


def print_time_assumed_excluded(results: pd.DataFrame) -> None:
    """List the time_assumed rows left out of the firm_only sample."""
    left_out = time_assumed_excluded(results)
    print(f"\nLeft out of the firm_only sample ({len(left_out)}):")
    directions = results.set_index("event_id")["direction"]
    for _, row in left_out.iterrows():
        print(f"  {row['event_id']} ({directions[row['event_id']]}, {row['status']}): {row['reason']}")


def load_masks(shift_assumed: bool) -> pd.DataFrame:
    """The mask-only rows (MASK_PATH), printed as a list."""
    masks = load_mask_events(MASK_PATH, shift_assumed=shift_assumed)
    print(f"\nMask-only events ({len(masks)}; skipped in estimation windows, never tested):")
    for _, row in masks.iterrows():
        print(f"  {row['event_id']} (day 0 {row['day0'].date()}): {row['reason']}")
    return masks


def attack_day0s(
    attacks: pd.DataFrame, masks: pd.DataFrame, shifted_masks: pd.DataFrame
) -> pd.DatetimeIndex:
    """Supply-route day 0s whose [-5,+5] days the OPEC+ estimation windows skip.

    attacks: the counted attacks (load_supply_route_events, leak time where
    present). masks and shifted_masks: the attack mask-only file loaded
    with shift_assumed False and True. Every counted attack's day 0, every
    mask row's day 0, and the next session of time_assumed mask rows
    (events.main_and_shifted_day0s; DECISIONS.md: either day could be the
    reaction). Sorted, each day once.

    Assumption: these never depend on --official-time or --shift-assumed.
    Those flags are about OPEC+ rows; the attacks are masked the same way
    run_supply_route.py masks them.
    """
    day0s = pd.concat(
        [attacks["day0"], main_and_shifted_day0s(masks, shifted_masks)], ignore_index=True
    )
    return pd.DatetimeIndex(day0s.drop_duplicates().sort_values())


def load_attack_masks() -> pd.DatetimeIndex:
    """attack_day0s from SUPPLY_ROUTE_EVENTS_PATH and SUPPLY_ROUTE_MASK_PATH, printed.

    The paths are read when called (not as default arguments), so a test
    can point them at its own files. Counted attacks always use their leak
    time where present (load_supply_route_events default), also in an
    --official-time run; no attack has a leak time today.
    """
    attacks = load_supply_route_events(SUPPLY_ROUTE_EVENTS_PATH)
    masks = load_mask_events(SUPPLY_ROUTE_MASK_PATH)
    shifted = load_mask_events(SUPPLY_ROUTE_MASK_PATH, shift_assumed=True)
    day0s = attack_day0s(attacks, masks, shifted)
    print(
        f"\nSupply-route attacks masked ({len(attacks)} counted, {len(masks)} mask-only; "
        f"{len(day0s)} day 0s skipped in estimation windows, never tested):"
    )
    for _, row in attacks.iterrows():
        print(f"  {row['event_id']} (day 0 {row['day0'].date()}): counted attack")
    # zip pairs each mask row with the same row loaded shifted.
    for (_, row), (_, moved) in zip(masks.iterrows(), shifted.iterrows(), strict=True):
        also = f", and {moved['day0'].date()} (time_assumed)" if row["time_assumed"] else ""
        print(f"  {row['event_id']} (day 0 {row['day0'].date()}{also}): mask-only attack")
    return day0s


def combined_mask_day0s(opec_mask_day0s, attack_mask_day0s) -> pd.DatetimeIndex:
    """The OPEC+ mask-only day 0s plus the attack day 0s, sorted, each day once.

    The one set every OPEC+ estimation window skips (run_events,
    estimation_days and estimation_dates all get it). A day in both lists
    is kept once, as in run_supply_route.build_mask_day0s; this only
    changes the nearby_mask_events count, never which days are skipped.
    """
    # One dtype for both, so concat does not have to reconcile two.
    parts = [pd.Series(d, dtype="datetime64[ns]") for d in (opec_mask_day0s, attack_mask_day0s)]
    day0s = pd.concat(parts, ignore_index=True)
    return pd.DatetimeIndex(day0s.drop_duplicates().sort_values())


def load_mask_day0s(shift_assumed: bool) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """(every mask day 0 for this run, the attack part of it), both lists printed.

    The OPEC+ mask-only rows follow --shift-assumed (load_masks); the
    attack day 0s do not (attack_day0s). main and dates_only both call
    this, so a real run and --dates-only skip the same days.
    """
    masks = load_masks(shift_assumed)
    attacks = load_attack_masks()
    return combined_mask_day0s(masks["day0"], attacks), attacks


def average_car_path(results: pd.DataFrame, abnormal: pd.DataFrame, group: str) -> pd.Series:
    """Average cumulative abnormal return by event day for one direction.

    reporting.average_car_path on the rows with this direction: the mean
    abnormal return across the group's "ok" events on each day, summed from
    the first day of the widest window (-5 by default). The last value is
    the group's mean [-5,+5] CAR.
    """
    return reporting.average_car_path(results[results["direction"] == group], abnormal)


def caar_groups(results: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """{headline group: its rows} for the average-CAR chart.

    Saudi unilateral rows are left out, as in the headline tests.
    """
    groups = opec_groups(results)
    return {group: groups[group] for group in HEADLINE_GROUPS}


def dates_only(prices: dict[str, pd.Series], use_leak: bool, shift_assumed: bool = False) -> None:
    """--dates-only: print where each event's windows fall, from dates alone.

    Zeros stand in for returns (simple_returns would drop the first price
    row, so the dates are prices.index[1:]); nothing is computed from prices.
    """
    placeholders = {t: pd.Series(0.0, index=p.index[1:]) for t, p in prices.items()}
    security, _ = reporting.common_dates(
        placeholders[SECURITY], placeholders[BENCHMARK], (SECURITY, BENCHMARK)
    )
    events = load_events(EVENTS_PATH, use_leak=use_leak, shift_assumed=shift_assumed)
    mask_day0s, _ = load_mask_day0s(shift_assumed)
    table = estimation_dates(
        security.index,
        events,
        DEFAULT_EST_LENGTH,
        DEFAULT_GAP,
        DEFAULT_EVENT_WINDOWS,
        mask_day0s,
    )
    reporting.print_dates_only(table)


def main() -> None:
    args = parse_args()
    use_leak = not args.official_time
    shift = args.shift_assumed
    results_path, run_info_path, chart_path = output_paths(args.official_time, shift)
    # Read git first, before this run writes anything.
    git = reporting.git_state()

    # 1. Prices from the cache (downloaded only if missing or --refresh),
    #    then returns.
    prices = {ticker: load_cached(ticker, refresh=args.refresh) for ticker in (SECURITY, BENCHMARK)}
    if args.dates_only:
        dates_only(prices, use_leak, shift)
        return
    security = simple_returns(prices[SECURITY])
    benchmark = simple_returns(prices[BENCHMARK])

    # 2. Line the two series up date for date. (run_events checks the dates
    #    against the NYSE calendar.)
    security, benchmark = reporting.common_dates(security, benchmark, (SECURITY, BENCHMARK))

    # 3-4. Events, the data-coverage check, and the market model.
    #    mask_day0s (OPEC+ mask-only rows and supply-route attacks) is built
    #    once here and passed to every call below that places estimation
    #    windows, so the outlier sample uses the same skipped days.
    events = load_events(EVENTS_PATH, use_leak=use_leak, shift_assumed=shift)
    mask_day0s, attack_mask_day0s = load_mask_day0s(shift)
    reporting.stop_if_data_too_short(
        events, security.index[-1], REFRESH_COMMAND, DEFAULT_EVENT_WINDOWS
    )
    results, abnormal = run_events(
        events,
        security,
        benchmark,
        DEFAULT_EST_LENGTH,
        DEFAULT_GAP,
        DEFAULT_EVENT_WINDOWS,
        mask_day0s,
    )
    reporting.print_summary(results, DEFAULT_EVENT_WINDOWS)

    # 5. Save.
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(results_path, index=False)
    print(f"Saved {results_path}")
    info = build_run_info(
        prices, security, git, use_leak, shift, attack_mask_day0_count=len(attack_mask_day0s)
    )
    run_info_path.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print_run_info(info)
    print(f"Saved {run_info_path}")

    # 6. Across-event tests, filtered from the results above.
    all_table = across_event_table(results, DEFAULT_EVENT_WINDOWS)
    print("\n=== Sample: all events ===")
    print_across_event(all_table, results)
    firm_results = firm_only(results)
    firm_table = across_event_table(firm_results, DEFAULT_EVENT_WINDOWS)
    print("\n=== Sample: without time_assumed rows ===")
    print_across_event(firm_table, firm_results)
    print_time_assumed_excluded(results)

    outliers = largest_residual_days(security, benchmark, OUTLIER_DAYS)
    est_days = estimation_days(
        security.index,
        events,
        DEFAULT_EST_LENGTH,
        DEFAULT_GAP,
        DEFAULT_EVENT_WINDOWS,
        mask_day0s,
    )
    hits = outlier_hits(est_days, outliers.index)
    clean_results = without_outliers(results, hits)
    clean_table = across_event_table(clean_results, DEFAULT_EVENT_WINDOWS)
    print(f"\n=== Sample: without events fitted on the {OUTLIER_DAYS} largest residual days ===")
    print_across_event(clean_table, clean_results)
    print_outliers(outliers, hits, results)

    across = pd.concat(
        [
            all_table.assign(sample="all"),
            firm_table.assign(sample=FIRM_ONLY),
            clean_table.assign(sample=NO_OUTLIERS),
        ],
        ignore_index=True,
    )
    across = across[["sample", *all_table.columns]]
    across_path = across_event_path(args.official_time, shift)
    across.to_csv(across_path, index=False)
    print(f"Saved {across_path}")

    abnormal_path, caar_path = caar_paths(args.official_time, shift)
    abnormal.to_csv(abnormal_path)
    print(f"Saved {abnormal_path}")
    if (results["status"] == "ok").any():
        reporting.draw_chart(
            results,
            abnormal,
            security.index[-1],
            chart_path,
            results_path,
            security=SECURITY,
            benchmark=BENCHMARK,
            est_length=DEFAULT_EST_LENGTH,
            gap=DEFAULT_GAP,
            event_windows=DEFAULT_EVENT_WINDOWS,
        )
        reporting.draw_caar_chart(
            caar_groups(results),
            abnormal,
            security.index[-1],
            caar_path,
            colors=GROUP_COLORS,
            security=SECURITY,
            benchmark=BENCHMARK,
            title=f"{SECURITY} average cumulative abnormal return around OPEC+ decisions",
            xlabel="Trading days from the OPEC+ decision (day 0)",
            est_length=DEFAULT_EST_LENGTH,
            gap=DEFAULT_GAP,
        )
    else:
        print("No events ran, so no chart.")


if __name__ == "__main__":
    main()
