"""Printing, run-info and chart helpers shared by the run scripts.

scripts/run_opec.py uses these, and a later script for another event type
can reuse them. Nothing here knows about OPEC+: the security and benchmark
tickers, the groups, the headline result and the chart colors are all
passed in by the script.

Assumptions:
- `results` and `abnormal` are the two tables runner.run_events returns.
- A "groups" mapping is {group name: a filter of the finished results
  table}, never of the events table (DECISIONS.md: dropping an event
  beforehand would change its neighbours' estimation windows).
- Importing this module switches matplotlib to the "Agg" backend, which
  draws straight to a file, so no chart window pops up.
"""

import hashlib
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

from event_study.aggregate import MIN_EVENTS, across_event_tests, excluded_events
from event_study.prices import cache_path, dates_sha256, values_sha256
from event_study.runner import (
    car_column,
    events_needing_later_data,
    stat_column,
    widest_window,
)
from event_study.windows import (
    DEFAULT_EST_LENGTH,
    DEFAULT_EVENT_WINDOWS,
    DEFAULT_GAP,
    window_label,
)

# Event days drawn in each panel. Must lie inside the widest event window.
CHART_DAYS = range(-5, 6)
PANEL_COLUMNS = 4

# Caption text size, and roughly how many characters of it fit in one inch
# (set a little low so a line never runs off the edge). One caption line
# takes about 1.3 times the font size in height; 72 points make an inch.
CAPTION_FONTSIZE = 7
CAPTION_CHARS_PER_INCH = 16
CAPTION_LINE_HEIGHT_IN = 1.3 * CAPTION_FONTSIZE / 72

# Colors from the same palette as plot_prices.py. Group colors are passed in
# by the script (they depend on its groups).
DAY0 = "#2a78d6"
OTHER_DAYS = "#c3c2b7"
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e0"
BASELINE = "#c3c2b7"


