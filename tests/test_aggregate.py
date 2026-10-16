"""Tests for the across-event statistics.

Two kinds of tests:
- Exact checks on small hand-made results tables: the numbers must match a
  hand calculation or scipy's own function to floating-point precision.
- Calibration checks on simulated data with fixed seeds: with no true
  effect, how often does each test reject at 5%? A rejection rate estimated
  from R samples has standard error (SE) sqrt(rate * (1 - rate) / R); with
  R = 2000 and rate 5% that is 0.49 percentage points. The checks allow
  3 SE (about 1.5 points), which a correct implementation misses for only
  about 3 seeds in 1000. The seeds are fixed, so each test passes or fails
  the same way on every run.
"""

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from event_study.aggregate import (
    MIN_EVENTS,
    TEST_NAMES,
    across_event_tests,
    compute_tests,
)
from event_study.runner import run_events
from event_study.simulate import NOISE_STD, fake_returns
from event_study.windows import DEFAULT_EST_LENGTH

WINDOW = (-1, 1)
CAR, T = "car_[-1,+1]", "t_[-1,+1]"

N_REPS = 2000
LEVEL = 0.05
SEED = 7


def make_results(cars, scars, failed=()) -> pd.DataFrame:
    """A results table with the columns across_event_tests reads.

    One "ok" row per CAR, then one "failed" row (NaN numbers) per
    (event_id, error) pair in `failed`, like run_events produces.
    """
    ok = pd.DataFrame(
        {
            "event_id": [f"ok_{i}" for i in range(len(cars))],
            CAR: cars,
            T: scars,
            "status": "ok",
            "error": None,
        }
    )
    bad = pd.DataFrame(
        {
            "event_id": [event_id for event_id, _ in failed],
            CAR: np.nan,
            T: np.nan,
            "status": "failed",
            "error": [error for _, error in failed],
        }
    )
    return pd.concat([ok, bad], ignore_index=True)


# --- Exact checks ---------------------------------------------------------------


def test_hand_calculation():
    # CARs 1..5 (in %): mean 3, std sqrt(2.5), t = 3 / (sqrt(2.5) / sqrt(5)) = sqrt(18).
    # All five positive, so the sign test sees 5 of 5: p = 2 * (1/2)^5 = 0.0625.
    # Wilcoxon: every rank is positive, so the smaller rank sum is 0, and only
    # "all +" or "all -" (2 of 32 sign patterns) is that extreme: p = 0.0625.
    cars = np.array([1, 2, 3, 4, 5]) / 100
    result = across_event_tests(make_results(cars, cars * 10), WINDOW)
    tests = result.tests

    assert result.n_used == 5
    assert result.mean_car == pytest.approx(0.03)
    assert result.median_car == pytest.approx(0.03)
    assert result.std_car == pytest.approx(np.sqrt(2.5) / 100)
    assert result.n_positive == 5
    assert tests.loc["cross_sectional_t", "statistic"] == pytest.approx(np.sqrt(18))
    assert tests.loc["cross_sectional_t", "p_value"] == pytest.approx(
        2 * stats.t.sf(np.sqrt(18), df=4)
    )
    # Multiplying every SCAR by 10 does not change the BMP statistic.
    assert tests.loc["bmp", "statistic"] == pytest.approx(np.sqrt(18))
    assert tests.loc["wilcoxon", "statistic"] == 0
    assert tests.loc["wilcoxon", "p_value"] == pytest.approx(0.0625)
    assert tests.loc["sign", "statistic"] == 5
    assert tests.loc["sign", "p_value"] == pytest.approx(0.0625)


def test_matches_scipy():
    rng = np.random.default_rng(1)
    cars = rng.normal(0.004, 0.02, 25)
    # SCARs deliberately not proportional to the CARs, so a test that read
    # the wrong column would give a different answer.
    scars = rng.normal(0.3, 1.0, 25)
    tests = across_event_tests(make_results(cars, scars), WINDOW).tests

    t = stats.ttest_1samp(cars, 0.0)
    bmp = stats.ttest_1samp(scars, 0.0)
    wilcoxon = stats.wilcoxon(cars)
    sign = stats.binomtest(int((cars > 0).sum()), len(cars), 0.5)
    assert tests.loc["cross_sectional_t"].tolist() == pytest.approx([t.statistic, t.pvalue])
    assert tests.loc["bmp"].tolist() == pytest.approx([bmp.statistic, bmp.pvalue])
    assert tests.loc["wilcoxon"].tolist() == pytest.approx([wilcoxon.statistic, wilcoxon.pvalue])
    assert tests.loc["sign", "p_value"] == pytest.approx(sign.pvalue)
    assert list(tests.index) == list(TEST_NAMES)


