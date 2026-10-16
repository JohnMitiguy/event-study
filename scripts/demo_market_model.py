"""Demo the market model on fake data with a known +4% event on day 0.

Run from the project root:

    uv run python scripts/demo_market_model.py

Prints the fitted beta, residual std, and CAR / test statistic for each event
window, then saves charts/market_model_demo.png:
- left: estimation-window days with the fitted line (estimated vs true beta)
- right: abnormal returns for days -5 to +5, the planted day highlighted

The data is simulated (see event_study.simulate); nothing here is real prices.
"""

from pathlib import Path

import matplotlib

# "Agg" draws straight to a file, so no chart window pops up.
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import PercentFormatter

from event_study.market_model import car_test, fit_market_model
from event_study.simulate import DEMO_SEED, PLANTED_JUMP, TRUE_BETA, planted_event, window_label
from event_study.windows import (
    DEFAULT_EST_LENGTH,
    DEFAULT_EVENT_WINDOWS,
    DEFAULT_GAP,
    slice_windows,
)

OUTPUT = Path("charts") / "market_model_demo.png"

# Window drawn in the bar chart. It must be one of DEFAULT_EVENT_WINDOWS.
BAR_WINDOW = (-5, 5)

# Colors from the same palette as plot_prices.py.
ACCENT = "#2a78d6"  # points, and the planted day 0 bar
FIT_LINE = "#eb6834"
OTHER_DAYS = "#c3c2b7"  # neutral gray for ordinary days
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e0"
BASELINE = "#c3c2b7"


def style_axes(ax) -> None:
    """Recessive grid and axes, shared by both panels."""
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))


def plot_fit(ax, sec_est, bench_est, fit) -> None:
    """Scatter of estimation-window days with the fitted line."""
    ax.scatter(
        bench_est, sec_est, s=22, color=ACCENT, edgecolors="white", linewidths=0.8,
        label=f"Estimation-window days (n={fit.n})",
    )
    # A straight line only needs its two ends: the smallest and largest x.
    x = np.array([bench_est.min(), bench_est.max()])
    ax.plot(x, fit.alpha + fit.beta * x, color=FIT_LINE, linewidth=2, label="Fitted line")
    ax.set_title(f"Estimated β = {fit.beta:.2f} (true β = {TRUE_BETA})")
    ax.set_xlabel("Benchmark daily return")
    ax.set_ylabel("Security daily return")
    style_axes(ax)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.legend(loc="upper left", frameon=False)


def plot_abnormal(ax, abnormal, day0) -> None:
    """Bars of abnormal returns by event day, with day 0 highlighted."""
    start, end = BAR_WINDOW
    # The abnormal returns are indexed by date; label them by event day instead.
    event_days = np.arange(start, end + 1)
    colors = [ACCENT if day == 0 else OTHER_DAYS for day in event_days]
    ax.bar(event_days, abnormal.to_numpy(), width=0.35, color=colors)
    ax.axhline(0, color=BASELINE, linewidth=1)

    # Label only the planted day, just above (or below) its bar tip.
    ar0 = abnormal.loc[day0]
    ax.annotate(
        f"{ar0:+.1%}", xy=(0, ar0), xytext=(0, 4 if ar0 >= 0 else -12),
        textcoords="offset points", ha="center", color=TEXT_SECONDARY,
    )
    ax.set_title(f"Abnormal returns, days {start} to +{end} (+{PLANTED_JUMP:.0%} planted on day 0)")
    ax.set_xlabel(f"Event day (day 0 = {day0.date()})")
    ax.set_ylabel("Abnormal return")
    ax.set_xticks(event_days)
    style_axes(ax)
    # Event days are whole numbers, not percentages: -5 ... 0 ... +5.
    # "−" (Unicode minus) matches the minus sign matplotlib uses on the y-axis.
    ax.xaxis.set_major_formatter(lambda x, _: f"{x:+.0f}".replace("-", "−") if x != 0 else "0")


def main() -> None:
    # 1. Fake data with a +4% jump on day 0.
    security, benchmark, day0 = planted_event()

    # 2. Cut the windows. Both series have the same dates, so the same day0
    #    and window lengths pick out the same rows in each.
    sec_est, sec_events = slice_windows(
        security, day0, DEFAULT_EST_LENGTH, DEFAULT_GAP, DEFAULT_EVENT_WINDOWS
    )
    bench_est, bench_events = slice_windows(
        benchmark, day0, DEFAULT_EST_LENGTH, DEFAULT_GAP, DEFAULT_EVENT_WINDOWS
    )

    # 3. Fit on the estimation window, then test each event window.
    fit = fit_market_model(sec_est, bench_est, min_obs=DEFAULT_EST_LENGTH)
    results = {w: car_test(fit, sec_events[w], bench_events[w]) for w in DEFAULT_EVENT_WINDOWS}

    # 4. Print the numbers.
    print(f"Simulated data, seed {DEMO_SEED}. True beta {TRUE_BETA}, true alpha 0.")
    print(f"Planted {PLANTED_JUMP:+.1%} on day 0 = {day0.date()}.")
    print(
        f"Estimation window: {fit.n} days, "
        f"{sec_est.index[0].date()} to {sec_est.index[-1].date()}"
    )
    print(f"beta          {fit.beta:.3f}")
    print(f"residual std  {fit.resid_std:.3%}")
    print(f"{'window':<9} {'days':>4} {'CAR':>8} {'test stat':>10}")
    for window, result in results.items():
        print(
            f"{window_label(window):<9} {result.n_days:>4} "
            f"{result.car:>+8.2%} {result.test_stat:>10.2f}"
        )

    # 5. Draw both panels.
    fig, (left, right) = plt.subplots(1, 2, figsize=(13, 5.5))
    plot_fit(left, sec_est, bench_est, fit)
    plot_abnormal(right, results[BAR_WINDOW].abnormal, day0)
    caption = (
        f"Simulated data (seed {DEMO_SEED}), not real prices. Benchmark ~ Normal(0, 1%); "
        f"security = {TRUE_BETA} × benchmark + Normal(0, 1%) noise."
    )
    fig.text(0.01, 0.01, caption, fontsize=8, color=TEXT_SECONDARY)

    # 6. Save, creating charts/ if it does not exist yet.
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0.04, 1, 1))  # leave room at the bottom for the caption
    fig.savefig(OUTPUT, dpi=150)
    print(f"Saved {OUTPUT}")


if __name__ == "__main__":
    main()
