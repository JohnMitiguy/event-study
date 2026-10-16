"""How well do the across-event tests work? Simulated data only.

Run from the project root:

    uv run python scripts/across_event_demo.py

Takes about two minutes. Each fake event follows event_study.simulate's
model (true beta TRUE_BETA, benchmark std BENCHMARK_STD, residual std
NOISE_STD, normal noise, day 0 at row DAY0_POSITION), with the project's
default estimation window, and the [-1,+1] event window throughout.

(a) Null calibration: no true effect. For N = 10, 30 and 60 events, 2000
    repeated samples each; how often does each test reject at 5%? A
    well-calibrated test rejects about 5% of the time.
(b) Same, but the residual std is doubled on every event-window day for
    every event (the event makes the stock more volatile, still with no
    average effect). A "naive pooled z" (Patell-style: assumes each SCAR has
    std 1, as if volatility did not change) is added as a reference to show
    what over-rejecting looks like. It is not in aggregate.py on purpose.
(c) Power: a true abnormal return of 0% to 3% planted on day 0 of every
    event; rejection rate for N = 15, 30 and 60.

Before the simulations it prints a quick formula-based count of the events
needed for 80% power at a 1% average abnormal return and 1% daily noise,
with its assumptions (see events_needed). It is an illustration, not a
recorded target.

Saves charts/across_event_null.png and charts/power_curve.png and prints the
numbers behind both.

Speed: running 2000 x 60 events through run_events one by one would take
hours, so simulate_cars below does the same steps on numpy arrays, many
events at once. Before anything else, main() checks that it reproduces
simulate.null_test_stats to 1e-9 on the same seed, so it cannot drift from
the real pipeline unnoticed.

Seeds: every scenario with N events uses a generator seeded with
(SEED, N), so (a), (b) and every effect size in (c) see the same random
draws and differ only in what was changed. This makes the comparisons less
noisy; each rate is still from N_REPS independent samples.
"""

import math
from pathlib import Path

import matplotlib

# "Agg" draws straight to a file, so no chart window pops up.
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.power import TTestPower

from event_study.aggregate import TEST_NAMES, compute_tests
from event_study.simulate import (
    BENCHMARK_STD,
    DAY0_POSITION,
    N_DAYS,
    NOISE_STD,
    NULL_MASTER_SEED,
    TRUE_ALPHA,
    TRUE_BETA,
    null_test_stats,
)
from event_study.windows import DEFAULT_EST_LENGTH, DEFAULT_GAP, window_label

WINDOW = (-1, 1)
EST_LENGTH = DEFAULT_EST_LENGTH
GAP = DEFAULT_GAP
N_REPS = 2000
LEVEL = 0.05  # reject when p < LEVEL
NULL_SIZES = (10, 30, 60)
POWER_SIZES = (15, 30, 60)
EVENT_VOL_MULTIPLIER = 2.0
# 0%, 0.25%, ..., 3%, as decimals.
EFFECTS = np.round(np.arange(0, 13) * 0.0025, 4)
SEED = 2027
CHECK_EVENTS = 50  # events in the check against null_test_stats
# Assumptions for the formula-based events-needed count (events_needed).
TARGET_POWER = 0.80
ASSUMED_EFFECT = 0.01  # true average abnormal return, all of it on day 0
ASSUMED_DAILY_STD = 0.01  # residual (abnormal-return) std per day
SENSITIVITY_WINDOWS = ((0, 0), (-5, 5))

NAIVE = "naive_z"
LABELS = {
    "cross_sectional_t": "Cross-sectional t",
    "bmp": "BMP standardized",
    "wilcoxon": "Wilcoxon signed-rank",
    "sign": "Sign test",
    NAIVE: "Naive pooled z (reference only)",
}
# First four slots of the colorblind-checked default palette (as in
# plot_prices.py), plus a marker shape each so color is not the only cue.
STYLES = {
    "cross_sectional_t": {"color": "#2a78d6", "marker": "o"},
    "bmp": {"color": "#eb6834", "marker": "s"},
    "wilcoxon": {"color": "#1baf7a", "marker": "^"},
    "sign": {"color": "#eda100", "marker": "D"},
    NAIVE: {"color": "#898781", "marker": "x", "linestyle": "--"},
}
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e0"
REFERENCE_LINE = "#52514e"
BAND = "#e6e5e0"
CHARTS = Path("charts")