def test_only_ok_rows_are_used_and_failures_are_listed():
    cars = np.array([0.01, -0.02, 0.03, 0.005, 0.02, -0.01])
    failed = [("too_early", "estimation window needs 12 more row(s)"), ("gap_day", "not in index")]
    result = across_event_tests(make_results(cars, cars * 50, failed), WINDOW)
    clean = across_event_tests(make_results(cars, cars * 50), WINDOW)

    assert result.n_used == 6
    assert result.excluded["event_id"].tolist() == ["too_early", "gap_day"]
    assert result.excluded["reason"].tolist() == [error for _, error in failed]
    assert (result.excluded["status"] == "failed").all()
    # The failed rows' NaNs change nothing.
    pd.testing.assert_frame_equal(result.tests, clean.tests)
    assert clean.excluded.empty


def test_missing_error_message_still_gets_a_reason():
    table = make_results(np.arange(1, 6) / 100, np.arange(1, 6), failed=[("x", None)])
    excluded = across_event_tests(table, WINDOW).excluded
    assert excluded["reason"].tolist() == ["no error message recorded"]


def test_fewer_than_five_ok_events_raises():
    assert MIN_EVENTS == 5
    table = make_results([0.01, 0.02, -0.01, 0.03], [1, 2, -1, 3], failed=[("bad", "NaN return")])
    with pytest.raises(ValueError, match=r"only 4 event\(s\).*at least 5.*bad \(NaN return\)"):
        across_event_tests(table, WINDOW)


def test_five_ok_events_is_enough():
    table = make_results([0.01, 0.02, -0.01, 0.03, 0.005], [1, 2, -1, 3, 0.5])
    assert across_event_tests(table, WINDOW).n_used == 5


def test_missing_column_raises():
    table = make_results(np.arange(1, 6) / 100, np.arange(1, 6)).drop(columns=T)
    with pytest.raises(ValueError, match=r"missing column.*t_\[-1,\+1\]"):
        across_event_tests(table, WINDOW)


def test_window_not_in_results_raises():
    table = make_results(np.arange(1, 6) / 100, np.arange(1, 6))
    with pytest.raises(ValueError, match=r"car_\[-5,\+5\]"):
        across_event_tests(table, (-5, 5))


def test_ok_row_with_nan_raises():
    table = make_results([0.01, 0.02, np.nan, 0.03, 0.0, 0.01], [1, 2, 1, 3, 0, 1])
    with pytest.raises(ValueError, match="status 'ok' but NaN.*ok_2"):
        across_event_tests(table, WINDOW)


def test_identical_cars_raise():
    table = make_results([0.01] * 6, [1.0] * 6)
    with pytest.raises(ValueError, match="same value"):
        across_event_tests(table, WINDOW)


def test_on_run_events_output():
    # Seven events on one simulated series. Rows 130..190 leave room for the
    # estimation window (129 rows before) and the [-5,+5] window (5 rows
    # after, of 200). Row 100 has too little history, so it fails.
    security, benchmark = fake_returns(np.random.default_rng(3))
    positions = [130, 140, 150, 160, 170, 180, 190, 100]
    events = pd.DataFrame(
        {
            "event_id": [f"e{p}" for p in positions],
            "decision_group": "ministerial",
            "direction": "cut",
            "surprise_flag": pd.array([pd.NA] * len(positions), dtype="Int64"),
            "event_time": pd.NaT,
            "used_leak": False,
            "day0": security.index[positions],
        }
    )
    results, _ = run_events(events, security, benchmark)
    result = across_event_tests(results, WINDOW)

    assert result.n_used == 7
    assert result.excluded["event_id"].tolist() == ["e100"]
    assert "estimation window needs" in result.excluded.loc[0, "reason"]
    ok = results[results["status"] == "ok"]
    assert result.mean_car == pytest.approx(ok[CAR].mean())
    # The [-5,+5] window works from the same table.
    assert across_event_tests(results, (-5, 5)).n_used == 7


