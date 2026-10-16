"""Load daily adjusted-close prices from yfinance and compute simple returns.

Prices are cached in one CSV per ticker (data/prices/{TICKER}.csv). The cache
always starts at CACHE_START and ends at the last completed trading day as of
the download. Callers ask for any [start, end) range inside it and get a slice.
"""

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

# Earliest date the cache holds. Requests starting before this are rejected.
# Change it (and re-run with force_download=True) if events need older history.
CACHE_START = "2010-01-01"

DEFAULT_DATA_DIR = Path("data")

_EASTERN = ZoneInfo("America/New_York")


def today_eastern() -> date:
    """Today's date in US Eastern time (the NYSE time zone)."""
    return datetime.now(_EASTERN).date()


def cache_path(ticker: str, data_dir: Path = DEFAULT_DATA_DIR) -> Path:
    """Where a ticker's cached prices live: data/prices/{TICKER}.csv."""
    return Path(data_dir) / "prices" / f"{ticker.upper()}.csv"


def download_adjusted_close(ticker: str, start: str, end: str) -> pd.Series:
    """Download daily adjusted close for one ticker from yfinance.

    `end` is EXCLUSIVE: end="2024-01-01" returns data up to 2023-12-29 at most.
    Returns a float Series indexed by trading date (tz-naive), named "Adj Close".
    Raises ValueError if yfinance returns nothing (bad ticker or empty range).

    auto_adjust=False makes yfinance return both raw "Close" and "Adj Close",
    so we pick the adjusted column by name instead of relying on a default.
    """
    df = yf.download(
        ticker,
        start=start,
        end=end,
        interval="1d",
        auto_adjust=False,
        actions=False,
        multi_level_index=False,
        progress=False,
    )
    if df is None or df.empty:
        raise ValueError(f"yfinance returned no data for {ticker!r} from {start} to {end}")
    return df["Adj Close"].sort_index().rename("Adj Close")


def _read_cache(path: Path) -> pd.Series | None:
    """Read a cached price file, or None if it is missing or empty."""
    if not path.exists():
        return None
    # round_trip makes the parsed floats exactly equal what was written, so a
    # cache hit returns the same numbers as a fresh download.
    df = pd.read_csv(path, index_col="Date", parse_dates=True, float_precision="round_trip")
    prices = df["Adj Close"]
    return prices if len(prices) > 0 else None


def _write_cache(path: Path, prices: pd.Series) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prices.rename("Adj Close").to_csv(path, index_label="Date")


def load_prices(
    ticker: str,
    start: str,
    end: str,
    data_dir: Path = DEFAULT_DATA_DIR,
    force_download: bool = False,
    today: date | None = None,
) -> pd.Series:
    """Daily adjusted close for `ticker` on trading days in [start, end).

    `end` is exclusive, matching yfinance. A weekend or holiday `start` is fine:
    you simply get the first trading day after it.

    Cache rules:
    - The cache is re-downloaded (whole file replaced, never appended) if it is
      missing, if force_download=True, or if the last requested day (end - 1 day)
      is after the cached data's last date.
    - A download runs from CACHE_START to `today` (exclusive), so the last row is
      the last completed trading day and today's unfinished bar is never cached.
    - Known cost: an `end` in the future, or on a weekend/holiday just past the
      last cached date, re-downloads on every call even though nothing new
      exists. Requests inside the cached history are unaffected.

    `today` exists so tests can fix the date; leave it None normally.
    """
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    if start_ts < pd.Timestamp(CACHE_START):
        raise ValueError(f"start {start} is before CACHE_START {CACHE_START}")
    if end_ts <= start_ts:
        raise ValueError(f"end {end} must be after start {start}")

    path = cache_path(ticker, data_dir)
    prices = None if force_download else _read_cache(path)

    last_day_needed = end_ts - pd.Timedelta(days=1)
    if prices is None or last_day_needed > prices.index[-1]:
        download_end = (today or today_eastern()).isoformat()
        prices = download_adjusted_close(ticker, CACHE_START, download_end)
        _write_cache(path, prices)

    window = prices[(prices.index >= start_ts) & (prices.index < end_ts)]
    if window.empty:
        raise ValueError(f"no trading days for {ticker!r} in [{start}, {end})")
    return window


def simple_returns(prices: pd.Series) -> pd.Series:
    """Daily simple returns: price_t / price_(t-1) - 1.

    The first row has no previous price, so it is dropped. A missing price
    stays missing (NaN) and produces NaN returns around it; nothing is filled.
    """
    returns = prices / prices.shift(1) - 1
    return returns.iloc[1:].rename("return")
