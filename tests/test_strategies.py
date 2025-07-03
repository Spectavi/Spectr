import pandas as pd
from types import SimpleNamespace

from spectr.strategies.custom_strategy import CustomStrategy
from spectr.strategies.macd_oscillator import MACDOscillator
from spectr.strategies.awesome_oscillator import AwesomeOscillator
from spectr.strategies.dual_thrust import DualThrust
from spectr.strategies.trading_strategy import IndicatorSpec
from spectr.strategies import metrics


def _stub_analyze(df: pd.DataFrame, *args, **kwargs) -> pd.DataFrame:
    df = df.copy()
    df["macd_crossover"] = None
    df["bb_upper"] = df["close"] + 1
    df["bb_mid"] = df["close"] - 1
    if len(df) >= 2:
        if df["close"].iloc[-1] > df["close"].iloc[-2]:
            df.loc[df.index[-1], "macd_crossover"] = "buy"
        elif df["close"].iloc[-1] < df["close"].iloc[-2]:
            df.loc[df.index[-1], "macd_crossover"] = "sell"
    return df


def test_custom_strategy_live_signals():
    idx = pd.date_range("2021-01-01", periods=2, freq="D")
    df = pd.DataFrame(
        {
            "open": [100, 101],
            "high": [100, 101],
            "low": [100, 101],
            "close": [100, 101],
            "volume": [1, 1],
        },
        index=idx,
    )
    df = _stub_analyze(df)
    sig = CustomStrategy.detect_signals(
        df,
        "TEST",
        position=None,
        stop_loss_pct=0.01,
        take_profit_pct=0.05,
        bb_period=20,
        bb_dev=2,
        macd_thresh=0.005,
        is_backtest=False,
    )
    assert sig and sig["signal"] == "buy"

    idx = pd.date_range("2021-01-01", periods=3, freq="D")
    df = pd.DataFrame(
        {
            "open": [100, 101, 99],
            "high": [100, 101, 99],
            "low": [100, 101, 99],
            "close": [100, 101, 99],
            "volume": [1, 1, 1],
        },
        index=idx,
    )
    df = _stub_analyze(df)
    sig = CustomStrategy.detect_signals(
        df,
        "TEST",
        position=SimpleNamespace(qty=1),
        stop_loss_pct=0.01,
        take_profit_pct=0.05,
        bb_period=20,
        bb_dev=2,
        macd_thresh=0.005,
        is_backtest=False,
    )
    assert sig and sig["signal"] == "sell"


def test_custom_strategy_backtest_signals():
    idx = pd.date_range("2021-01-01", periods=2, freq="D")
    df = pd.DataFrame(
        {
            "open": [100, 101],
            "high": [100, 101],
            "low": [100, 101],
            "close": [100, 101],
            "volume": [1, 1],
            "bb_upper": [101, 102],
            "bb_mid": [99, 100],
            "macd_crossover": [None, "buy"],
        },
        index=idx,
    )
    sig = CustomStrategy.detect_signals(
        df,
        "TEST",
        position=None,
        stop_loss_pct=0.01,
        take_profit_pct=0.05,
        bb_period=20,
        bb_dev=2,
        macd_thresh=0.005,
        is_backtest=False,
    )
    assert sig and sig["signal"] == "buy"

    idx = pd.date_range("2021-01-01", periods=3, freq="D")
    df = pd.DataFrame(
        {
            "open": [100, 101, 99],
            "high": [100, 101, 99],
            "low": [100, 101, 99],
            "close": [100, 101, 99],
            "volume": [1, 1, 1],
            "bb_upper": [101, 102, 100],
            "bb_mid": [99, 100, 98],
            "macd_crossover": [None, "buy", "sell"],
        },
        index=idx,
    )
    sig = CustomStrategy.detect_signals(
        df,
        "TEST",
        position=SimpleNamespace(qty=1),
        stop_loss_pct=0.01,
        take_profit_pct=0.05,
        bb_period=20,
        bb_dev=2,
        macd_thresh=0.005,
        is_backtest=False,
    )
    assert sig and sig["signal"] == "sell"


