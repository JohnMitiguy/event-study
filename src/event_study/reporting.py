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
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e0"
BASELINE = "#c3c2b7"
# The before/after day 0 chart: days before day 0 take the highlight color,
# days from day 0 on a muted gray (darker than OTHER_DAYS, so a column still
# stands out against the white background).
BEFORE_DAY0 = DAY0
FROM_DAY0 = "#898781"

# Two-sided 95% point of the standard normal, for per-event intervals. The
# per-event t was calibrated against +/-1.96 (DECISIONS.md).
Z_95 = 1.96


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
    """SHA-256 of a text file's bytes, with every Windows line ending made Unix.

    Every b"\\r\\n" is replaced by b"\\n" before hashing. git checks a file out
    with CRLF line endings on Windows (core.autocrlf true) and LF on Linux,
    so hashing raw bytes would give two hashes for one committed file. This
    hash matches the committed (LF) file on any checkout.

    Used for the events and mask-only CSVs, which are text. A lone b"\\r" is
    left as it is, so a real content change still changes the hash.
    """
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


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


def signed(value: float, decimals: int = 2) -> str:
    """A return as signed percent text: 0.031 -> "+3.10%", -0.0282 -> "−2.82%".

    "−" (Unicode minus) matches the axis labels (see percent_label).
    """
    return f"{value:+.{decimals}%}".replace("-", "−")


def day_label(day: int) -> str:
    """An event day as axis text: -5 -> "−5", 0 -> "0", 5 -> "+5"."""
    return f"{day:+d}".replace("-", "−") if day != 0 else "0"


def split_car(abnormal: pd.DataFrame) -> tuple[float, float]:
    """(mean CAR over the days before day 0, mean CAR from day 0 on).

    abnormal: one row per event, "ok" events only, one column per event day
    (ints, or strings like "-5" as read back from the abnormal CSVs). Each
    event's abnormal returns are summed over the days before 0 and over day 0
    and after, and each sum is averaged across events. The two add up to the
    mean CAR over every column (days -5 to +5 by default).

    A descriptive split, not a test: nothing here says whether either part
    differs from zero.
    """
    days = abnormal.columns.astype(int)
    before = abnormal.loc[:, days < 0].sum(axis=1).mean()
    after = abnormal.loc[:, days >= 0].sum(axis=1).mean()
    return float(before), float(after)


def car_interval(rows: pd.DataFrame, window: tuple[int, int], z: float = Z_95) -> pd.DataFrame:
    """Each event's CAR over window, with an interval of z standard errors.

    rows: rows of a results table, "ok" rows only. The standard error is
    resid_std times the square root of the window length, the one the
    per-event t divides by (market_model.car_test). Like that t, it treats
    the fitted alpha and beta as exact, so the interval is slightly too
    narrow. Returns columns event_id, car, low and high, in the order of rows.
    """
    length = window[1] - window[0] + 1
    se = rows["resid_std"] * math.sqrt(length)
    car = rows[car_column(window)]
    return pd.DataFrame(
        {"event_id": rows["event_id"], "car": car, "low": car - z * se, "high": car + z * se}
    )


def _style_axis(ax, value_axis: str) -> None:
    """Shared look: muted ticks, hairline grid on value_axis ("x" or "y"), no box."""
    ax.tick_params(labelsize=8, colors=TEXT_SECONDARY)
    ax.grid(axis=value_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)


