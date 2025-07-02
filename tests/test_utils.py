import pandas as pd
import pytest
from zoneinfo import ZoneInfo

import spectr.utils as utils
from spectr.fetch.data_interface import DataInterface

# ---------------------------------------------------------------------------
# Helper classes
# ---------------------------------------------------------------------------
class DummyAPI(DataInterface):
    def __init__(self, df_first, df_second=None, quote=None):
        self.df_first = df_first
        self.df_second = df_second if df_second is not None else df_first
        self.quote = quote or {"price": 1.0}
        self.calls = []

    def fetch_chart_data(self, symbol, from_date, to_date):
        self.calls.append(("chart", symbol, from_date, to_date))
        return self.df_first

    def fetch_quote(self, symbol):
        self.calls.append(("quote", symbol))
        return self.quote

    def fetch_chart_data_for_backtest(self, symbol, from_date, to_date, interval=None):
        self.calls.append(("backtest", symbol, from_date, to_date, interval))
        if interval is None:
            return self.df_first
        return self.df_second

    def fetch_top_movers(self, limit=10):
        self.calls.append(("movers", limit))
        return []

    def has_recent_positive_news(self, symbol, hours=12):
        self.calls.append(("news", symbol, hours))
        return False

    def fetch_company_profile(self, symbol):
        self.calls.append(("profile", symbol))
        return {}


# ---------------------------------------------------------------------------
# DataInterface tests
# ---------------------------------------------------------------------------

def test_data_interface_cannot_instantiate():
    with pytest.raises(TypeError):
        DataInterface()


def test_data_interface_subclass():
    api = DummyAPI(pd.DataFrame())
    assert isinstance(api, DataInterface)

# ---------------------------------------------------------------------------
# Utility function tests
# ---------------------------------------------------------------------------

def test_human_format():
    assert utils.human_format(999) == "999"
    assert utils.human_format(1_000) == "1.0K"
    assert utils.human_format(1_234_567) == "1.2M"


def test_is_crypto_symbol():
    assert utils.is_crypto_symbol("BTCUSD")
    assert utils.is_crypto_symbol("ethusdt")
    assert not utils.is_crypto_symbol("AAPL")
    assert not utils.is_crypto_symbol("BTC")


def test_is_market_open_now(monkeypatch):
    import datetime as dt
    class Fixed(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2024, 1, 2, 10, 0, tzinfo=tz)
    monkeypatch.setattr(utils, "datetime", Fixed)
    assert utils.is_market_open_now(ZoneInfo("America/New_York"))

    class Closed(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2024, 1, 6, 10, 0, tzinfo=tz)  # Saturday
    monkeypatch.setattr(utils, "datetime", Closed)
    assert not utils.is_market_open_now(ZoneInfo("America/New_York"))


def test_inject_quote_into_df():
    idx = pd.date_range("2024-01-01 09:30", periods=2, freq="min")
    df = pd.DataFrame({"open": [1, 2], "high": [1, 2], "low": [1, 2], "close": [1, 2], "volume": [10, 10]}, index=idx)
    quote = {"price": 3.0, "timestamp": idx[-1].timestamp() + 60}

    out = utils.inject_quote_into_df(df, quote, tz=ZoneInfo("America/New_York"))

    assert len(out) == 3
    assert 3.0 in out["close"].values
    assert out.index.tz is not None


def test_get_historical_data(monkeypatch):
    idx_full = pd.date_range("2023-12-31", periods=3, freq="D")
    df_full = pd.DataFrame({"open": [1, 2, 3], "high": [1, 2, 3], "low": [1, 2, 3], "close": [1, 2, 3], "volume": [1, 1, 1]}, index=idx_full)
    api = DummyAPI(df_full)
    monkeypatch.setattr(utils.metrics, "analyze_indicators", lambda df, *args, **kw: df)

    df, quote = utils.get_historical_data(api, 20, 2, 0.01, "TEST", "2024-01-01", "2024-01-02")

    assert ("backtest", "TEST", "2023-12-31", "2024-01-02", None) in api.calls
    assert len(df) == 2
    assert quote == {"price": 1.0}


def test_get_historical_data_with_fallback(monkeypatch):
    idx_second = pd.date_range("2023-12-31", periods=3, freq="D")
    df_first = pd.DataFrame()
    df_second = pd.DataFrame({"open": [1, 2, 3], "high": [1, 2, 3], "low": [1, 2, 3], "close": [1, 2, 3], "volume": [1, 1, 1]}, index=idx_second)
    api = DummyAPI(df_first, df_second)
    monkeypatch.setattr(utils.metrics, "analyze_indicators", lambda df, *args, **kw: df)

    df, _ = utils.get_historical_data(api, 20, 2, 0.01, "TEST", "2024-01-01", "2024-01-02")

    assert ("backtest", "TEST", "2023-12-31", "2024-01-02", None) in api.calls
    assert ("backtest", "TEST", "2023-12-31", "2024-01-02", "5min") in api.calls
    assert len(df) == 2


def test_get_live_data(monkeypatch):
    idx = pd.date_range("2024-01-02", periods=1, freq="D")
    df_live = pd.DataFrame({"open": [1], "high": [1], "low": [1], "close": [1], "volume": [1]}, index=idx)
    api = DummyAPI(df_live)
    import datetime as dt
    class Fixed(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2024, 1, 2)
    monkeypatch.setattr(utils, "datetime", Fixed)

    df, quote = utils.get_live_data(api, "TEST")

    assert ("chart", "TEST", "2024-01-02", "2024-01-02") in api.calls
    assert df.equals(df_live)
    assert quote == {"price": 1.0}