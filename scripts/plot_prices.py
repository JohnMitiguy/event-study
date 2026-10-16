"""Plot XLE vs SPY total return since 2010, both rebased to 100.

Run from the project root (the price cache lives at the relative path data/):

    uv run python scripts/plot_prices.py            # use the cached prices as they are
    uv run python scripts/plot_prices.py --refresh  # re-download prices first

Nothing is downloaded unless a cache file is missing or --refresh is passed,
so this script never changes the data scripts/run_opec.py uses by accident.

Prints the NYSE trading-day check for each ticker, then saves
charts/xle_vs_spy.png. A failed check is printed but does not stop the chart.
"""

import argparse
from datetime import datetime
from pathlib import Path

import matplotlib

# "Agg" draws straight to a file, so no chart window pops up.
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from event_study.event_days import check_trading_days
from event_study.prices import cache_path, load_cached

TICKERS = ["XLE", "SPY"]
OUTPUT = Path("charts") / "xle_vs_spy.png"

# Line colors: the first two slots of the colorblind-checked default palette.
COLORS = {"XLE": "#2a78d6", "SPY": "#eb6834"}
TEXT_SECONDARY = "#52514e"


def report_trading_days(ticker: str, prices: pd.Series) -> None:
    """Print whether the price dates match the NYSE trading calendar.

    check_trading_days is named for returns, but it only looks at the dates,
    so it works on prices too. It returns nothing when the dates are fine and
    raises ValueError when they are not; we catch that and print it instead.
    """
    first, last = prices.index[0].date(), prices.index[-1].date()
    try:
        check_trading_days(prices)
        print(f"{ticker}: trading days OK ({first} to {last}, {len(prices)} days)")
    except ValueError as err:
        print(f"*** {ticker}: TRADING-DAY CHECK FAILED ***")
        print(err)
        print(f"*** {ticker}: chart is still drawn, but check the data above ***")


def download_date(ticker: str) -> str:
    """Date the cached CSV was last written, i.e. when yfinance was last called.

    The cache is reused until --refresh is passed, so this can be well
    before today.
    """
    modified = cache_path(ticker).stat().st_mtime
    return datetime.fromtimestamp(modified).date().isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot XLE vs SPY total return.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="re-download XLE and SPY prices first (otherwise the cache is used as is)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    # 1. Load prices: the whole cache, which starts at prices.CACHE_START
    #    (2010-01-01). Downloaded only if missing or with --refresh.
    prices = {ticker: load_cached(ticker, refresh=args.refresh) for ticker in TICKERS}

    # 2. Check each ticker's dates against the NYSE calendar.
    for ticker in TICKERS:
        report_trading_days(ticker, prices[ticker])

    # 3. Put both series side by side. dropna() keeps only dates where both
    #    have a price, so they share the same first date.
    table = pd.DataFrame(prices).dropna()

    # 4. Rebase: divide every row by the first row and multiply by 100,
    #    so both lines start at exactly 100.
    rebased = table / table.iloc[0] * 100

    # 5. Draw one line per ticker.
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for ticker in TICKERS:
        ax.plot(rebased.index, rebased[ticker], color=COLORS[ticker], linewidth=2, label=ticker)
        # Write the ticker name at the end of its line so it is not color-only.
        ax.annotate(
            ticker,
            xy=(rebased.index[-1], rebased[ticker].iloc[-1]),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            color=TEXT_SECONDARY,
        )

    # 6. Title, axis labels, legend, and a light grid.
    ax.set_title("XLE vs SPY, total return, rebased to 100")
    ax.set_xlabel("Date")
    ax.set_ylabel(f"Value (100 = {table.index[0].date()})")
    ax.axhline(100, color="#c3c2b7", linewidth=1)
    ax.grid(axis="y", color="#e6e5e0", linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper left", frameon=False)

    # 7. Caption: where the data came from, the last data date, and the date
    #    the cached files were last downloaded.
    downloaded = ", ".join(f"{t} {download_date(t)}" for t in TICKERS)
    caption = (
        "Source: Yahoo Finance adjusted close (yfinance), dividends included. "
        f"Data through {table.index[-1].date()}. Downloaded: {downloaded}."
    )
    fig.text(0.01, 0.01, caption, fontsize=8, color=TEXT_SECONDARY)

    # 8. Save the chart, creating charts/ if it does not exist yet.
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0.04, 1, 1))  # leave room at the bottom for the caption
    fig.savefig(OUTPUT, dpi=150)
    print(f"Saved {OUTPUT}")


if __name__ == "__main__":
    main()
