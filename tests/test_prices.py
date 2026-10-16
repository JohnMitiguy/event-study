"""Tests for the price loader. No network: yf.download is replaced by a fake."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from event_study import prices as P

TODAY = date(2024, 6, 12)  # a Wednesday; the cache then ends 2024-06-11


class FakeDownload:
    """Stands in for yf.download. Returns weekday rows for [start, end)."""

    def __init__(self):
        self.calls = []

    def __call__(self, ticker, **kwargs):
        self.calls.append((ticker, kwargs))
        days = pd.bdate_range(kwargs["start"], pd.Timestamp(kwargs["end"]) - pd.Timedelta(days=1))
        adj = pd.Series(100.0 + np.arange(len(days)), index=days, name="Adj Close")
        df = pd.DataFrame({"Adj Close": adj, "Close": adj * 2})
        df.index.name = "Date"
        return df


@pytest.fixture
def fake(monkeypatch):
    fake = FakeDownload()
    monkeypatch.setattr(P.yf, "download", fake)
    return fake


def load(tmp_path, start, end, **kwargs):
    return P.load_prices("XLE", start, end, data_dir=tmp_path, today=TODAY, **kwargs)


# --- simple_returns ---------------------------------------------------------

def test_simple_returns_values():
    prices = pd.Series([100.0, 110.0, 99.0], index=pd.bdate_range("2024-01-01", periods=3))
    result = P.simple_returns(prices)
    assert list(result.index) == list(prices.index[1:])
    assert result.tolist() == pytest.approx([0.10, -0.10])


def test_simple_returns_leaves_gaps_as_nan():
    prices = pd.Series([100.0, np.nan, 110.0, 121.0], index=pd.bdate_range("2024-01-01", periods=4))
    result = P.simple_returns(prices)
    assert result.isna().tolist() == [True, True, False]
    assert result.iloc[-1] == pytest.approx(0.10)


# --- the yfinance call ------------------------------------------------------

def test_download_call_arguments(fake, tmp_path):
    load(tmp_path, "2024-03-04", "2024-03-08")
    ticker, kwargs = fake.calls[0]
    assert ticker == "XLE"
    assert kwargs == {
        "start": P.CACHE_START,
        "end": "2024-06-12",
        "interval": "1d",
        "auto_adjust": False,
        "actions": False,
        "multi_level_index": False,
        "progress": False,
    }


def test_returns_come_from_adj_close_not_close(fake, tmp_path):
    result = load(tmp_path, "2024-03-04", "2024-03-08")
    assert result.name == "Adj Close"
    raw = fake("XLE", start=P.CACHE_START, end="2024-06-12")  # fake Close is 2x Adj Close
    assert result.iloc[0] == raw["Adj Close"].loc[result.index[0]]
    assert result.iloc[0] != raw["Close"].loc[result.index[0]]


def test_empty_download_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(P.yf, "download", lambda *a, **k: pd.DataFrame())
    with pytest.raises(ValueError, match="no data"):
        load(tmp_path, "2024-03-04", "2024-03-08")


# --- caching ----------------------------------------------------------------

def test_second_call_uses_cache(fake, tmp_path):
    first = load(tmp_path, "2024-03-04", "2024-03-08")
    second = load(tmp_path, "2024-03-04", "2024-03-08")
    assert len(fake.calls) == 1
    assert P.cache_path("XLE", tmp_path).exists()
    pd.testing.assert_series_equal(first, second, check_freq=False, check_index_type=False)


def test_range_inside_cache_is_a_hit(fake, tmp_path):
    load(tmp_path, "2024-03-04", "2024-03-08")
    load(tmp_path, "2020-01-02", "2020-02-01")
    assert len(fake.calls) == 1


def test_end_equal_to_today_is_a_hit(fake, tmp_path):
    # end is exclusive, so end == today needs data only through 2024-06-11.
    load(tmp_path, "2024-03-04", "2024-06-12")
    load(tmp_path, "2024-06-03", "2024-06-12")
    assert len(fake.calls) == 1


def test_end_past_cache_redownloads_and_replaces(fake, tmp_path):
    load(tmp_path, "2024-03-04", "2024-03-08")
    later = P.load_prices(
        "XLE", "2024-06-03", "2024-07-01", data_dir=tmp_path, today=date(2024, 7, 2)
    )
    assert len(fake.calls) == 2
    assert fake.calls[1][1]["end"] == "2024-07-02"
    assert later.index[-1] == pd.Timestamp("2024-06-28")
    cached = P._read_cache(P.cache_path("XLE", tmp_path))
    assert cached.index[-1] == pd.Timestamp("2024-07-01")


def test_force_download(fake, tmp_path):
    load(tmp_path, "2024-03-04", "2024-03-08")
    load(tmp_path, "2024-03-04", "2024-03-08", force_download=True)
    assert len(fake.calls) == 2


def test_weekend_start_does_not_redownload(fake, tmp_path):
    load(tmp_path, "2024-03-04", "2024-03-08")  # warm the cache
    result = load(tmp_path, "2024-03-02", "2024-03-08")  # Saturday start
    assert result.index[0] == pd.Timestamp("2024-03-04")
    assert len(fake.calls) == 1


# --- bad requests -----------------------------------------------------------

def test_start_before_cache_start_raises_without_downloading(fake, tmp_path):
    with pytest.raises(ValueError, match="CACHE_START"):
        load(tmp_path, "2009-12-31", "2010-02-01")
    assert fake.calls == []


def test_end_not_after_start_raises(fake, tmp_path):
    with pytest.raises(ValueError, match="after start"):
        load(tmp_path, "2024-03-08", "2024-03-08")


def test_range_with_no_trading_days_raises(fake, tmp_path):
    with pytest.raises(ValueError, match="no trading days"):
        load(tmp_path, "2024-03-02", "2024-03-04")  # Saturday to Monday, exclusive


# --- load_cached: frozen data (item 1 of the review) ---------------------------


def fail_if_called(*args, **kwargs):
    raise AssertionError("yf.download was called, but the cache should have been used")


def test_load_cached_downloads_when_cache_missing(fake, tmp_path):
    prices = P.load_cached("XLE", data_dir=tmp_path, today=TODAY)
    assert len(fake.calls) == 1
    assert fake.calls[0][1]["end"] == "2024-06-12"
    assert prices.index[-1] == pd.Timestamp("2024-06-11")
    assert P.cache_path("XLE", tmp_path).exists()


def test_load_cached_never_downloads_when_cache_exists(fake, tmp_path, monkeypatch):
    first = P.load_cached("XLE", data_dir=tmp_path, today=TODAY)
    monkeypatch.setattr(P.yf, "download", fail_if_called)
    # A year later the cache is stale, but it is still used as is.
    later = P.load_cached("XLE", data_dir=tmp_path, today=date(2025, 6, 12))
    assert later.index[-1] == pd.Timestamp("2024-06-11")
    pd.testing.assert_series_equal(first, later, check_freq=False, check_index_type=False)


def test_load_cached_refresh_downloads_and_replaces(fake, tmp_path):
    P.load_cached("XLE", data_dir=tmp_path, today=TODAY)
    refreshed = P.load_cached("XLE", data_dir=tmp_path, refresh=True, today=date(2024, 7, 2))
    assert len(fake.calls) == 2
    assert refreshed.index[-1] == pd.Timestamp("2024-07-01")
    assert P._read_cache(P.cache_path("XLE", tmp_path)).index[-1] == pd.Timestamp("2024-07-01")


# --- hashes -------------------------------------------------------------------


def test_hashes_match_between_download_and_cache_read(fake, tmp_path):
    downloaded = P.load_cached("XLE", data_dir=tmp_path, today=TODAY)
    from_cache = P.load_cached("XLE", data_dir=tmp_path, today=TODAY)
    assert P.dates_sha256(downloaded) == P.dates_sha256(from_cache)
    assert P.values_sha256(downloaded) == P.values_sha256(from_cache)


def test_values_hash_changes_with_one_value_but_dates_hash_does_not():
    prices = pd.Series([100.0, 101.0, 102.0], index=pd.bdate_range("2024-01-02", periods=3))
    changed = prices.copy()
    changed.iloc[1] = 101.00000001
    assert P.values_sha256(changed) != P.values_sha256(prices)
    assert P.dates_sha256(changed) == P.dates_sha256(prices)


def test_dates_hash_changes_with_one_date_but_values_hash_does_not():
    prices = pd.Series([100.0, 101.0, 102.0], index=pd.bdate_range("2024-01-02", periods=3))
    shifted = prices.copy()
    shifted.index = pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-05"])
    assert P.dates_sha256(shifted) != P.dates_sha256(prices)
    assert P.values_sha256(shifted) == P.values_sha256(prices)