def common_dates(a: pd.Series, b: pd.Series, names: tuple[str, str]) -> tuple[pd.Series, pd.Series]:
    """Trim both series to the dates they share.

    names are the two tickers, used only in the error message.

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
        raise SystemExit(f"{names[0]} and {names[1]} dates still differ after trimming; check the data.")
    return a, b


def stop_if_data_too_short(
    events: pd.DataFrame,
    last_date: pd.Timestamp,
    refresh_command: str,
    event_windows=DEFAULT_EVENT_WINDOWS,
) -> None:
    """Stop if any event's widest window ends after the last data date.

    refresh_command is the command printed for downloading fresh prices,
    for example "uv run python scripts/run_opec.py --refresh".
    """
    needing = events_needing_later_data(events, last_date, event_windows)
    if needing:
        raise SystemExit(
            f"{len(needing)} event(s) need prices after the cached data ends "
            f"({last_date.date()}): {', '.join(needing)}\n"
            "Re-run with --refresh to download fresh prices:\n"
            f"    {refresh_command}\n"
            "If you just refreshed, these events are too recent: their last "
            "window day has not closed yet."
        )


def file_sha256(path: Path) -> str:
    """SHA-256 of a file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_state() -> tuple[str | None, bool | None]:
    """(commit hash, dirty) for the working tree, or (None, None) without git.

    dirty is True if any file has uncommitted changes, untracked files
    included, except under results/ and charts/: those are the run scripts'
    own outputs and would otherwise make every second run look dirty.
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


def print_summary(results: pd.DataFrame, event_windows=DEFAULT_EVENT_WINDOWS) -> None:
    """Number of events, the failures with reasons, and each event's numbers.

    event_windows must be the windows results was run with (one CAR and t
    column each).
    """
    failed = results[results["status"] == "failed"]
    ran = results[results["status"] == "ok"]
    print(f"\n{len(results)} event(s): {len(ran)} ok, {len(failed)} failed")
    for _, row in failed.iterrows():
        print(f"  FAILED {row['event_id']} (day 0 {row['day0'].date()}): {row['error']}")

    if ran.empty:
        return
    header = f"{'event_id':<24} {'day 0':<10}"
    for window in event_windows:
        header += f" {'CAR ' + window_label(window):>14} {'t':>6}"
    print("\n" + header + f" {'masked':>6} {'nearby':>6} {'n_mask':>6}")
    for _, row in ran.iterrows():
        line = f"{row['event_id']:<24} {row['day0'].date()!s:<10}"
        for window in event_windows:
            line += f" {row[car_column(window)]:>+14.2%} {row[stat_column(window)]:>6.2f}"
        print(
            line
            + f" {row['est_masked_days']:>6} {row['nearby_events']:>6} {row['nearby_mask_events']:>6}"
        )


def print_dates_only(table: pd.DataFrame) -> None:
    """Per event: day 0, estimation window, skipped days, span and neighbours.

    table is runner.estimation_dates' output. est_span is the trading days
    from est_start to est_end inclusive. An event that lacks the data for its
    windows shows its reason instead.
    """
    print(f"\n{len(table)} event(s); no returns, regressions or CARs computed.\n")
    print(
        f"{'event_id':<24} {'day 0':<10} {'est_start':<10} {'est_end':<10} "
        f"{'masked':>6} {'est_span':>8} {'nearby':>6} {'n_mask':>6}"
    )
    for _, row in table.iterrows():
        line = f"{row['event_id']:<24} {row['day0'].date()!s:<10} "
        if pd.isna(row["error"]):
            line += (
                f"{row['est_start'].date()!s:<10} {row['est_end'].date()!s:<10} "
                f"{row['est_masked_days']:>6} {row['est_span_days']:>8} {row['nearby_events']:>6} "
                f"{row['nearby_mask_events']:>6}"
            )
        else:
            line += (
                f"{'-':<10} {'-':<10} {'-':>6} {'-':>8} {row['nearby_events']:>6} "
                f"{row['nearby_mask_events']:>6}  {row['error']}"
            )
        print(line)


def across_event_table(
    groups: dict[str, pd.DataFrame],
    windows,
    headline_window: tuple[int, int],
    headline_groups,
    include_cs_p: bool = False,
) -> pd.DataFrame:
    """One row per window and group: N ok, mean CAR and the four tests.

    groups: {group name: that group's rows of the finished results table},
    in the order the rows should appear. Building it is the script's job
    (which events go in which group is a choice for each event type).

    headline is True for headline_window and the groups in headline_groups.
    N counts rows with status "ok" only. A group with fewer than MIN_EVENTS
    of them is not tested: tested is False, the statistics are empty and
    note says "too few events". Otherwise the numbers come straight from
    aggregate.across_event_tests, which still raises ValueError for things
    like identical CARs.

    include_cs_p=True adds a cs_p column right after cross_sectional_t: the
    two-sided p-value of the cross-sectional t. Off by default, so the
    OPEC+ table keeps its columns.
    """
    rows = []
    for window in windows:
        for group, subset in groups.items():
            n_ok = int((subset["status"] == "ok").sum())
            tested = n_ok >= MIN_EVENTS
            row = {
                "window": window_label(window),
                "group": group,
                "n_ok": n_ok,
                "tested": tested,
                "headline": tuple(window) == tuple(headline_window) and group in headline_groups,
                "note": "" if tested else f"too few events (N < {MIN_EVENTS})",
            }
            if tested:
                result = across_event_tests(subset, window)
                tests = result.tests
                row |= {
                    "mean_car": result.mean_car,
                    "cross_sectional_t": tests.loc["cross_sectional_t", "statistic"],
                    "cs_p": tests.loc["cross_sectional_t", "p_value"],
                    "bmp_t": tests.loc["bmp", "statistic"],
                    "wilcoxon_p": tests.loc["wilcoxon", "p_value"],
                    "sign_p": tests.loc["sign", "p_value"],
                }
            rows.append(row)
    columns = [
        "window", "group", "n_ok", "tested", "headline", "mean_car",
        "cross_sectional_t", "bmp_t", "wilcoxon_p", "sign_p", "note",
    ]  # fmt: skip
    if include_cs_p:
        columns.insert(columns.index("cross_sectional_t") + 1, "cs_p")
    # columns= keeps only the listed keys of each row dict, so cs_p is
    # dropped when not asked for.
    return pd.DataFrame(rows, columns=columns)


# The legend under the across-event heading for OPEC+ (its default).
OPEC_LEGEND = "* = headline result, fixed before the first full run; 'all' is descriptive only."


def print_across_event(
    table: pd.DataFrame, results: pd.DataFrame, label_column: str, legend: str = OPEC_LEGEND
) -> None:
    """The across-event table, then every event that is not "ok" and why.

    label_column is a results column shown next to each excluded event
    (for OPEC+: "direction"). legend is the line explaining the "*" mark
    (rows with headline True).
    """
    print("\nAcross-event tests (two-sided; events assumed independent, see aggregate.py).")
    print(legend)
    for window, part in table.groupby("window", sort=False):
        print(f"\n  Window {window}")
        print(
            f"    {'group':<17} {'N ok':>4} {'mean CAR':>9} {'CS t':>7} {'BMP t':>7} "
            f"{'Wilcoxon p':>11} {'sign p':>7}"
        )
        for _, row in part.iterrows():
            mark = "*" if row["headline"] else " "
            line = f"  {mark} {row['group']:<17} {row['n_ok']:>4} "
            if row["tested"]:
                line += (
                    f"{row['mean_car']:>+9.2%} {row['cross_sectional_t']:>7.2f} "
                    f"{row['bmp_t']:>7.2f} {row['wilcoxon_p']:>11.3f} {row['sign_p']:>7.3f}"
                )
            else:
                line += row["note"]
            print(line)
    excluded = excluded_events(results)
    if excluded.empty:
        print("\nEvents excluded from the across-event tests: none")
        return
    print(f"\nEvents excluded from the across-event tests ({len(excluded)}):")
    labels = results.set_index("event_id")[label_column]
    for _, row in excluded.iterrows():
        print(f"  {row['event_id']} ({labels[row['event_id']]}, {row['status']}): {row['reason']}")


def average_car_path(results: pd.DataFrame, abnormal: pd.DataFrame) -> pd.Series:
    """Average cumulative abnormal return by event day over the "ok" rows of results.

    Pass one group's rows of the results table. Mean abnormal return across
    its "ok" events on each day, summed from the first day of the widest
    window (-5 by default). The last value is the group's mean CAR over the
    widest window.
    """
    ids = results.loc[results["status"] == "ok", "event_id"]
    return abnormal.loc[ids].mean().cumsum()


def wrap_caption(text: str, fig_width: float) -> str:
    """Break text into lines that fit across a figure fig_width inches wide.

    The width is estimated from CAPTION_CHARS_PER_INCH, leaving the 1% margin
    on each side that the caption is drawn with.
    """
    width = int(0.98 * fig_width * CAPTION_CHARS_PER_INCH)
    return textwrap.fill(text, width=width)


def percent_label(x: float, _pos=None) -> str:
    """Y-axis label for a return: 0.025 -> "2.5%", 0.02 -> "2%", -0.005 -> "−0.5%".

    Uses only the decimals the tick needs, so ticks 0.5% apart don't all
    round to the same whole percent (PercentFormatter(decimals=0) labelled
    0.5%, 1.0%, 1.5% and 2.0% as "0%, 1%, 2%, 2%"). ":g" also drops float
    noise like 1.5000000000000002. "+ 0" turns -0.0 into 0.0, and "−"
    (Unicode minus) matches the x-axis labels.
    """
    return f"{x * 100 + 0:g}%".replace("-", "−")


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
    ax.yaxis.set_major_formatter(percent_label)
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
    *,
    security: str,
    benchmark: str,
    est_length: int = DEFAULT_EST_LENGTH,
    gap: int = DEFAULT_GAP,
    event_windows=DEFAULT_EVENT_WINDOWS,
) -> None:
    """One small panel per event that ran, all on the same y-axis scale.

    Saved to chart_path; the caption points to results_path for failed events.
    security and benchmark are the tickers named in the title and caption;
    est_length, gap and event_windows must be the ones results was run with
    (they are only written into the caption).
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
        f"{security} abnormal returns vs {benchmark} market model, event days "
        f"{CHART_DAYS[0]} to +{CHART_DAYS[-1]} (day 0 highlighted)",
        fontsize=11,
    )
    widest = window_label(widest_window(event_windows))
    # " " is a non-breaking space, so wrapping never splits "day -10".
    caption = (
        f"Market model fitted on {est_length} trading days up to day "
        f"-{gap}, skipping days inside other events' {widest} windows and reaching "
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
    # Keep the top half inch for the title, so it never runs into the first row.
    fig.tight_layout(rect=(0, bottom, 1, 1 - 0.5 / fig_height))
    fig.savefig(chart_path, dpi=150)
    print(f"Saved {chart_path}")


def draw_caar_chart(
    groups: dict[str, pd.DataFrame],
    abnormal: pd.DataFrame,
    data_end: pd.Timestamp,
    path: Path,
    *,
    colors: dict[str, str],
    security: str,
    benchmark: str,
    title: str,
    xlabel: str,
    est_length: int = DEFAULT_EST_LENGTH,
    gap: int = DEFAULT_GAP,
) -> None:
    """One line per group: average CAR from the first chart day through each day.

    groups: {group name: that group's rows of the results table}, one line
    each, drawn in this order in colors[group name]. A group with no "ok"
    event is left out. Each line's end label is the group name capitalized
    with an "s" added ("cut" -> "Cuts"), its N ok and its last value.
    security and benchmark are named in the caption; est_length and gap must
    be the ones results was run with (they are only written into the caption).
    """
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for group, rows in groups.items():
        n = int((rows["status"] == "ok").sum())
        if n == 0:
            continue
        path_ = average_car_path(rows, abnormal)
        color = colors[group]
        ax.plot(path_.index, path_.to_numpy(), color=color, linewidth=2, marker="o", markersize=4)
        label = f"{group.capitalize()}s (N = {n}): {path_.iloc[-1]:+.1%}"
        ax.annotate(
            label,
            (path_.index[-1], path_.iloc[-1]),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
            color=TEXT_SECONDARY,
        )
    ax.axhline(0, color=BASELINE, linewidth=1)
    ax.axvline(0, color=GRID, linewidth=1, zorder=0)
    days = list(CHART_DAYS)
    ax.set_xticks(days)
    ax.xaxis.set_major_formatter(lambda x, _: f"{x:+.0f}".replace("-", "−") if x != 0 else "0")
    ax.yaxis.set_major_formatter(percent_label)
    ax.set_xlim(days[0] - 0.5, days[-1] + 3.5)  # room for the end labels
    ax.set_xlabel(xlabel, fontsize=9, color=TEXT_SECONDARY)
    ax.tick_params(labelsize=8, colors=TEXT_SECONDARY)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(title, fontsize=11, loc="left")
    caption = (
        f"Abnormal return = {security} return minus a market model on {benchmark}, fitted on "
        f"{est_length} trading days ending day -{gap}. Cumulated from day "
        f"{days[0]}. Source: Yahoo Finance adjusted close, data through {data_end.date()}."
    )
    fig.text(
        0.01,
        0.01,
        wrap_caption(caption, fig.get_size_inches()[0]),
        fontsize=CAPTION_FONTSIZE,
        color=TEXT_SECONDARY,
        va="bottom",
    )
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    print(f"Saved {path}")
