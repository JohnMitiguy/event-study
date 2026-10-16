"""Tests for the market model.

Statistics used in the comments below:
- A standard error (SE) is how much an estimate would wobble if we drew new
  random data and estimated again. For roughly normal estimates, about 99.7%
  land within 3 SE of the true value, so "within 3 SE" is a check a correct
  implementation fails only about 3 times in 1000 seeds.
- The data here is simulated with fixed seeds (event_study.simulate), so each
  test is deterministic: it passes or fails the same way on every run. The
  tolerances say how far off a correct implementation could plausibly be.
"""

import numpy as np
import pandas as pd
import pytest

from event_study.errors import EventDataError
from event_study.market_model import MarketModelFit, car_test, fit_market_model
from event_study.simulate import (
    NOISE_STD,
    NULL_MASTER_SEED,
    PLANTED_JUMP,
    TRUE_ALPHA,
    TRUE_BETA,
    null_test_stats,
    planted_event,
)
from event_study.windows import (
    DEFAULT_EST_LENGTH,
    DEFAULT_EVENT_WINDOWS,
    DEFAULT_GAP,
    slice_windows,
    window_label,
)


@pytest.fixture(scope="module")
def demo():
    """The same data and fit as scripts/demo_market_model.py (seed 42, +4% on day 0).

    scope="module" builds it once and shares it across the tests in this file.
    """
    security, benchmark, day0 = planted_event()
    sec_est, sec_events = slice_windows(
        security, day0, DEFAULT_EST_LENGTH, DEFAULT_GAP, DEFAULT_EVENT_WINDOWS
    )
    bench_est, bench_events = slice_windows(
        benchmark, day0, DEFAULT_EST_LENGTH, DEFAULT_GAP, DEFAULT_EVENT_WINDOWS
    )
    fit = fit_market_model(sec_est, bench_est, min_obs=DEFAULT_EST_LENGTH)
    return {
        "security": security,
        "benchmark": benchmark,
        "day0": day0,
        "sec_est": sec_est,
        "bench_est": bench_est,
        "sec_events": sec_events,
        "bench_events": bench_events,
        "fit": fit,
    }


# ---------------------------------------------------------------------------
# The fit
# ---------------------------------------------------------------------------


def test_beta_within_three_standard_errors(demo):
    fit, x = demo["fit"], demo["bench_est"].to_numpy()

    # SE of beta = resid_std / sqrt(sum of (x - mean x)^2).
    # In words: beta is learned from how the security moves when the
    # benchmark moves. More benchmark movement (bigger spread in x) and less
    # noise (smaller resid_std) pin it down more precisely.
    # Back of the envelope: 1% noise / (1% benchmark std * sqrt(120 days))
    # = 1 / sqrt(120) ~= 0.09. With seed 42 it is about 0.11: the benchmark
    # happened to be calmer than its true 1% in this window (sample std
    # ~0.86%), so beta is pinned down a little less precisely.
    se_beta = fit.resid_std / np.sqrt(((x - x.mean()) ** 2).sum())
    assert 0.07 < se_beta < 0.12, "SE should be near the ~0.09 back-of-envelope figure"

    # 3 SE ~= 0.34 here, so beta must land between about 0.86 and 1.54.
    # (Estimated beta is 1.18, only 0.2 SE from the truth.)
    assert abs(fit.beta - TRUE_BETA) < 3 * se_beta


def test_fit_matches_hand_formulas(demo):
    # The 3-SE check above is loose (+/-0.27): a bug that returned beta = 1.0
    # would still pass it. So also recompute everything with the textbook
    # one-variable regression formulas and require an essentially exact match.
    fit = demo["fit"]
    x = demo["bench_est"].to_numpy()
    y = demo["sec_est"].to_numpy()
    n = len(x)

    # beta = how x and y move together (covariance), per unit of x's own
    # variation (variance). alpha makes the line pass through the means.
    beta = np.cov(x, y, ddof=1)[0, 1] / np.var(x, ddof=1)
    alpha = y.mean() - beta * x.mean()
    residuals = y - (alpha + beta * x)
    # n - 2: dividing by n - 1 instead would be about 0.4% larger and fail.
    resid_std = np.sqrt((residuals**2).sum() / (n - 2))

    assert fit.n == DEFAULT_EST_LENGTH == n
    assert fit.beta == pytest.approx(beta, rel=1e-9)
    assert fit.alpha == pytest.approx(alpha, rel=1e-9, abs=1e-12)
    assert fit.resid_std == pytest.approx(resid_std, rel=1e-9)


# ---------------------------------------------------------------------------
# Abnormal returns, CAR and the test statistic
# ---------------------------------------------------------------------------


