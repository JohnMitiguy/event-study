"""Run the OPEC+ event study: XLE (security) vs SPY (benchmark).

Run from the project root:

    uv run python scripts/run_opec.py            # use the cached prices as they are
    uv run python scripts/run_opec.py --refresh  # re-download prices first

Steps:
1. Load XLE and SPY adjusted closes from the cache in data/prices/. Nothing
   is downloaded unless a cache file is missing or --refresh is passed, so
   re-running gives the same numbers. Turn them into simple daily returns.
2. Check both return series against the NYSE trading calendar. A failure
   STOPS the script: windows count rows, so a missing day would shift every
   window without any error.
3. Load events/opec_events.csv (leak time used where present). If any
   event's widest window ends after the cached data ends, STOP and ask for
   --refresh rather than recording those events as failed.
4. Run the market model for every event and print a summary, including each
   failed event and why.
5. Save results/opec_results.csv, results/opec_run_info.json (which data,
   settings, events file and code produced the results) and, if any event
   ran, charts/opec_events.png: one small panel per event with abnormal
   returns for days -5 to +5.
"""

import argparse
import hashlib
import json
import math
import subprocess
from datetime import datetime
from pathlib import Path

import matplotlib

# "Agg" draws straight to a file, so no chart window pops up.
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import yfinance
from matplotlib.ticker import PercentFormatter

from event_study.event_days import check_trading_days
from event_study.events import load_events
from event_study.prices import (
    cache_path,
    dates_sha256,
    load_cached,
    simple_returns,
    values_sha256,
)
from event_study.runner import (
    car_column,
    events_needing_later_data,
    run_events,
    stat_column,
)
from event_study.windows import (
    DEFAULT_EST_LENGTH,
    DEFAULT_EVENT_WINDOWS,
    DEFAULT_GAP,
    window_label,
)

SECURITY = "XLE"
BENCHMARK = "SPY"
# Main results use the leak time where present (DECISIONS.md); False is the
# official-time robustness check.
USE_LEAK = True
EVENTS_PATH = Path("events") / "opec_events.csv"
RESULTS_PATH = Path("results") / "opec_results.csv"
RUN_INFO_PATH = Path("results") / "opec_run_info.json"
CHART_PATH = Path("charts") / "opec_events.png"

# Event days drawn in each panel. Must lie inside the widest event window.
CHART_DAYS = range(-5, 6)
PANEL_COLUMNS = 4

# Colors from the same palette as plot_prices.py.
DAY0 = "#2a78d6"
OTHER_DAYS = "#c3c2b7"
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e0"
BASELINE = "#c3c2b7"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the OPEC+ event study (XLE vs SPY).")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="re-download XLE and SPY prices before running (otherwise the cache is used as is)",
    )
    return parser.parse_args()


def check_or_stop(ticker: str, returns: pd.Series) -> None:
    """Run the trading-day check; on failure print why and stop the script."""
    try:
        check_trading_days(returns)
    except ValueError as err:
        raise SystemExit(f"{ticker}: trading-day check FAILED, stopping.\n{err}") from None
    first, last = returns.index[0].date(), returns.index[-1].date()
    print(f"{ticker}: trading days OK ({first} to {last}, {len(returns)} days)")


