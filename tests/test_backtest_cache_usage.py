import importlib
import pathlib

import pandas as pd

from spectr import cache as cache_module
from spectr import utils as utils_module


class StubDataAPI:
    def __init__(self):
        self.calls: list[str] = []

    def fetch_chart_data_for_backtest(self, symbol, from_date, to_date, interval=None):
        self.calls.append(interval or "1min")
        idx = pd.date_range("2025-01-01", periods=3, freq="D", tz="UTC")
        return pd.DataFrame(
            {
                "open": [1.0, 1.0, 1.0],
                "high": [1.0, 1.0, 1.0],
                "low": [1.0, 1.0, 1.0],
                "close": [1.0, 1.0, 1.0],
                "volume": [10, 10, 10],
            },
            index=idx,
        )

    def fetch_quote(self, symbol):
        return None


def test_get_historical_data_uses_cache(monkeypatch, tmp_path):
    # Isolate cache location
    importlib.reload(cache_module)
    monkeypatch.setattr(cache_module, "CACHE_DIR", tmp_path / "cache")
    importlib.reload(utils_module)

    api = StubDataAPI()

    df1, _ = utils_module.get_historical_data(
        api,
        bb_period=20,
        bb_dev=2,
        macd_thresh=0.01,
        symbol="TEST",
        from_date="2025-01-02",
        to_date="2025-01-03",
        indicators=[],  # Skip heavy indicator calc
    )

    assert not df1.empty
    assert api.calls == ["1min"]

    df2, _ = utils_module.get_historical_data(
        api,
        bb_period=20,
        bb_dev=2,
        macd_thresh=0.01,
        symbol="TEST",
        from_date="2025-01-02",
        to_date="2025-01-03",
        indicators=[],
    )

    # Second call should use cache (no new fetch) and return data.
    assert api.calls == ["1min"]
    assert not df2.empty
