"""Null calibration: is the test statistic honest when nothing happens?

Run from the project root:

    uv run python scripts/null_calibration.py

Simulates N_EVENTS fake events with NO planted jump (fresh random data for
each, from one fixed master seed) and computes the [-1,+1] and [-5,+5] test
statistics. With no real effect a well-behaved statistic is roughly standard
normal: mean near 0, standard deviation near 1, and about 5% of events beyond
+/-1.96 purely by chance. A much larger share would mean the test "finds"
effects that are not there.

Prints those three numbers for each window, then saves
charts/null_calibration.png: a histogram of the [-1,+1] statistics with the
standard normal curve drawn over it and lines at -1.96 and +1.96.
"""

from pathlib import Path

import matplotlib

# "Agg" draws straight to a file, so no chart window pops up.
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import norm

from event_study.simulate import (
    NOISE_STD,
    NULL_MASTER_SEED,
    TRUE_BETA,
    null_test_stats,
)
from event_study.windows import (
    DEFAULT_EST_LENGTH,
    DEFAULT_EVENT_WINDOWS,
    DEFAULT_GAP,
    window_label,
)

N_EVENTS = 1000
CRITICAL = 1.96  # two-sided 5% cutoff for a standard normal
HIST_WINDOW = (-1, 1)
BIN_WIDTH = 0.25
OUTPUT = Path("charts") / "null_calibration.png"

# Colors from the same palette as plot_prices.py.
BARS = "#2a78d6"
NORMAL_CURVE = "#eb6834"
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e0"
CUTOFF_LINE = "#52514e"


def share_beyond(stats, cutoff: float = CRITICAL) -> float:
    """Fraction of statistics with absolute value above cutoff."""
    return float((stats.abs() > cutoff).mean())


def plot_histogram(ax, stats) -> None:
    """Histogram of statistics (counts) with the expected standard normal curve."""
    # Bin edges cover every value, so no statistic falls off the ends.
    edges = np.arange(np.floor(stats.min()), np.ceil(stats.max()) + BIN_WIDTH, BIN_WIDTH)
    ax.hist(stats, bins=edges, rwidth=0.9, color=BARS, label="Simulated events")

    # The curve shows how many events per bin a perfect standard normal would
    # give: total events x bin width x normal density at that point.
    x = np.linspace(edges[0], edges[-1], 400)
    expected = len(stats) * BIN_WIDTH * norm.pdf(x)
    ax.plot(x, expected, color=NORMAL_CURVE, linewidth=2, label="Standard normal")

    for cutoff in (-CRITICAL, CRITICAL):
        ax.axvline(cutoff, color=CUTOFF_LINE, linewidth=1)
        # "−" (Unicode minus) matches the minus sign matplotlib uses on the axis.
        ax.annotate(
            f"{cutoff:+.2f}".replace("-", "−"), xy=(cutoff, 1), xycoords=("data", "axes fraction"),
            xytext=(4 if cutoff > 0 else -4, -2), textcoords="offset points",
            ha="left" if cutoff > 0 else "right", va="top", color=TEXT_SECONDARY,
        )

    label = window_label(HIST_WINDOW)
    ax.set_title(
        f"Null calibration, {label} test statistic: "
        f"{share_beyond(stats):.1%} beyond ±{CRITICAL} (5% expected)"
    )
    ax.set_xlabel(f"{label} test statistic")
    ax.set_ylabel(f"Number of events (of {len(stats)})")
    # Symmetric x-axis, one unit wider than the most extreme value, so 0 sits
    # in the middle and the legend has room left of the -1.96 line.
    limit = np.ceil(stats.abs().max()) + 1
    ax.set_xlim(-limit, limit)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper left", frameon=False)


def main() -> None:
    # 1. Simulate. Estimation length, gap and windows are the project defaults.
    stats = null_test_stats(
        N_EVENTS, NULL_MASTER_SEED, DEFAULT_EST_LENGTH, DEFAULT_GAP, DEFAULT_EVENT_WINDOWS
    )

    # 2. Print the summary for each window.
    print(f"{N_EVENTS} simulated events, no planted effect, master seed {NULL_MASTER_SEED}")
    print(f"{'window':<9} {'mean':>7} {'std':>6} {'share |stat| > 1.96':>21}")
    for window in DEFAULT_EVENT_WINDOWS:
        column = stats[window_label(window)]
        print(
            f"{window_label(window):<9} {column.mean():>+7.3f} {column.std():>6.3f} "
            f"{share_beyond(column):>21.1%}"
        )

    # 3. Draw the histogram for one window.
    fig, ax = plt.subplots(figsize=(10, 5.5))
    plot_histogram(ax, stats[window_label(HIST_WINDOW)])
    caption = (
        f"Simulated data (master seed {NULL_MASTER_SEED}), not real prices. "
        f"Each event: {DEFAULT_EST_LENGTH}-day estimation window ending on day -{DEFAULT_GAP}, "
        f"true beta {TRUE_BETA}, noise std {NOISE_STD:.0%}."
    )
    fig.text(0.01, 0.01, caption, fontsize=8, color=TEXT_SECONDARY)

    # 4. Save, creating charts/ if it does not exist yet.
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0.04, 1, 1))  # leave room at the bottom for the caption
    fig.savefig(OUTPUT, dpi=150)
    print(f"Saved {OUTPUT}")


if __name__ == "__main__":
    main()