def test_day0_abnormal_return_near_planted_jump(demo):
    fit, day0 = demo["fit"], demo["day0"]
    security, benchmark = demo["security"], demo["benchmark"]
    window = (-5, 5)
    abnormal = car_test(fit, demo["sec_events"][window], demo["bench_events"][window]).abnormal
    ar0 = abnormal.loc[day0]

    # Loose check. Day 0's abnormal return = the planted 4% + that day's
    # ordinary noise (std 1%) + a small error from the estimated alpha and
    # beta. The noise dominates, so allow 3 noise standard deviations: 1%-7%.
    assert abs(ar0 - PLANTED_JUMP) < 3 * NOISE_STD

    # Tight check. Compute day 0's abnormal return with the TRUE alpha and
    # beta. That contains the same jump and the same noise, so the only
    # difference from ar0 is the estimation error in alpha and beta.
    true_ar0 = security[day0] - (TRUE_ALPHA + TRUE_BETA * benchmark[day0])
    # SE of that difference = resid_std * sqrt(1/n + (x0 - mean x)^2 / sum (x - mean x)^2):
    # the 1/n part is alpha's uncertainty, the second part is beta's
    # uncertainty scaled by how far that day's benchmark move is from average.
    # It comes to about 0.1%, a tenth of a normal day's noise. This is the
    # error the test statistic ignores.
    x = demo["bench_est"].to_numpy()
    x0 = benchmark[day0]
    se_prediction = fit.resid_std * np.sqrt(
        1 / fit.n + (x0 - x.mean()) ** 2 / ((x - x.mean()) ** 2).sum()
    )
    assert abs(ar0 - true_ar0) < 3 * se_prediction

    # The planted day stands out as the largest abnormal return in the window.
    assert abnormal.idxmax() == day0


def test_car_and_test_stat_by_hand():
    # A fit built directly, so this checks only the event-window arithmetic.
    fit = MarketModelFit(alpha=0.001, beta=1.5, resid_std=0.01, n=100)
    dates = pd.bdate_range("2024-03-04", periods=3)
    benchmark = pd.Series([0.01, -0.02, 0.0], index=dates)
    security = pd.Series([0.02, -0.03, 0.005], index=dates)

    # predicted = 0.001 + 1.5 * benchmark   ->  0.016, -0.029, 0.001
    # abnormal  = security - predicted      ->  0.004, -0.001, 0.004
    # CAR       = 0.004 - 0.001 + 0.004     =   0.007
    # test stat = 0.007 / (0.01 * sqrt(3))  ~=  0.4041
    result = car_test(fit, security, benchmark)
    assert result.abnormal.to_numpy() == pytest.approx([0.004, -0.001, 0.004])
    assert list(result.abnormal.index) == list(dates)
    assert result.car == pytest.approx(0.007)
    assert result.test_stat == pytest.approx(0.007 / (0.01 * np.sqrt(3)))
    assert result.n_days == 3


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


@pytest.fixture
def est_pair(demo):
    """Fresh copies of the estimation-window slices, safe to modify."""
    return demo["sec_est"].copy(), demo["bench_est"].copy()


def test_fit_mismatched_dates_raises(est_pair):
    security, benchmark = est_pair
    with pytest.raises(ValueError, match="1 date\\(s\\) only in security"):
        fit_market_model(security, benchmark.iloc[:-1], min_obs=3)


def test_fit_same_dates_different_order_raises(est_pair):
    security, benchmark = est_pair
    with pytest.raises(ValueError, match="different order"):
        fit_market_model(security, benchmark.iloc[::-1], min_obs=3)


@pytest.mark.parametrize("which", ["security", "benchmark"])
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_fit_nan_or_inf_raises(est_pair, which, bad):
    security, benchmark = est_pair
    target = security if which == "security" else benchmark
    target.iloc[5] = bad
    with pytest.raises(ValueError, match=f"{which} has 1 NaN or infinite"):
        fit_market_model(security, benchmark, min_obs=3)


def test_fit_fewer_than_min_obs_raises(est_pair):
    security, benchmark = est_pair
    with pytest.raises(ValueError, match="only 119 observation"):
        fit_market_model(security.iloc[1:], benchmark.iloc[1:], min_obs=DEFAULT_EST_LENGTH)


def test_min_obs_below_hard_floor_raises(est_pair):
    # Two days leave n - 2 = 0 degrees of freedom: no residual std is possible.
    security, benchmark = est_pair
    with pytest.raises(ValueError, match="min_obs must be at least 3"):
        fit_market_model(security.iloc[:2], benchmark.iloc[:2], min_obs=2)


def test_constant_benchmark_raises(est_pair):
    security, benchmark = est_pair
    benchmark[:] = 0.001
    with pytest.raises(ValueError, match="same every day"):
        fit_market_model(security, benchmark, min_obs=3)


def test_event_window_mismatched_dates_raises(demo):
    window = (-1, 1)
    with pytest.raises(ValueError, match="share the same dates"):
        car_test(demo["fit"], demo["sec_events"][window], demo["bench_events"][(-5, 5)])


def test_event_window_nan_raises(demo):
    window = (-1, 1)
    security = demo["sec_events"][window].copy()
    security.iloc[1] = np.nan
    with pytest.raises(ValueError, match="security has 1 NaN or infinite"):
        car_test(demo["fit"], security, demo["bench_events"][window])