def test_macd_oscillator_signals():
    idx = pd.date_range("2021-01-01", periods=2, freq="D")
    df = pd.DataFrame(
        {
            "close": [1, 2],
            "open": [1, 2],
            "high": [1.1, 2.1],
            "low": [0.9, 1.9],
            "volume": [1, 1],
        },
        index=idx,
    )
    sig = MACDOscillator.detect_signals(
        df, "TEST", position=None, fast_period=1, slow_period=2
    )
    assert sig and sig["signal"] == "buy"

    idx = pd.date_range("2021-01-01", periods=3, freq="D")
    df = pd.DataFrame(
        {
            "close": [1, 2, 1],
            "open": [1, 2, 1],
            "high": [1.1, 2.1, 1.1],
            "low": [0.9, 1.9, 0.9],
            "volume": [1, 1, 1],
        },
        index=idx,
    )
    sig = MACDOscillator.detect_signals(
        df, "TEST", position=SimpleNamespace(qty=1), fast_period=1, slow_period=2
    )
    assert sig and sig["signal"] == "sell"


def test_awesome_oscillator_signals():
    idx = pd.date_range("2021-01-01", periods=3, freq="D")
    vals = [3, 2, 4]
    df = pd.DataFrame(
        {
            "open": vals,
            "high": [v + 0.1 for v in vals],
            "low": [v - 0.1 for v in vals],
            "close": vals,
            "volume": [1] * 3,
        },
        index=idx,
    )
    sig = AwesomeOscillator.detect_signals(
        df, "TEST", position=None, fast_period=1, slow_period=2
    )
    assert sig and sig["signal"] == "buy"

    idx = pd.date_range("2021-01-01", periods=4, freq="D")
    vals = [3, 2, 4, 1]
    df = pd.DataFrame(
        {
            "open": vals,
            "high": [v + 0.1 for v in vals],
            "low": [v - 0.1 for v in vals],
            "close": vals,
            "volume": [1] * 4,
        },
        index=idx,
    )
    sig = AwesomeOscillator.detect_signals(
        df, "TEST", position=SimpleNamespace(qty=1), fast_period=1, slow_period=2
    )
    assert sig and sig["signal"] == "sell"


def test_dual_thrust_signals():
    dates = ["2021-01-01 09:00", "2021-01-02 09:00", "2021-01-03 09:00"]
    df = pd.DataFrame(
        {
            "open": [100, 100, 100],
            "high": [110, 110, 105],
            "low": [90, 98, 94],
            "close": [105, 108, 94],
            "volume": [1, 1, 1],
        },
        index=pd.to_datetime(dates),
    )
    sig = DualThrust.detect_signals(
        df.iloc[:2],
        "TEST",
        position=None,
        k=0.5,
        window=1,
        start_time="00:00",
        end_time="23:59",
    )
    assert sig and sig["signal"] == "buy"

    sig = DualThrust.detect_signals(
        df,
        "TEST",
        position=SimpleNamespace(qty=1),
        k=0.5,
        window=1,
        start_time="00:00",
        end_time="23:59",
    )
    assert sig and sig["signal"] == "sell"


def test_indicator_specs():
    assert any(spec.name == "MACD" for spec in CustomStrategy.get_indicators())

    mo_inds = MACDOscillator.get_indicators()
    assert len(mo_inds) == 1 and mo_inds[0].name == "MACD"

    ao_inds = AwesomeOscillator.get_indicators()
    assert len(ao_inds) == 2

    dt_inds = DualThrust.get_indicators()
    assert dt_inds and dt_inds[0].name == "DualThrustRange"


def test_analyze_indicators_from_specs():
    idx = pd.date_range("2021-01-01", periods=3, freq="D")
    df = pd.DataFrame(
        {
            "open": [1, 2, 3],
            "high": [1, 2, 3],
            "low": [1, 2, 3],
            "close": [1, 2, 3],
            "volume": [1, 1, 1],
        },
        index=idx,
    )
    specs = [IndicatorSpec(name="VWAP", params={})]
    out = metrics.analyze_indicators(df, specs)
    assert "vwap" in out.columns
    assert "macd" not in out.columns
