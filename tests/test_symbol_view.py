import pandas as pd
from types import SimpleNamespace

from spectr.views.symbol_view import SymbolView
from spectr.views.graph_view import GraphView
from spectr.views.macd_view import MACDView
from spectr.views.volume_view import VolumeView
from spectr.strategies.trading_strategy import IndicatorSpec


def _dummy_df():
    idx = pd.date_range("2024-01-01", periods=2, freq="min")
    return pd.DataFrame(
        {
            "open": [1, 1],
            "high": [1, 1],
            "low": [1, 1],
            "close": [1, 1],
            "volume": [1, 1],
        },
        index=idx,
    )


def _dummy_args():
    return SimpleNamespace(scale=1, candles=True)


def test_symbol_view_macd_visibility():
    sv = SymbolView()
    sv.graph = GraphView()
    sv.macd = MACDView()
    sv.volume = VolumeView()
    df = _dummy_df()
    specs = [IndicatorSpec(name="MACD", params={})]
    sv.load_df("TEST", df, _dummy_args(), specs)
    assert sv.macd.display is True
    assert sv.graph.indicators == specs


def test_symbol_view_without_macd():
    sv = SymbolView()
    sv.graph = GraphView()
    sv.macd = MACDView()
    sv.volume = VolumeView()
    df = _dummy_df()
    specs = [IndicatorSpec(name="VWAP", params={})]
    sv.load_df("TEST", df, _dummy_args(), specs)
    assert sv.macd.display is False
    assert sv.graph.indicators == specs
