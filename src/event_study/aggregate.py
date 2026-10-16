"""Across-event statistics: is the average reaction different from zero?

Input is the results table from runner.run_events (one row per event). For
one event window, four tests ask whether the events' CARs are centred on 0:

1. Cross-sectional t-test on the CARs.
2. Standardized-CAR test (Boehmer, Musumeci and Poulsen 1991, "BMP").
3. Wilcoxon signed-rank test on the CARs.
4. Sign test on the CARs.

Every test is two-sided. Only rows with status "ok" are used. N is the
number of those rows, and every other row is listed with its reason in
AcrossEventResult.excluded, so no event disappears silently.

Assumptions shared by all four tests (none is checked here):
- Events are independent of each other. Events whose windows overlap
  (nearby_events > 0 in the results) react to the same market days, so their
  CARs are correlated and every test here then rejects too often.
- Every event is expected to move in the same direction. Averaging a cut
  (expected up) with an increase (expected down) can cancel to 0. Pass a
  subset (e.g. one direction or one decision_group) to test it on its own.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from event_study.runner import car_column, stat_column
from event_study.windows import window_label

# Fewer "ok" events than this raises ValueError: with 4 or fewer, the
# cross-sectional std is too unstable and the sign and Wilcoxon tests cannot
# reach 5% significance at all.
MIN_EVENTS = 5

# Row names of AcrossEventResult.tests, in this order.
TEST_NAMES = ("cross_sectional_t", "bmp", "wilcoxon", "sign")


@dataclass(frozen=True)
class AcrossEventResult:
    """Result of across_event_tests for one event window.

    tests has one row per name in TEST_NAMES and columns "statistic" and
    "p_value" (two-sided). What each statistic means is in the
    across_event_tests docstring.
    """

    window: tuple[int, int]
    n_used: int  # events with status "ok"
    excluded: pd.DataFrame  # event_id, status, reason: every row not used
    mean_car: float
    median_car: float
    std_car: float  # sample std across events (divides by N - 1)
    n_positive: int  # events with CAR > 0
    tests: pd.DataFrame


def _check_columns(results: pd.DataFrame, columns: list[str]) -> None:
    missing = [c for c in columns if c not in results.columns]
    if missing:
        raise ValueError(f"results is missing column(s): {', '.join(missing)}")


def excluded_events(results: pd.DataFrame) -> pd.DataFrame:
    """Rows whose status is not "ok", as event_id, status and reason.

    reason is the row's error message, or "no error message recorded" if it
    is empty (run_events always fills it for failed events).
    """
    rows = results.loc[results["status"] != "ok", ["event_id", "status", "error"]]
    reason = rows["error"].fillna("no error message recorded")
    excluded = rows.drop(columns="error").assign(reason=reason)
    return excluded.reset_index(drop=True)


def _format_excluded(excluded: pd.DataFrame) -> str:
    """'a (reason); b (reason)' for error messages, or 'none'."""
    if excluded.empty:
        return "none"
    return "; ".join(f"{e} ({r})" for e, r in zip(excluded["event_id"], excluded["reason"], strict=True))


def _t_test_on_mean(values: np.ndarray) -> tuple[float, float]:
    """(t, two-sided p) for H0 "the mean is 0": mean / (std / sqrt(N)), N - 1 df.

    std divides by N - 1 (ddof=1). Same as scipy.stats.ttest_1samp.
    """
    n = len(values)
    t = values.mean() / (values.std(ddof=1) / np.sqrt(n))
    # sf is the upper tail, P(T > |t|); doubling it gives the two-sided p.
    p = 2 * stats.t.sf(abs(t), df=n - 1)
    return float(t), float(p)


def _sign_test(values: np.ndarray) -> tuple[int, float]:
    """(number of positive values, two-sided exact binomial p).

    H0: each value is positive with probability 1/2. Values exactly 0 are
    dropped from the count, the usual convention.
    """
    nonzero = values[values != 0]
    n_positive = int((nonzero > 0).sum())
    p = stats.binomtest(n_positive, len(nonzero), 0.5).pvalue
    return n_positive, float(p)


def compute_tests(cars: np.ndarray, scars: np.ndarray) -> pd.DataFrame:
    """The four tests on arrays of CARs and standardized CARs (one per event).

    The arrays must already hold only "ok" events, with no NaN. Most callers
    want across_event_tests, which does that filtering; this is the part the
    simulation demo calls thousands of times. Returns the `tests` table of
    AcrossEventResult.
    """
    t_stat, t_p = _t_test_on_mean(cars)
    bmp_stat, bmp_p = _t_test_on_mean(scars)
    wilcoxon = stats.wilcoxon(cars)
    n_positive, sign_p = _sign_test(cars)
    return pd.DataFrame(
        {
            "statistic": [t_stat, bmp_stat, float(wilcoxon.statistic), float(n_positive)],
            "p_value": [t_p, bmp_p, float(wilcoxon.pvalue), sign_p],
        },
        index=pd.Index(TEST_NAMES, name="test"),
    )


def across_event_tests(results: pd.DataFrame, window: tuple[int, int]) -> AcrossEventResult:
    """Test whether the average CAR over `window` is 0, across events.

    results: the table from run_events. It needs event_id, status, error and
    the window's car_ and t_ columns (e.g. "car_[-1,+1]" and "t_[-1,+1]").
    Only rows with status "ok" are used; the rest are returned in `excluded`
    with their reasons.

    Notation: N events, CAR_i is event i's CAR, L = number of days in the
    window, s_i = event i's resid_std (estimation-window residual std).

    1. cross_sectional_t. statistic = mean(CAR) / (std(CAR) / sqrt(N)),
       std across events with N - 1 in the denominator; p from a t
       distribution with N - 1 df. Uses only how spread out the CARs are
       across events, so it stays valid if the event makes returns more
       volatile. Gives every event the same weight, so one very volatile
       event can dominate the mean.

    2. bmp (Boehmer, Musumeci and Poulsen 1991). First standardize each CAR
       by its own expected spread:

           SCAR_i = CAR_i / (s_i * sqrt(L))

       which is exactly the per-event statistic already in the t_ column
       (market_model.car_test), so this reads that column. Then a t-test on
       the SCARs, across events:

           statistic = mean(SCAR) / (std(SCAR) / sqrt(N))

       with std over N - 1, and p from a t distribution with N - 1 df.
       Standardizing means a noisy event counts less than a quiet one.
       Dividing by the cross-sectional std of the SCARs (instead of
       assuming each SCAR has std 1, as the older Patell test does) is
       what keeps it valid when the event raises volatility.

       Points I am not sure match the paper exactly, flagged on purpose:
       - BMP's standardization also includes the error in the estimated
         alpha and beta: s_i * sqrt(1 + 1/T + (Rm_t - mean Rm)^2 /
         sum((Rm - mean Rm)^2)) per day. It is left out here, matching
         car_test and DECISIONS.md. Because the statistic is unchanged if
         every SCAR is multiplied by the same number, only the part of that
         correction that differs between events matters, which is small
         with a 120-day estimation window.
       - BMP's paper standardizes single days. For a multi-day window this
         divides the CAR by s_i * sqrt(L), which equals summing the daily
         standardized returns and dividing by sqrt(L) (Mikkelson and Partch
         1988) when the correction above is left out.
       - BMP compare the statistic to a standard normal. The t distribution
         with N - 1 df used here gives slightly larger p-values when N is
         small, so it is the more cautious choice. For N = 30 the two 5%
         cutoffs are 2.05 and 1.96.
       - No adjustment for events that share calendar days (Kolari and
         Pynnonen 2010); see the module docstring.

    3. wilcoxon. scipy.stats.wilcoxon on the CARs, with scipy's defaults:
       zero CARs are dropped; p is exact for N <= 50 with no ties or zeros
       and from a normal approximation otherwise. statistic is the smaller
       of (sum of ranks of |CAR| for positive CARs) and (the same for
       negative CARs). H0: CARs are symmetric around 0. Skewed CARs can
       make it reject even when the mean is 0.

    4. sign. statistic = number of events with CAR > 0, out of the nonzero
       CARs; p from the exact binomial with probability 1/2. H0: the median
       CAR is 0. If returns are skewed, the share of positive CARs need not
       be 1/2 with no event effect; Cowan's generalized sign test corrects
       for that using estimation-window returns, which the results table
       does not have. The binomial is discrete, so the test rejects less
       than 5% of the time under H0 (about 2% for N = 10).

    Raises ValueError if columns are missing, an "ok" row has a NaN CAR or
    test statistic, every CAR is identical (the t-tests would divide by 0),
    or fewer than MIN_EVENTS events are "ok". The message lists the
    excluded events.
    """
    car_col, t_col = car_column(window), stat_column(window)
    _check_columns(results, ["event_id", "status", "error", car_col, t_col])

    excluded = excluded_events(results)
    ok = results.loc[results["status"] == "ok"]
    label = window_label(window)
    if len(ok) < MIN_EVENTS:
        raise ValueError(
            f"only {len(ok)} event(s) with status 'ok' for window {label}, need at least "
            f"{MIN_EVENTS}. Excluded: {_format_excluded(excluded)}"
        )

    cars = ok[car_col].to_numpy(dtype=float)
    scars = ok[t_col].to_numpy(dtype=float)
    bad = ~(np.isfinite(cars) & np.isfinite(scars))
    if bad.any():
        bad_ids = ", ".join(str(e) for e in ok["event_id"][bad])
        raise ValueError(f"status 'ok' but NaN or infinite {car_col} or {t_col}: {bad_ids}")
    # max == min rather than std == 0, as in market_model: rounding can leave
    # a tiny nonzero std.
    if cars.max() == cars.min():
        raise ValueError(f"every {car_col} is the same value, so the t-tests are undefined")

    return AcrossEventResult(
        window=window,
        n_used=len(ok),
        excluded=excluded,
        mean_car=float(cars.mean()),
        median_car=float(np.median(cars)),
        std_car=float(cars.std(ddof=1)),
        n_positive=int((cars > 0).sum()),
        tests=compute_tests(cars, scars),
    )