def test_empty_event_window_raises(demo):
    window = (-1, 1)
    with pytest.raises(ValueError, match="empty"):
        car_test(demo["fit"], demo["sec_events"][window].iloc[:0], demo["bench_events"][window].iloc[:0])


# ---------------------------------------------------------------------------
# Null calibration: 1000 fake events with no effect
#
# If nothing happened, the test statistic should behave like a standard
# normal: centered on 0, spread of 1, and |stat| > 1.96 about 5% of the time.
# If it were too spread out, the test would "find" effects in pure noise.
#
# Tolerances are fixed in advance (not tuned to these results). For scale,
# with 1000 events the sampling error is about 0.03 for the mean, 0.02 for
# the standard deviation, and 0.7 percentage points for the 5% share. The
# standard deviation band reaches up to 1.15 because ignoring the error in
# alpha and beta is expected to push it slightly above 1, more so for the
# longer window.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def null_stats():
    """Test statistics for 1000 no-effect events (built once, ~2 seconds)."""
    return null_test_stats(
        1000, NULL_MASTER_SEED, DEFAULT_EST_LENGTH, DEFAULT_GAP, DEFAULT_EVENT_WINDOWS
    )


@pytest.mark.parametrize("window", DEFAULT_EVENT_WINDOWS, ids=window_label)
def test_null_mean_near_zero(null_stats, window):
    assert abs(null_stats[window_label(window)].mean()) <= 0.1


@pytest.mark.parametrize("window", DEFAULT_EVENT_WINDOWS, ids=window_label)
def test_null_std_near_one(null_stats, window):
    assert 0.9 <= null_stats[window_label(window)].std() <= 1.15


@pytest.mark.parametrize("window", DEFAULT_EVENT_WINDOWS, ids=window_label)
def test_null_rejection_rate_near_five_percent(null_stats, window):
    share = (null_stats[window_label(window)].abs() > 1.96).mean()
    assert 0.03 <= share <= 0.08


# ---------------------------------------------------------------------------
# Error types (item 4 of the review)
# ---------------------------------------------------------------------------


def _nan_first(pair):
    security, benchmark = pair
    security.iloc[0] = np.nan
    return security, benchmark, 3


@pytest.mark.parametrize(
    "make_inputs, match",
    [
        (lambda p: (p[0], p[1].iloc[:-1], 3), "share the same dates"),
        (lambda p: (p[0], p[1].iloc[::-1], 3), "different order"),
        (_nan_first, "NaN or infinite"),
        (lambda p: (p[0].iloc[1:], p[1].iloc[1:], DEFAULT_EST_LENGTH), "only 119 observation"),
    ],
    ids=["mismatched", "reordered", "nan", "too-few"],
)
def test_event_data_problems_raise_event_data_error(est_pair, make_inputs, match):
    security, benchmark, min_obs = make_inputs(est_pair)
    with pytest.raises(EventDataError, match=match):
        fit_market_model(security, benchmark, min_obs=min_obs)


def test_event_window_nan_raises_event_data_error(demo):
    window = (-1, 1)
    security = demo["sec_events"][window].copy()
    security.iloc[1] = np.inf
    with pytest.raises(EventDataError):
        car_test(demo["fit"], security, demo["bench_events"][window])


def _constant_benchmark(pair):
    security, benchmark = pair
    benchmark[:] = 0.001
    return security, benchmark, 3


@pytest.mark.parametrize(
    "make_inputs, match",
    [
        (lambda p: (p[0].iloc[:2], p[1].iloc[:2], 2), "min_obs must be at least 3"),
        (lambda p: (p[0].iloc[:0], p[1].iloc[:0], 3), "empty"),
        (_constant_benchmark, "same every day"),
    ],
    ids=["min-obs", "empty", "constant-benchmark"],
)
def test_other_bad_input_is_plain_value_error(est_pair, make_inputs, match):
    security, benchmark, min_obs = make_inputs(est_pair)
    with pytest.raises(ValueError, match=match) as info:
        fit_market_model(security, benchmark, min_obs=min_obs)
    assert not isinstance(info.value, EventDataError)


# ---------------------------------------------------------------------------
# Perfect fit (item 5)
# ---------------------------------------------------------------------------


def test_exact_linear_security_raises(est_pair):
    _, benchmark = est_pair
    security = 0.001 + 1.2 * benchmark
    with pytest.raises(EventDataError, match="aren't the same series"):
        fit_market_model(security, benchmark, min_obs=3)


def test_same_series_twice_raises(est_pair):
    _, benchmark = est_pair
    with pytest.raises(EventDataError, match="aren't the same series"):
        fit_market_model(benchmark, benchmark.copy(), min_obs=3)


def test_tiny_residual_relative_to_security_spread_raises(est_pair):
    # Residual std about 1e-9: above the absolute floor (1e-10) but far below
    # 1e-6 times the security's std (about 10), so the relative floor fires.
    _, benchmark = est_pair
    noise = np.random.default_rng(0).normal(0.0, 1e-9, len(benchmark))
    security = 1000 * benchmark + noise
    with pytest.raises(EventDataError, match="aren't the same series"):
        fit_market_model(security, benchmark, min_obs=3)
