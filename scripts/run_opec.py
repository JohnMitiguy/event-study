"""Run the OPEC+ event study: XLE (security) vs SPY (benchmark).

Run from the project root:

    uv run python scripts/run_opec.py            # use the cached prices as they are
    uv run python scripts/run_opec.py --refresh  # re-download prices first
    uv run python scripts/run_opec.py --official-time  # robustness check: ignore leak times
    uv run python scripts/run_opec.py --dates-only  # where each window falls; no returns

Steps:
1. Load XLE and SPY adjusted closes from the cache in data/prices/. Nothing
   is downloaded unless a cache file is missing or --refresh is passed, so
   re-running gives the same numbers. Turn them into simple daily returns.
2. Line the two return series up date for date. run_events checks both
   against the NYSE trading calendar and STOPS with a ValueError on a
   failure: windows count rows, so a missing day would shift every window
   without any error.
3. Load events/opec_events.csv (leak time used where present). If any
   event's widest window ends after the cached data ends, STOP and ask for
   --refresh rather than recording those events as failed.
4. Run the market model for every event and print a summary, including each
   failed event and why.
5. Save results/opec_results.csv, results/opec_run_info.json (which data,
   settings, events file and code produced the results) and, if any event
   ran, charts/opec_events.png: one small panel per event with abnormal
   returns for days -5 to +5.

With --dates-only the script prints, per event, day 0, the estimation window
(est_start, est_end, skipped days, span in trading days) and nearby_events,
then stops. No returns, regressions or CARs are computed, and nothing is
saved. It uses the same events, skipping rule and calendar check as a real run,
so it can be run before reading any CAR (DECISIONS.md: the look-back limit
is chosen from event dates).

With --official-time, events use the official announcement time even where
a leak time exists, and every output name gets "_official_time" added (see
output_paths), so this run can never overwrite the main results.
"""

import argparse
import hashlib
import json
import math
import subprocess
import textwrap
from datetime import datetime
from pathlib import Path

import matplotlib

# "Agg" draws straight to a file, so no chart window pops up.
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import yfinance
from matplotlib.ticker import PercentFormatter

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
    estimation_dates,
    events_needing_later_data,
    run_events,
    stat_column,
    widest_window,
)
from event_study.windows import (
    DEFAULT_EST_LENGTH,
    DEFAULT_EVENT_WINDOWS,
    DEFAULT_GAP,
    window_label,
)

SECURITY = "XLE"
BENCHMARK = "SPY"
EVENTS_PATH = Path("events") / "opec_events.csv"

# Event days drawn in each panel. Must lie inside the widest event window.
CHART_DAYS = range(-5, 6)
PANEL_COLUMNS = 4

# Caption text size, and roughly how many characters of it fit in one inch
# (set a little low so a line never runs off the edge). One caption line
# takes about 1.3 times the font size in height; 72 points make an inch.
CAPTION_FONTSIZE = 7
CAPTION_CHARS_PER_INCH = 16
CAPTION_LINE_HEIGHT_IN = 1.3 * CAPTION_FONTSIZE / 72

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
    return parser.parse_args()


def output_paths(official_time: bool) -> tuple[Path, Path, Path]:
    """(results CSV, run info JSON, chart PNG) for this run.

    Main results use the leak time where present (DECISIONS.md). The
    official-time robustness run adds "_official_time" to every file name,
    so it can never overwrite the main outputs.
    """
    suffix = "_official_time" if official_time else ""
    return (
        Path("results") / f"opec_results{suffix}.csv",
        Path("results") / f"opec_run_info{suffix}.json",
        Path("charts") / f"opec_events{suffix}.png",
    )


