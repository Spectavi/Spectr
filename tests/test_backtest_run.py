import pandas as pd
from types import SimpleNamespace
from spectr.backtest import run_backtest
from spectr.strategies.macd_oscillator import MACDOscillator


def test_backtest_buy_sell_counts_match():
    idx = pd.date_range("2024-01-01", periods=9, freq="D")
    vals = [1, 2, 1, 2, 1, 2, 1, 2, 1]
    df = pd.DataFrame(
        {
            "open": vals,
            "high": vals,
            "low": vals,
            "close": vals,
            "volume": [1] * 9,
        },
        index=idx,
    )
    config = SimpleNamespace(
        bb_period=20,
        bb_dev=2,
        macd_thresh=0.005,
        fast_period=1,
        slow_period=2,
    )
    result = run_backtest(df, "TEST", config, MACDOscillator)
    assert len(result["buy_signals"]) == len(result["sell_signals"]) == 4
