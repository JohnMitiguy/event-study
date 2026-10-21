"""Fake returns where the true alpha and beta are known.

Used by the demo scripts and the tests to check the market model on data
where the right answer is known. Nothing here touches real prices.

Setup (all returns are decimals, 0.01 = 1%):
    benchmark_t = Normal(mean 0, std BENCHMARK_STD)
    security_t  = TRUE_ALPHA + TRUE_BETA * benchmark_t + Normal(mean 0, std NOISE_STD)

Dates are real NYSE sessions starting on or after FIRST_DATE, because
run_events rejects a return series that is not exactly the NYSE sessions.
The returns do not depend on the dates.
"""

import numpy as np
import pandas as pd

from event_study.event_days import nyse_calendar
from event_study.market_model import car_test, fit_market_model
from event_study.windows import slice_windows, window_label

TRUE_ALPHA = 0.0
TRUE_BETA = 1.2
BENCHMARK_STD = 0.01
NOISE_STD = 0.01
N_DAYS = 200
FIRST_DATE = "2024-01-01"

# Row used as day 0. With a 120-day estimation window and a gap of 10 it needs
# at least 129 rows before it, and with a [-5, +5] window 5 rows after it.
DAY0_POSITION = 150

# The planted-event demo: seed for its data and the jump added on day 0.
DEMO_SEED = 42
PLANTED_JUMP = 0.04

# Master seed for the null calibration run. One random generator is created
# from it and every fake event draws fresh numbers from that generator in turn.
NULL_MASTER_SEED = 2026


def fake_returns(
    rng: np.random.Generator, n_days: int = N_DAYS
) -> tuple[pd.Series, pd.Series]:
    """(security, benchmark) daily returns for n_days NYSE sessions.

    Draws all benchmark returns first, then all noise, from rng. With the
    same seed you get the same numbers every time.
    """
    sessions = nyse_calendar().sessions
    dates = sessions[sessions >= pd.Timestamp(FIRST_DATE)][:n_days]
    benchmark = rng.normal(0.0, BENCHMARK_STD, n_days)
    noise = rng.normal(0.0, NOISE_STD, n_days)
    security = TRUE_ALPHA + TRUE_BETA * benchmark + noise
    return (
        pd.Series(security, index=dates, name="security"),
        pd.Series(benchmark, index=dates, name="benchmark"),
    )


def planted_event(
    seed: int = DEMO_SEED, jump: float = PLANTED_JUMP
) -> tuple[pd.Series, pd.Series, pd.Timestamp]:
    """Fake returns with `jump` added to the security on day 0.

    Returns (security, benchmark, day0). Only the security's day-0 return
    changes; every other day is plain market model plus noise.
    """
    security, benchmark = fake_returns(np.random.default_rng(seed))
    security.iloc[DAY0_POSITION] += jump
    return security, benchmark, security.index[DAY0_POSITION]


def null_test_stats(
    n_events: int,
    seed: int,
    est_length: int,
    gap: int,
    event_windows: tuple[tuple[int, int], ...],
) -> pd.DataFrame:
    """Test statistics for n_events fake events with NO planted jump.

    Each event gets fresh random data, then the full pipeline runs on it:
    slice_windows, fit_market_model (min_obs = est_length), car_test.
    Returns one row per event and one column per event window, named by
    window_label.

    With no real effect, a well-behaved statistic should look roughly
    standard normal across events: mean near 0, standard deviation near 1,
    and about 5% beyond +/-1.96.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n_events):
        security, benchmark = fake_returns(rng)
        day0 = security.index[DAY0_POSITION]
        sec_est, sec_events = slice_windows(security, day0, est_length, gap, event_windows)
        bench_est, bench_events = slice_windows(benchmark, day0, est_length, gap, event_windows)
        fit = fit_market_model(sec_est, bench_est, min_obs=est_length)
        rows.append(
            {
                window_label(w): car_test(fit, sec_events[w], bench_events[w]).test_stat
                for w in event_windows
            }
        )
    return pd.DataFrame(rows)