def draw_move_timing(ax, groups: dict[str, pd.DataFrame], fontsize: float = 8) -> None:
    """Two columns per group: mean CAR before day 0 and from day 0 on.

    groups: {label under the pair: that group's abnormal rows, "ok" events
    only}, drawn left to right. The values come from split_car. Every column
    carries its value; the text under each pair adds N and the whole-window
    mean CAR (the two columns added up).
    """
    width = 0.36
    for i, (label, abnormal) in enumerate(groups.items()):
        days = abnormal.columns.astype(int)
        first, last = int(days.min()), int(days.max())
        before, after = split_car(abnormal)
        parts = (
            (-width / 2, before, BEFORE_DAY0, f"Days {day_label(first)} to −1"),
            (width / 2, after, FROM_DAY0, f"Days 0 to {day_label(last)}"),
        )
        for offset, value, color, legend in parts:
            # Only the first pair's columns name the legend entries.
            ax.bar(i + offset, value, width=width * 0.9, color=color, label=legend if i == 0 else None)
            above = value >= 0
            ax.annotate(
                signed(value),
                (i + offset, value),
                xytext=(0, 3 if above else -3),
                textcoords="offset points",
                ha="center",
                va="bottom" if above else "top",
                fontsize=fontsize,
                color=TEXT_PRIMARY,
            )
        whole = f"[{day_label(first)},{day_label(last)}]"
        # Under the pair, below the plot: xycoords mixes data x with axes y.
        under = ax.annotate(
            f"{label}\nN = {len(abnormal)}\n{whole} {signed(before + after)}",
            (i, 0),
            xycoords=("data", "axes fraction"),
            xytext=(0, -6),
            textcoords="offset points",
            ha="center",
            va="top",
            fontsize=fontsize,
            color=TEXT_SECONDARY,
        )
        # tight_layout misjudges text placed partly in axes coordinates, so it
        # ignores this one; the figure leaves room for it instead.
        under.set_in_layout(False)
    ax.axhline(0, color=BASELINE, linewidth=1)
    ax.set_xticks([])
    ax.set_xlim(-0.6, len(groups) - 0.4)
    ax.margins(y=0.18)  # room for the value labels
    ax.yaxis.set_major_formatter(percent_label)
    _style_axis(ax, "y")
    ax.tick_params(labelsize=fontsize)
    ax.spines["bottom"].set_visible(False)
    ax.legend(frameon=False, fontsize=fontsize, loc="upper right")