def common_dates(a: pd.Series, b: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Trim both series to the dates they share.

    Both have passed check_trading_days, so between a shared first and last
    date they hold exactly the same NYSE sessions; only the ends can differ.
    """
    first = max(a.index[0], b.index[0])
    last = min(a.index[-1], b.index[-1])
    a, b = a.loc[first:last], b.loc[first:last]
    if not a.index.equals(b.index):
        raise SystemExit("XLE and SPY dates still differ after trimming; check the data.")
    return a, b


def stop_if_data_too_short(events: pd.DataFrame, last_date: pd.Timestamp) -> None:
    """Stop if any event's widest window ends after the last data date."""
    needing = events_needing_later_data(events, last_date, DEFAULT_EVENT_WINDOWS)
    if needing:
        raise SystemExit(
            f"{len(needing)} event(s) need prices after the cached data ends "
            f"({last_date.date()}): {', '.join(needing)}\n"
            "Re-run with --refresh to download fresh prices:\n"
            "    uv run python scripts/run_opec.py --refresh\n"
            "If you just refreshed, these events are too recent: their last "
            "window day has not closed yet."
        )


def file_sha256(path: Path) -> str:
    """SHA-256 of a file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_state() -> tuple[str | None, bool | None]:
    """(commit hash, dirty) for the working tree, or (None, None) without git.

    dirty is True if any file has uncommitted changes, untracked files
    included, except under results/ and charts/: those are this script's own
    outputs and would otherwise make every second run look dirty.
    """
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--", ".", ":(exclude)results", ":(exclude)charts"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None, None
    return commit, status.strip() != ""


def ticker_info(ticker: str, prices: pd.Series) -> dict:
    """What identifies one ticker's cached data: file, dates, rows, hashes."""
    path = cache_path(ticker)
    modified = datetime.fromtimestamp(path.stat().st_mtime).astimezone()
    return {
        "cache_file": path.as_posix(),
        "cache_modified": modified.isoformat(timespec="seconds"),
        "first_date": str(prices.index[0].date()),
        "last_date": str(prices.index[-1].date()),
        "rows": len(prices),
        "dates_sha256": dates_sha256(prices),
        "adj_close_sha256": values_sha256(prices),
    }


def build_run_info(prices: dict[str, pd.Series], returns_used: pd.Series, git: tuple) -> dict:
    """Everything needed to tell whether two runs used the same inputs."""
    commit, dirty = git
    return {
        "tickers": {ticker: ticker_info(ticker, series) for ticker, series in prices.items()},
        "returns_used": {
            "first_date": str(returns_used.index[0].date()),
            "last_date": str(returns_used.index[-1].date()),
            "rows": len(returns_used),
        },
        "est_length": DEFAULT_EST_LENGTH,
        "gap": DEFAULT_GAP,
        "event_windows": [list(w) for w in DEFAULT_EVENT_WINDOWS],
        "use_leak": USE_LEAK,
        "events_file": EVENTS_PATH.as_posix(),
        "events_file_sha256": file_sha256(EVENTS_PATH),
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
    print(f"  events file sha256 {info['events_file_sha256'][:12]}, use_leak {info['use_leak']}")
    commit = info["git_commit"][:12] if info["git_commit"] else "unavailable"
    print(f"  git commit {commit}, uncommitted changes: {info['git_dirty']}")


def print_summary(results: pd.DataFrame) -> None:
    """Number of events, the failures with reasons, and each event's numbers."""
    failed = results[results["status"] == "failed"]
    ran = results[results["status"] == "ok"]
    print(f"\n{len(results)} event(s): {len(ran)} ok, {len(failed)} failed")
    for _, row in failed.iterrows():
        print(f"  FAILED {row['event_id']} (day 0 {row['day0'].date()}): {row['error']}")

    if ran.empty:
        return
    header = f"{'event_id':<24} {'day 0':<10}"
    for window in DEFAULT_EVENT_WINDOWS:
        header += f" {'CAR ' + window_label(window):>14} {'t':>6}"
    print("\n" + header + f" {'est overlap':>11} {'nearby':>6}")
    for _, row in ran.iterrows():
        line = f"{row['event_id']:<24} {row['day0'].date()!s:<10}"
        for window in DEFAULT_EVENT_WINDOWS:
            line += f" {row[car_column(window)]:>+14.2%} {row[stat_column(window)]:>6.2f}"
        print(line + f" {row['est_overlap_days']:>11} {row['nearby_events']:>6}")


def draw_panel(ax, event_id: str, day0: pd.Timestamp, abnormal: pd.Series) -> None:
    """Bars of one event's abnormal returns by event day, day 0 highlighted."""
    days = list(CHART_DAYS)
    colors = [DAY0 if day == 0 else OTHER_DAYS for day in days]
    ax.bar(days, abnormal.loc[days].to_numpy(), width=0.6, color=colors)
    ax.axhline(0, color=BASELINE, linewidth=1)
    ax.set_title(f"{event_id}\nday 0 = {day0.date()}", fontsize=9)
    ax.set_xticks([days[0], 0, days[-1]])
    # "−" (Unicode minus) matches the minus sign matplotlib uses on the y-axis.
    ax.xaxis.set_major_formatter(lambda x, _: f"{x:+.0f}".replace("-", "−") if x != 0 else "0")
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    ax.tick_params(labelsize=8, colors=TEXT_SECONDARY)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)


def draw_chart(results: pd.DataFrame, abnormal: pd.DataFrame, data_end: pd.Timestamp) -> None:
    """One small panel per event that ran, all on the same y-axis scale."""
    ran = results[results["status"] == "ok"]
    rows = math.ceil(len(ran) / PANEL_COLUMNS)
    columns = min(len(ran), PANEL_COLUMNS)
    # sharey=True puts every panel on one scale, so bar heights compare
    # across events. squeeze=False keeps `axes` a 2-D grid even for one panel.
    fig, axes = plt.subplots(
        rows, columns, figsize=(3.2 * columns, 2.6 * rows + 0.8), sharey=True, squeeze=False
    )
    flat = axes.flatten()
    for ax, (_, row) in zip(flat, ran.iterrows(), strict=False):
        draw_panel(ax, row["event_id"], row["day0"], abnormal.loc[row["event_id"]])
    for ax in flat[len(ran):]:
        ax.set_visible(False)  # empty slots in the last row

    fig.suptitle(
        f"{SECURITY} abnormal returns vs {BENCHMARK} market model, event days "
        f"{CHART_DAYS[0]} to +{CHART_DAYS[-1]} (day 0 highlighted)",
        fontsize=11,
    )
    caption = (
        f"Market model fitted on {DEFAULT_EST_LENGTH} trading days ending on day "
        f"-{DEFAULT_GAP}. Source: Yahoo Finance adjusted close (yfinance), data through "
        f"{data_end.date()}. Failed events are not shown; see {RESULTS_PATH.as_posix()}."
    )
    fig.text(0.01, 0.01, caption, fontsize=7, color=TEXT_SECONDARY)

    CHART_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0.04, 1, 1))  # leave room at the bottom for the caption
    fig.savefig(CHART_PATH, dpi=150)
    print(f"Saved {CHART_PATH}")