def simulate_cars(
    rng: np.random.Generator, n_events: int, jump: float = 0.0, event_vol: float = 1.0
) -> tuple[np.ndarray, np.ndarray]:
    """(CARs, SCARs) over WINDOW for n_events fake events, one array entry each.

    Same model and draw order as simulate.fake_returns (per event: N_DAYS
    benchmark draws, then N_DAYS noise draws), then the market-model fit
    and car_test written out with numpy, one row per event:

        beta = sum((x - mean x)(y - mean y)) / sum((x - mean x)^2)
        alpha = mean y - beta * mean x
        resid_std = sqrt(sum(residual^2) / (EST_LENGTH - 2))
        CAR = sum over the window of (y - alpha - beta * x)
        SCAR = CAR / (resid_std * sqrt(L))

    jump is added to the security on day 0. event_vol multiplies the noise
    on every event-window day.
    """
    draws = rng.standard_normal((n_events, 2, N_DAYS))
    benchmark = BENCHMARK_STD * draws[:, 0]
    noise = NOISE_STD * draws[:, 1]

    start, end = WINDOW
    window_rows = np.arange(DAY0_POSITION + start, DAY0_POSITION + end + 1)
    noise[:, window_rows] *= event_vol
    security = TRUE_ALPHA + TRUE_BETA * benchmark + noise
    security[:, DAY0_POSITION] += jump

    # Estimation rows, as in windows.slice_windows.
    est = slice(DAY0_POSITION - GAP - EST_LENGTH + 1, DAY0_POSITION - GAP + 1)
    x, y = benchmark[:, est], security[:, est]
    # keepdims=True keeps one value per row as a column, so it subtracts row by row.
    x_dev = x - x.mean(axis=1, keepdims=True)
    y_dev = y - y.mean(axis=1, keepdims=True)
    beta = (x_dev * y_dev).sum(axis=1) / (x_dev**2).sum(axis=1)
    alpha = y.mean(axis=1) - beta * x.mean(axis=1)
    # [:, None] turns one value per event into a column, again for row-by-row math.
    resid = y - alpha[:, None] - beta[:, None] * x
    resid_std = np.sqrt((resid**2).sum(axis=1) / (EST_LENGTH - 2))

    abnormal = security[:, window_rows] - alpha[:, None] - beta[:, None] * benchmark[:, window_rows]
    cars = abnormal.sum(axis=1)
    scars = cars / (resid_std * np.sqrt(len(window_rows)))
    return cars, scars


def events_needed(window: tuple[int, int]) -> int:
    """Ok events needed for TARGET_POWER at LEVEL, from a formula, not simulation.

    Assumes every event has a true abnormal return of ASSUMED_EFFECT on day 0
    and residual noise with std ASSUMED_DAILY_STD per day, independent across
    days. A CAR over L days then has mean ASSUMED_EFFECT and std
    ASSUMED_DAILY_STD * sqrt(L), so longer windows add noise but no effect.
    The test is the two-sided one-sample t-test on the CARs (the
    cross-sectional t, the primary test in DECISIONS.md).

    Ignores estimation error in alpha and beta, effects that differ from
    event to event, and events that share days. Each of these pushes the
    real number up.
    """
    start, end = window
    car_std = ASSUMED_DAILY_STD * math.sqrt(end - start + 1)
    # effect_size is the true mean CAR divided by the CAR std. solve_power
    # uses the exact t distribution and returns a fractional N; round up.
    n = TTestPower().solve_power(
        effect_size=ASSUMED_EFFECT / car_std, alpha=LEVEL, power=TARGET_POWER,
        alternative="two-sided",
    )
    return math.ceil(n)


def print_events_needed() -> None:
    """The events_needed count for WINDOW, its assumptions, and other windows for comparison."""
    print(f"Events needed for {TARGET_POWER:.0%} power (formula, not simulation; an illustration, "
          "not a recorded target):")
    print(f"  Assumes a true abnormal return of {ASSUMED_EFFECT:.0%} on day 0 of every event, "
          f"residual std {ASSUMED_DAILY_STD:.0%}/day independent across days,")
    print(f"  and a two-sided cross-sectional t-test at {LEVEL:.0%}. Ignores estimation error, "
          "effects that vary between events and events that share days;")
    print("  each pushes the number up.")
    print(f"  {window_label(WINDOW)} window: {events_needed(WINDOW)} ok events.")
    others = ", ".join(f"{window_label(w)} needs {events_needed(w)}" for w in SENSITIVITY_WINDOWS)
    print(f"  Same assumptions, other windows: {others}.\n")