def _save_with_caption(fig, path: Path, caption: str, bottom_extra_in: float = 0.0) -> None:
    """Wrap caption across the bottom of fig, fit the plot above it, save at 150 dpi.

    tight_layout leaves room for the suptitle by itself (matplotlib 3.3 and
    later), so nothing is reserved at the top. bottom_extra_in adds space
    between the plot and the caption, for text drawn under the plot that
    tight_layout is told to ignore.
    """
    fig_width, fig_height = fig.get_size_inches()
    caption = wrap_caption(caption, fig_width)
    # va="bottom": the caption's last line sits on y = 0.01 and extra lines go up.
    fig.text(0.01, 0.01, caption, fontsize=CAPTION_FONTSIZE, color=TEXT_SECONDARY, va="bottom")
    n_lines = caption.count("\n") + 1
    bottom = (n_lines * CAPTION_LINE_HEIGHT_IN + 0.15 + bottom_extra_in) / fig_height
    fig.tight_layout(rect=(0, bottom, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Saved {path}")


def draw_move_timing_chart(
    groups: dict[str, pd.DataFrame], path: Path, *, title: str, caption: str
) -> None:
    """draw_move_timing on its own figure, with a title and a caption; saved to path."""
    fig, ax = plt.subplots(figsize=(7, 4.4))
    draw_move_timing(ax, groups)
    fig.suptitle(title, fontsize=11, x=0.01, ha="left")
    # The three lines under each pair of columns take about half an inch.
    _save_with_caption(fig, path, caption, bottom_extra_in=0.55)


def draw_event_car_dots(
    results: pd.DataFrame,
    path: Path,
    *,
    window: tuple[int, int],
    group_column: str,
    group_labels: dict[str, str],
    colors: dict[str, str],
    title: str,
    xlabel: str,
    caption: str,
) -> None:
    """One row per event: its CAR over window as a dot with a 95% interval.

    Only "ok" rows of results are drawn. Events are grouped by group_column,
    one block per key of group_labels in that order, under a heading with
    that key's text (the script writes N, mean and t into it). Inside a block
    events run from the largest CAR down, and a thin vertical line marks the
    block's mean CAR. A key with no "ok" row is left out. Each row is named by
    the date in its event_id ("opec_2025_04_03" -> "2025-04-03").

    The interval comes from car_interval, so it shares the per-event t's
    assumptions.
    """
    ran = results[results["status"] == "ok"]
    blocks = [(key, ran[ran[group_column] == key]) for key in group_labels]
    blocks = [(key, rows) for key, rows in blocks if not rows.empty]
    n_rows = sum(len(rows) for _, rows in blocks) + 2 * len(blocks)
    fig, ax = plt.subplots(figsize=(7, 0.2 * n_rows + 1.6))

    y = 0.0
    ticks, tick_labels = [], []
    for key, rows in blocks:
        color = colors[key]
        # The heading sits on its own row, at the left edge of the plot. It is
        # inside the axes, so tight_layout can ignore it (see draw_move_timing).
        heading = ax.annotate(
            group_labels[key],
            (0, y),
            xycoords=("axes fraction", "data"),
            va="center",
            fontsize=8.5,
            fontweight="bold",
            color=TEXT_PRIMARY,
        )
        heading.set_in_layout(False)
        interval = car_interval(rows, window).sort_values("car", ascending=False)
        first_y = y - 1
        for _, event in interval.iterrows():
            y -= 1
            ax.plot([event["low"], event["high"]], [y, y], color=color, linewidth=1.5, zorder=2)
            # A white ring keeps the dot readable where it sits on its bar.
            ax.plot(event["car"], y, "o", color=color, markersize=6, markeredgecolor="white",
                    markeredgewidth=1, zorder=3)  # fmt: skip
            ticks.append(y)
            tick_labels.append(event["event_id"].split("_", 1)[1].replace("_", "-"))
        mean = interval["car"].mean()
        ax.plot([mean, mean], [first_y + 0.5, y - 0.5], color=color, linewidth=1, zorder=1)
        y -= 2  # a blank row, then the next heading

    ax.axvline(0, color=BASELINE, linewidth=1, zorder=0)
    ax.set_yticks(ticks, tick_labels)
    ax.set_ylim(y + 1.5, 0.6)
    ax.xaxis.set_major_formatter(percent_label)
    ax.set_xlabel(xlabel, fontsize=9, color=TEXT_SECONDARY)
    _style_axis(ax, "x")
    ax.tick_params(axis="y", labelsize=7, length=0)
    ax.spines["left"].set_visible(False)
    fig.suptitle(title, fontsize=11, x=0.01, ha="left")
    _save_with_caption(fig, path, caption)


def draw_social_preview(
    groups: dict[str, pd.DataFrame],
    path: Path,
    *,
    title: str,
    subtitle: str,
    footer: str,
    url: str,
    chart_title: str,
) -> None:
    """The 1280 x 640 image GitHub shows when the repository link is shared.

    Text on the left (title, subtitle, footer, url) and draw_move_timing on
    the right with groups. GitHub does not read it from the repository: it
    is uploaded by hand under Settings > General > Social preview.
    """
    fig = plt.figure(figsize=(12.8, 6.4), dpi=100)
    fig.text(0.06, 0.80, title, fontsize=30, fontweight="bold", color=TEXT_PRIMARY, va="top")
    fig.text(0.06, 0.52, subtitle, fontsize=15, color=TEXT_SECONDARY, va="top", linespacing=1.6)
    fig.text(0.06, 0.12, footer, fontsize=12, color=TEXT_SECONDARY)
    fig.text(0.06, 0.06, url, fontsize=12, color=TEXT_PRIMARY)
    ax = fig.add_axes((0.60, 0.30, 0.37, 0.54))
    draw_move_timing(ax, groups, fontsize=10)
    ax.set_title(chart_title, fontsize=12, loc="left", color=TEXT_PRIMARY)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=100)
    plt.close(fig)
    print(f"Saved {path}")
