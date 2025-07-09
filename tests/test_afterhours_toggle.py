import pandas as pd
from types import SimpleNamespace
import spectr.spectr as appmod
from spectr.spectr import SpectrApp


def _dummy_df():
    idx = pd.date_range("2024-01-01", periods=1, freq="min")
    return pd.DataFrame(
        {
            "open": [1],
            "high": [1],
            "low": [1],
            "close": [1],
            "volume": [1],
        },
        index=idx,
    )


def test_handle_signal_afterhours_disabled(monkeypatch):
    df = _dummy_df()
    calls = []

    app = SimpleNamespace(
        auto_trading_enabled=True,
        afterhours_enabled=False,
        trade_amount=0.0,
        voice_agent=SimpleNamespace(say=lambda *a, **k: None),
        signal_detected=[],
        call_from_thread=lambda func, *a, **k: func(*a, **k),
        strategy_signals=[],
        strategy_name="Test",
    )

    monkeypatch.setattr(
        appmod, "BROKER_API", SimpleNamespace(has_pending_order=lambda s: False)
    )
    monkeypatch.setattr(
        appmod.broker_tools, "submit_order", lambda *a, **k: calls.append(True)
    )
    monkeypatch.setattr(appmod.utils, "is_market_open_now", lambda: False)
    monkeypatch.setattr(appmod.cache, "record_signal", lambda *a, **k: None)

    SpectrApp._handle_signal(
        app,
        "AAA",
        df,
        {"price": 10.0},
        {"signal": "buy", "reason": "test"},
    )

    assert calls == []
    assert app.signal_detected == [("AAA", 10.0, "buy", "test")]


def test_handle_signal_afterhours_enabled(monkeypatch):
    df = _dummy_df()
    calls = []

    app = SimpleNamespace(
        auto_trading_enabled=True,
        afterhours_enabled=True,
        trade_amount=0.0,
        voice_agent=SimpleNamespace(say=lambda *a, **k: None),
        signal_detected=[],
        call_from_thread=lambda func, *a, **k: func(*a, **k),
        strategy_signals=[],
        strategy_name="Test",
    )

    monkeypatch.setattr(
        appmod, "BROKER_API", SimpleNamespace(has_pending_order=lambda s: False)
    )
    monkeypatch.setattr(
        appmod.broker_tools, "submit_order", lambda *a, **k: calls.append(True)
    )
    monkeypatch.setattr(appmod.utils, "is_market_open_now", lambda: False)
    monkeypatch.setattr(appmod.cache, "record_signal", lambda *a, **k: None)

    SpectrApp._handle_signal(
        app,
        "AAA",
        df,
        {"price": 10.0},
        {"signal": "buy", "reason": "test"},
    )

    assert calls == [True]
    assert app.signal_detected == []