def check_against_pipeline() -> None:
    """Stop if simulate_cars disagrees with the real pipeline on the same seed."""
    _, scars = simulate_cars(np.random.default_rng(NULL_MASTER_SEED), CHECK_EVENTS)
    expected = null_test_stats(CHECK_EVENTS, NULL_MASTER_SEED, EST_LENGTH, GAP, (WINDOW,))
    np.testing.assert_allclose(scars, expected[window_label(WINDOW)], rtol=1e-9)
    print(f"Check passed: simulate_cars matches null_test_stats on {CHECK_EVENTS} events.\n")


def naive_z_p_value(scars: np.ndarray) -> float:
    """Two-sided p of sum(SCAR) / sqrt(N) against a standard normal.

    Right only if every SCAR has std 1, i.e. the event window is exactly as
    volatile as the estimation window. Reference for scenario (b) only.
    """
    z = scars.sum() / np.sqrt(len(scars))
    return float(2 * stats.norm.sf(abs(z)))


def rejection_rates(n_events: int, jump: float = 0.0, event_vol: float = 1.0) -> pd.Series:
    """Share of N_REPS samples in which each test rejects at LEVEL."""
    rng = np.random.default_rng([SEED, n_events])
    p_values = []
    for _ in range(N_REPS):
        cars, scars = simulate_cars(rng, n_events, jump, event_vol)
        p = compute_tests(cars, scars)["p_value"]
        p_values.append([*p, naive_z_p_value(scars)])
    p_table = pd.DataFrame(p_values, columns=[*TEST_NAMES, NAIVE])
    return (p_table < LEVEL).mean()


def sign_test_exact_size(n_events: int) -> float:
    """Exact chance the sign test rejects at LEVEL when nothing happens.

    Under H0 the number of positive CARs is binomial(N, 1/2); add up the
    probability of every count whose p-value is below LEVEL. Below 5%
    because the binomial has no count with p exactly 5%.
    """
    counts = np.arange(n_events + 1)
    rejects = [stats.binomtest(k, n_events, 0.5).pvalue < LEVEL for k in counts]
    return float(stats.binom.pmf(counts[rejects], n_events, 0.5).sum())


def monte_carlo_band(rate: float = LEVEL) -> float:
    """1.96 x the standard error of a rejection rate estimated from N_REPS samples.

    A test whose true rate is `rate` lands within +/- this about 95% of the time.
    """
    return 1.96 * np.sqrt(rate * (1 - rate) / N_REPS)


def print_rates(title: str, table: pd.DataFrame, extra: pd.Series | None = None) -> None:
    """Rejection rates in percent, one row per N, one column per test."""
    print(title)
    shown = (table * 100).rename(columns=LABELS).round(1)
    if extra is not None:
        shown["Sign test, exact expected"] = (extra * 100).round(1)
    print(shown.to_string())
    print()


def style_axis(ax) -> None:
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)


def add_caption(fig, text: str) -> None:
    fig.text(0.01, 0.01, text, fontsize=8, color=TEXT_SECONDARY)


def caption_text(extra: str) -> str:
    """Two-line caption: how the data was made, then a chart-specific note."""
    return (
        f"Simulated data, not real prices. {N_REPS} samples per point; normal noise, residual std "
        f"{NOISE_STD:.0%}/day, true beta {TRUE_BETA}, {EST_LENGTH}-day estimation window ending "
        f"on day -{GAP}, window {window_label(WINDOW)}.\n"
        f"Cross-sectional t and BMP lines overlap almost exactly. {extra}"
    )


