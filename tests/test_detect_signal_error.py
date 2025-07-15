import pandas as pd
from types import SimpleNamespace
import spectr.spectr as appmod
from spectr.spectr import SpectrApp


def test_poll_one_symbol_error(monkeypatch):
    df = pd.DataFrame(
        {"open": [1], "high": [1], "low": [1], "close": [1], "volume": [1]},
        index=[pd.Timestamp("2024-01-01")],
    )

    overlay_msgs = []
    overlay = SimpleNamespace(
        flash_message=lambda msg, style="bold red": overlay_msgs.append(msg)
    )

    calls = {"said": [], "popped": False}

    dummy_broker = SimpleNamespace(
        get_position=lambda symbol: None,
        get_pending_orders=lambda symbol: None,
    )
    monkeypatch.setattr(appmod, "BROKER_API", dummy_broker)

    def raise_detect(*a, **k):
        raise ValueError("boom")

    app = SimpleNamespace(
        _fetch_data=lambda sym, quote=None: (df, {"price": 1}),
        _analyze_indicators=lambda d: d,
        _normalize_position=lambda p: p,
        strategy_class=SimpleNamespace(detect_signals=raise_detect),
        _handle_signal=lambda *a: None,
        df_cache={},
        _update_queue=SimpleNamespace(put=lambda sym: None),
        ticker_symbols=["AAA"],
        active_symbol_index=0,
        _is_splash_active=lambda: True,
        pop_screen=lambda: calls.__setitem__("popped", True),
        call_from_thread=lambda func, *a, **k: func(*a, **k),
        voice_agent=SimpleNamespace(
            say=lambda text, wait=False: calls["said"].append(text)
        ),
        update_view=lambda sym: None,
        query_one=lambda sel, cls: overlay,
    )

    SpectrApp._poll_one_symbol(app, "AAA")

    assert overlay_msgs == ["Strategy error: boom"]
    assert calls["said"] == ["Strategy error: boom"]
    assert calls["popped"]