def common_dates(a: pd.Series, b: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Trim both series to the dates they share.

    Each series is expected to hold every NYSE session between its own first
    and last date (run_events checks this afterwards), so between a shared
    first and last date they hold the same sessions; only the ends can differ.
    A series with a hole is caught by run_events, or here as "dates still
    differ" if the other series has no hole.
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


def build_run_info(
    prices: dict[str, pd.Series], returns_used: pd.Series, git: tuple, use_leak: bool
) -> dict:
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
        "use_leak": use_leak,
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
    print("\n" + header + f" {'masked':>6} {'nearby':>6}")
    for _, row in ran.iterrows():
        line = f"{row['event_id']:<24} {row['day0'].date()!s:<10}"
        for window in DEFAULT_EVENT_WINDOWS:
            line += f" {row[car_column(window)]:>+14.2%} {row[stat_column(window)]:>6.2f}"
        print(line + f" {row['est_masked_days']:>6} {row['nearby_events']:>6}")


def print_dates_only(table: pd.DataFrame) -> None:
    """Per event: day 0, estimation window, skipped days, span and neighbours.

    est_span is the trading days from est_start to est_end inclusive. An
    event that lacks the data for its windows shows its reason instead.
    """
    print(f"\n{len(table)} event(s); no returns, regressions or CARs computed.\n")
    print(
        f"{'event_id':<24} {'day 0':<10} {'est_start':<10} {'est_end':<10} "
        f"{'masked':>6} {'est_span':>8} {'nearby':>6}"
    )
    for _, row in table.iterrows():
        line = f"{row['event_id']:<24} {row['day0'].date()!s:<10} "
        if pd.isna(row["error"]):
            line += (
                f"{row['est_start'].date()!s:<10} {row['est_end'].date()!s:<10} "
                f"{row['est_masked_days']:>6} {row['est_span_days']:>8} {row['nearby_events']:>6}"
            )
        else:
            line += f"{'-':<10} {'-':<10} {'-':>6} {'-':>8} {row['nearby_events']:>6}  {row['error']}"
        print(line)


def wrap_caption(text: str, fig_width: float) -> str:
    """Break text into lines that fit across a figure fig_width inches wide.

    The width is estimated from CAPTION_CHARS_PER_INCH, leaving the 1% margin
    on each side that the caption is drawn with.
    """
    width = int(0.98 * fig_width * CAPTION_CHARS_PER_INCH)
    return textwrap.fill(text, width=width)


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


def draw_chart(
    results: pd.DataFrame,
    abnormal: pd.DataFrame,
    data_end: pd.Timestamp,
    chart_path: Path,
    results_path: Path,
) -> None:
    """One small panel per event that ran, all on the same y-axis scale.

    Saved to chart_path; the caption points to results_path for failed events.
    """
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
    widest = window_label(widest_window(DEFAULT_EVENT_WINDOWS))
    # " " is a non-breaking space, so wrapping never splits "day -10".
    caption = (
        f"Market model fitted on {DEFAULT_EST_LENGTH} trading days up to day "
        f"-{DEFAULT_GAP}, skipping days inside other events' {widest} windows and reaching "
        "further back to make up for them. Source: Yahoo Finance adjusted close (yfinance), "
        f"data through {data_end.date()}. Failed events are not shown; see "
        f"{results_path.as_posix()}."
    )
    fig_width, fig_height = fig.get_size_inches()
    caption = wrap_caption(caption, fig_width)
    # va="bottom": the caption's last line sits on y = 0.01 and extra lines go up.
    fig.text(0.01, 0.01, caption, fontsize=CAPTION_FONTSIZE, color=TEXT_SECONDARY, va="bottom")

    chart_path.parent.mkdir(parents=True, exist_ok=True)
    # Leave room at the bottom for the caption's lines, plus a little padding.
    n_lines = caption.count("\n") + 1
    bottom = (n_lines * CAPTION_LINE_HEIGHT_IN + 0.15) / fig_height
    fig.tight_layout(rect=(0, bottom, 1, 1))
    fig.savefig(chart_path, dpi=150)
    print(f"Saved {chart_path}")


def dates_only(prices: dict[str, pd.Series], use_leak: bool) -> None:
    """--dates-only: print where each event's windows fall, from dates alone.

    Zeros stand in for returns (simple_returns would drop the first price
    row, so the dates are prices.index[1:]); nothing is computed from prices.
    """
    placeholders = {t: pd.Series(0.0, index=p.index[1:]) for t, p in prices.items()}
    security, _ = common_dates(placeholders[SECURITY], placeholders[BENCHMARK])
    events = load_events(EVENTS_PATH, use_leak=use_leak)
    table = estimation_dates(
        security.index, events, DEFAULT_EST_LENGTH, DEFAULT_GAP, DEFAULT_EVENT_WINDOWS
    )
    print_dates_only(table)


def main() -> None:
    args = parse_args()
    use_leak = not args.official_time
    results_path, run_info_path, chart_path = output_paths(args.official_time)
    # Read git first, before this run writes anything.
    git = git_state()

    # 1. Prices from the cache (downloaded only if missing or --refresh),
    #    then returns.
    prices = {ticker: load_cached(ticker, refresh=args.refresh) for ticker in (SECURITY, BENCHMARK)}
    if args.dates_only:
        dates_only(prices, use_leak)
        return
    security = simple_returns(prices[SECURITY])
    benchmark = simple_returns(prices[BENCHMARK])

    # 2. Line the two series up date for date. (run_events checks the dates
    #    against the NYSE calendar.)
    security, benchmark = common_dates(security, benchmark)

    # 3-4. Events, the data-coverage check, and the market model.
    events = load_events(EVENTS_PATH, use_leak=use_leak)
    stop_if_data_too_short(events, security.index[-1])
    results, abnormal = run_events(
        events, security, benchmark, DEFAULT_EST_LENGTH, DEFAULT_GAP, DEFAULT_EVENT_WINDOWS
    )
    print_summary(results)

    # 5. Save.
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(results_path, index=False)
    print(f"Saved {results_path}")
    info = build_run_info(prices, security, git, use_leak)
    run_info_path.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print_run_info(info)
    print(f"Saved {run_info_path}")
    if (results["status"] == "ok").any():
        draw_chart(results, abnormal, security.index[-1], chart_path, results_path)
    else:
        print("No events ran, so no chart.")


if __name__ == "__main__":
    main()