def plot_null(null: pd.DataFrame, vol: pd.DataFrame, path: Path) -> None:
    """Rejection rate vs N, normal null on the left, doubled volatility on the right."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), sharey=True)
    band = monte_carlo_band()
    panels = (
        (axes[0], null, "(a) No effect, normal volatility"),
        (axes[1], vol, f"(b) No effect, event-window volatility x{EVENT_VOL_MULTIPLIER:g}"),
    )
    for ax, table, title in panels:
        ax.axhspan((LEVEL - band) * 100, (LEVEL + band) * 100, color=BAND, zorder=0)
        ax.axhline(LEVEL * 100, color=REFERENCE_LINE, linewidth=1)
        for name in table.columns:
            ax.plot(table.index, table[name] * 100, linewidth=2, markersize=8,
                    label=LABELS[name], **STYLES[name])
        ax.set_title(title, loc="left")
        ax.set_xticks(table.index)
        ax.set_xlabel("Number of events (N)")
        style_axis(ax)
    axes[0].set_ylabel("Rejection rate at 5% (% of samples)")
    axes[0].legend(loc="upper left", frameon=False)
    # After all lines are drawn: the axes are shared, so setting a limit earlier
    # would freeze the top at panel (a)'s range and cut off panel (b).
    axes[0].set_ylim(bottom=0)
    fig.suptitle("Across-event tests with no true effect: how often do they reject?")
    add_caption(fig, caption_text(
        f"Gray band: 5% +/- {band:.1%}, the range a correctly sized test lands in 95% of the time."
    ))
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_power(power: dict[int, pd.DataFrame], path: Path) -> None:
    """Rejection rate vs true day-0 abnormal return, one panel per N."""
    fig, axes = plt.subplots(1, len(power), figsize=(14, 5.5), sharey=True)
    for ax, (n_events, table) in zip(axes, power.items(), strict=True):
        ax.axhline(80, color=REFERENCE_LINE, linewidth=1, linestyle=":")
        ax.axhline(LEVEL * 100, color=REFERENCE_LINE, linewidth=1)
        ax.axvline(1.0, color=REFERENCE_LINE, linewidth=1, linestyle=":")
        for name in table.columns:
            ax.plot(table.index * 100, table[name] * 100, linewidth=2, markersize=6,
                    label=LABELS[name], **STYLES[name])
        ax.set_title(f"N = {n_events} events", loc="left")
        ax.set_xlabel("True abnormal return on day 0 (%)")
        ax.set_ylim(0, 102)
        style_axis(ax)
    axes[0].set_ylabel("Rejection rate at 5% (% of samples)")
    axes[0].legend(loc="lower right", frameon=False)
    fig.suptitle(
        f"Power of the across-event tests, {window_label(WINDOW)} window "
        "(dotted: 80% power and a 1% effect)"
    )
    add_caption(fig, caption_text("The same true effect is planted on day 0 of every event."))
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    print_events_needed()
    check_against_pipeline()
    print(f"{N_REPS} simulated samples per row; rejection rates in % at the 5% level.")
    print(f"A correctly sized test lands within 5% +/- {monte_carlo_band():.1%} about 95% of the time.\n")

    # (a) and (b): one row per N, one column per test.
    null = pd.DataFrame({n: rejection_rates(n) for n in NULL_SIZES}).T
    vol = pd.DataFrame(
        {n: rejection_rates(n, event_vol=EVENT_VOL_MULTIPLIER) for n in NULL_SIZES}
    ).T
    exact_sign = pd.Series({n: sign_test_exact_size(n) for n in NULL_SIZES})
    print_rates("(a) Null calibration, no effect:", null, exact_sign)
    print_rates(
        f"(b) No effect, residual std x{EVENT_VOL_MULTIPLIER:g} on event-window days:", vol, exact_sign
    )

    # (c): for each N, one row per effect size. The naive z is left out:
    # it only matters for (b).
    power = {}
    for n in POWER_SIZES:
        table = pd.DataFrame({jump: rejection_rates(n, jump=jump) for jump in EFFECTS}).T
        table = table[list(TEST_NAMES)]
        table.index.name = "true day-0 AR"
        power[n] = table
        shown = (table * 100).round(1).rename(columns=LABELS)
        shown.index = [f"{jump:.2%}" for jump in shown.index]
        print(f"(c) Power, N = {n}:")
        print(shown.to_string())
        print()

    CHARTS.mkdir(parents=True, exist_ok=True)
    null_path, power_path = CHARTS / "across_event_null.png", CHARTS / "power_curve.png"
    plot_null(null, vol, null_path)
    plot_power(power, power_path)
    print(f"Saved {null_path} and {power_path}")


if __name__ == "__main__":
    main()