# --- Calibration on simulated data -------------------------------------------


def draw_events(rng, n_events, jump=0.0):
    """(CARs, SCARs) for n_events fake events over a 3-day window.

    Shortcut: skips the market-model regression and draws what it would
    produce if alpha and beta were known exactly. Each event's 3 abnormal
    returns are normal with std NOISE_STD (plus `jump` on the CAR), and its
    resid_std is the sample std of DEFAULT_EST_LENGTH ordinary-day draws.
    These tests check the across-event statistics only;
    scripts/across_event_demo.py repeats the calibration with the full
    market model.
    """
    abnormal = rng.normal(0.0, NOISE_STD, (n_events, 3))
    cars = abnormal.sum(axis=1) + jump
    resid_std = rng.normal(0.0, NOISE_STD, (n_events, DEFAULT_EST_LENGTH)).std(axis=1, ddof=1)
    return cars, cars / (resid_std * np.sqrt(3))


def rejection_rates(n_events, n_reps=N_REPS, **kwargs) -> pd.Series:
    """Share of n_reps simulated samples in which each test rejects at 5%."""
    rng = np.random.default_rng([SEED, n_events])
    rejects = [compute_tests(*draw_events(rng, n_events, **kwargs))["p_value"] < LEVEL
               for _ in range(n_reps)]
    return pd.DataFrame(rejects).mean()


def tolerance(rate: float, n_reps: int = N_REPS) -> float:
    """3 standard errors of a rejection rate estimated from n_reps samples."""
    return 3 * np.sqrt(rate * (1 - rate) / n_reps)


def sign_test_size(n_events: int) -> float:
    """Exact null rejection rate of the sign test at 5%.

    The binomial has no count with p exactly 0.05, so this is below 5%
    (about 2.1% for N = 10 and 4.3% for N = 30). Comparing the sign test to
    5% would fail a correct implementation.
    """
    counts = np.arange(n_events + 1)
    rejects = [stats.binomtest(k, n_events, 0.5).pvalue < LEVEL for k in counts]
    return float(stats.binom.pmf(counts[rejects], n_events, 0.5).sum())


@pytest.mark.parametrize("n_events", [10, 30])
def test_null_calibration(n_events):
    rates = rejection_rates(n_events)
    # The t-tests are exact for normal CARs. Wilcoxon's exact p is discrete
    # too, but for N >= 10 its largest attainable size is within 0.2 points
    # of 5% (4.9% for N = 10), well inside the tolerance.
    for name in ("cross_sectional_t", "bmp", "wilcoxon"):
        assert rates[name] == pytest.approx(LEVEL, abs=tolerance(LEVEL)), name
    expected_sign = sign_test_size(n_events)
    assert rates["sign"] == pytest.approx(expected_sign, abs=tolerance(expected_sign))


def test_same_volatility_rise_for_every_event_changes_no_p_value():
    # If an event doubles every event's abnormal-return volatility, each CAR
    # and SCAR is (in distribution) doubled. All four tests are unchanged by
    # multiplying every value by the same positive number: the t-tests divide
    # by the cross-sectional std, and ranks and signs do not move. So this
    # holds exactly, not just on average, and a simulated calibration check
    # with doubled volatility could only repeat test_null_calibration.
    cars, scars = draw_events(np.random.default_rng(SEED), 30)
    pd.testing.assert_frame_equal(
        compute_tests(cars, scars)[["p_value"]], compute_tests(2 * cars, 2 * scars)[["p_value"]]
    )


def test_large_effect_is_detected():
    # A 2% CAR against a CAR std of about 1.7% (1% * sqrt(3)): with N = 30 the
    # t-test's expected statistic is about 6.3, and P(CAR > 0) is about 0.88,
    # so every test should reject in nearly all samples. 300 samples is
    # enough to tell 95% from, say, 50%.
    rates = rejection_rates(30, n_reps=300, jump=0.02)
    assert (rates > 0.95).all(), rates.to_dict()
