"""Market model: predict a security's return from the benchmark's return.

Two steps, both on daily simple returns stored as decimals (0.04 = 4%):

1. Fit, over the estimation window: regress the security's return on the
   benchmark's return with an intercept,

       security_t = alpha + beta * benchmark_t + error_t

   alpha is the security's average return on a day the benchmark is flat;
   beta is how much the security moves per unit move in the benchmark (1.2
   means 1.2% for each 1% the benchmark moves). The residual standard
   deviation measures the typical size of error_t: how far an ordinary day
   lands from the fitted line.

2. Test, over an event window: the abnormal return on each day is what the
   security actually did minus what the model predicted from the benchmark
   that day. CAR (cumulative abnormal return) is their sum. The test statistic
   divides CAR by the spread CAR would have on ordinary days, so a value
   near 0 means "nothing unusual" and values beyond about +/-2 are rare by
   chance alone.

Assumptions:
- Security and benchmark rows are matched by date. Both inputs must have
  identical indexes (same dates, same order); nothing is re-aligned here.
- Missing or infinite returns raise rather than being dropped, so a fit never
  quietly uses fewer days than the caller thinks.

Errors: problems with one event's data (mismatched dates, NaN/inf, too few
days, a perfect fit) raise EventDataError. Other bad input (min_obs below 3,
empty series, a constant benchmark) raises plain ValueError.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm

from event_study.errors import EventDataError

# n - 2 must be at least 1 to compute the residual standard deviation
# (two parameters, alpha and beta, are estimated from n days).
HARD_MIN_OBS = 3

# A residual std this small means the security is (almost) an exact linear
# function of the benchmark, e.g. the same series passed twice. The test
# statistic divides by resid_std, so it would blow up. Absolute floor, and a
# floor relative to the security's own day-to-day spread.
MIN_RESID_STD = 1e-10
MIN_RESID_STD_RATIO = 1e-6


@dataclass(frozen=True)
class MarketModelFit:
    """Result of fit_market_model. Returns are decimals (0.01 = 1%)."""

    alpha: float
    beta: float
    resid_std: float  # sqrt(sum of squared residuals / (n - 2))
    n: int  # number of days in the estimation window


@dataclass(frozen=True)
class EventWindowResult:
    """Result of car_test for one event window."""

    abnormal: pd.Series  # abnormal return per day, indexed by date
    car: float  # sum of the abnormal returns
    test_stat: float  # car / (resid_std * sqrt(n_days))
    n_days: int  # number of days in the event window


def _first_label(index: pd.Index, mask: np.ndarray) -> str:
    """Index label of the first True in mask, as a short string for errors."""
    label = index[mask.argmax()]
    if isinstance(label, pd.Timestamp):
        return label.date().isoformat()
    return str(label)


def _check_same_dates(security: pd.Series, benchmark: pd.Series) -> None:
    """Raise EventDataError unless both indexes hold the same dates in the same order.

    Index.equals compares element by element, so it also catches the same
    dates in a different order (which would pair the wrong days).
    """
    if security.index.equals(benchmark.index):
        return
    only_security = security.index.difference(benchmark.index)
    only_benchmark = benchmark.index.difference(security.index)
    if len(only_security) == 0 and len(only_benchmark) == 0:
        raise EventDataError(
            "security and benchmark have the same dates but in a different order "
            "(or with different duplicates); they must match row for row"
        )
    parts = []
    if len(only_security) > 0:
        parts.append(f"{len(only_security)} date(s) only in security (first {only_security[0]})")
    if len(only_benchmark) > 0:
        parts.append(f"{len(only_benchmark)} date(s) only in benchmark (first {only_benchmark[0]})")
    raise EventDataError("security and benchmark must share the same dates: " + "; ".join(parts))


def _check_finite(series: pd.Series, name: str) -> None:
    """Raise EventDataError if series has any NaN or +/-inf value.

    np.isfinite is False for NaN, inf and -inf. An inf return would come from
    a zero price, so it is treated as bad data just like a missing one.
    """
    bad = ~np.isfinite(series.to_numpy(dtype=float))
    if bad.any():
        raise EventDataError(
            f"{name} has {bad.sum()} NaN or infinite value(s), "
            f"first on {_first_label(series.index, bad)}"
        )


def _check_pair(security: pd.Series, benchmark: pd.Series) -> None:
    """All input checks shared by the fit and the event-window step."""
    _check_same_dates(security, benchmark)
    if len(security) == 0:
        raise ValueError("security and benchmark are empty")
    _check_finite(security, "security")
    _check_finite(benchmark, "benchmark")


def _check_not_perfect_fit(resid_std: float, security: pd.Series) -> None:
    """Raise EventDataError if the fit leaves (almost) no residual.

    security.std() is the sample std of the estimation-window returns. Real
    daily residuals are around 1e-2, nowhere near these floors, so hitting
    one means the inputs are degenerate.
    """
    floor = max(MIN_RESID_STD, MIN_RESID_STD_RATIO * float(security.std()))
    if resid_std < floor:
        raise EventDataError(
            f"residual std {resid_std:.3g} is below {floor:.3g}: the security is an almost "
            "exact linear function of the benchmark. Check that security and benchmark "
            "aren't the same series."
        )


def fit_market_model(
    security: pd.Series, benchmark: pd.Series, min_obs: int
) -> MarketModelFit:
    """Fit security = alpha + beta * benchmark by OLS over the estimation window.

    Pass the estimation-window slices (e.g. from windows.slice_windows).
    min_obs is required on purpose: pass the estimation length you intended,
    so a window that came out shorter raises instead of fitting on fewer days.
    min_obs must be at least 3, the fewest days that leave a residual
    standard deviation to compute.

    Raises EventDataError if the dates differ, either series has NaN/inf,
    there are fewer than min_obs days, or the fit is perfect (residual std
    below MIN_RESID_STD, or below MIN_RESID_STD_RATIO times the security's
    std). Raises ValueError if min_obs is below 3, the series are empty, or
    the benchmark has the same return every day (beta would be undefined:
    there is no benchmark movement to measure the security's response
    against).
    """
    if min_obs < HARD_MIN_OBS:
        raise ValueError(f"min_obs must be at least {HARD_MIN_OBS}, got {min_obs}")
    _check_pair(security, benchmark)
    n = len(security)
    if n < min_obs:
        raise EventDataError(f"only {n} observation(s) in the estimation window, need at least {min_obs}")
    # Compare max and min rather than testing std() == 0: a constant series
    # can have a tiny nonzero std from floating-point rounding.
    if benchmark.max() == benchmark.min():
        raise ValueError("benchmark return is the same every day, so beta cannot be estimated")

    # statsmodels gets plain numpy arrays. Series from simple_returns are both
    # named "return", so looking coefficients up by name could collide.
    # add_constant puts a column of 1s first; its coefficient is alpha.
    # has_constant="add" forces that column in (the default skips it if the
    # data already looks constant).
    x = sm.add_constant(benchmark.to_numpy(dtype=float), has_constant="add")
    y = security.to_numpy(dtype=float)
    result = sm.OLS(y, x).fit()
    alpha, beta = result.params

    # Divide by n - 2, not n: two numbers (alpha, beta) were fitted to these
    # same days, which makes the residuals a little smaller than the true
    # errors. n - 2 corrects for that. This equals statsmodels' mse_resid.
    resid_std = np.sqrt(result.ssr / (n - 2))
    _check_not_perfect_fit(resid_std, security)
    return MarketModelFit(alpha=float(alpha), beta=float(beta), resid_std=float(resid_std), n=n)


def abnormal_returns(
    fit: MarketModelFit, security: pd.Series, benchmark: pd.Series
) -> pd.Series:
    """Actual security return minus the model's prediction, one value per day.

    Prediction = alpha + beta * benchmark return that day. Pass event-window
    slices. Raises EventDataError under the same date and NaN/inf rules as
    the fit.
    """
    _check_pair(security, benchmark)
    predicted = fit.alpha + fit.beta * benchmark
    return (security - predicted).rename("abnormal_return")


def car_test(
    fit: MarketModelFit, security: pd.Series, benchmark: pd.Series
) -> EventWindowResult:
    """CAR and its test statistic for one event window.

    CAR = sum of the daily abnormal returns over the window's L days.
    test_stat = CAR / (resid_std * sqrt(L)).

    Why that denominator: on an ordinary day an abnormal return has standard
    deviation resid_std. If the L days are independent, their sum has
    variance L * resid_std**2, so standard deviation resid_std * sqrt(L).
    Dividing by it puts CAR in units of "ordinary-day spreads": with no event
    effect the statistic is roughly standard normal.

    Simplifications (the statistic is a bit too large in magnitude because of them):
    - It ignores the error in the estimated alpha and beta. They come from a
      finite sample, so the predictions themselves are slightly off; the full
      formula adds a term for that, which is small when the estimation window
      is long relative to the event window.
    - It assumes abnormal returns are uncorrelated from day to day and have the
      same variance in the event window as in the estimation window. If an
      event makes the security more volatile, the statistic overstates
      significance.
    """
    abnormal = abnormal_returns(fit, security, benchmark)
    n_days = len(abnormal)
    car = float(abnormal.sum())
    test_stat = car / (fit.resid_std * np.sqrt(n_days))
    return EventWindowResult(abnormal=abnormal, car=car, test_stat=float(test_stat), n_days=n_days)