def main() -> None:
    args = parse_args()
    # Read git first, before this run writes anything.
    git = git_state()

    # 1. Prices from the cache (downloaded only if missing or --refresh),
    #    then returns.
    prices = {ticker: load_cached(ticker, refresh=args.refresh) for ticker in (SECURITY, BENCHMARK)}
    security = simple_returns(prices[SECURITY])
    benchmark = simple_returns(prices[BENCHMARK])

    # 2. Calendar check, then line the two series up date for date.
    check_or_stop(SECURITY, security)
    check_or_stop(BENCHMARK, benchmark)
    security, benchmark = common_dates(security, benchmark)

    # 3-4. Events, the data-coverage check, and the market model.
    events = load_events(EVENTS_PATH, use_leak=USE_LEAK)
    stop_if_data_too_short(events, security.index[-1])
    results, abnormal = run_events(
        events, security, benchmark, DEFAULT_EST_LENGTH, DEFAULT_GAP, DEFAULT_EVENT_WINDOWS
    )
    print_summary(results)

    # 5. Save.
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(RESULTS_PATH, index=False)
    print(f"Saved {RESULTS_PATH}")
    info = build_run_info(prices, security, git)
    RUN_INFO_PATH.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print_run_info(info)
    print(f"Saved {RUN_INFO_PATH}")
    if (results["status"] == "ok").any():
        draw_chart(results, abnormal, security.index[-1])
    else:
        print("No events ran, so no chart.")


if __name__ == "__main__":
    main()
