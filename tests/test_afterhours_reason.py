import pandas as pd
from types import SimpleNamespace
import spectr.spectr as appmod
from spectr.spectr import SpectrApp


def _dummy_df():
    idx = pd.date_range("2024-01-01", periods=1, freq="min")
    return pd.DataFrame(
        {"open": [1], "high": [1], "low": [1], "close": [1], "volume": [1]}, index=idx
    )


def test_handle_signal_auto_attaches_reason(monkeypatch):
    df = _dummy_df()
    order = SimpleNamespace(id="42", status="new")
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
    monkeypatch.setattr(appmod.broker_tools, "submit_order", lambda *a, **k: order)
    attach_calls = []
    monkeypatch.setattr(
        appmod.cache,
        "attach_order_to_last_signal",
        lambda *a, **k: attach_calls.append((a, k)),
    )
    monkeypatch.setattr(appmod.utils, "is_market_open_now", lambda: False)
    monkeypatch.setattr(appmod.cache, "record_signal", lambda *a, **k: None)

    SpectrApp._handle_signal(
        app, "AAA", df, {"price": 10.0}, {"signal": "buy", "reason": "test"}
    )

    assert attach_calls
    args, kwargs = attach_calls[0]
    assert args[0] is app.strategy_signals
    assert args[1] == "AAA"
    assert args[2] == "buy"
    assert args[3] is order
    assert kwargs["reason"] == "test"
