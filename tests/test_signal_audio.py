import pandas as pd
from types import SimpleNamespace

import spectr.spectr as spectr_module
from spectr.spectr import (
    SpectrApp,
    AppConfig,
    BUY_SOUND_PATH,
    SELL_SOUND_PATH,
    INTRO_SOUND_PATH,
)


class DummyVoiceAgent:
    def __init__(self, *args, **kwargs):
        pass


def _make_app(monkeypatch):
    args = SimpleNamespace(symbols=[], voice_streaming=False, listen=False)
    monkeypatch.setattr(spectr_module, "VoiceAgent", DummyVoiceAgent)
    return SpectrApp(args, AppConfig())


def test_handle_signal_plays_buy_and_sell_sounds(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = _make_app(monkeypatch)
    monkeypatch.setattr(app, "call_from_thread", lambda func, *a, **k: func(*a, **k))
    monkeypatch.setattr(spectr_module.cache, "record_signal", lambda *a, **k: None)

    played = []
    monkeypatch.setattr(
        spectr_module.utils, "play_sound", lambda path: played.append(path)
    )

    df = pd.DataFrame({"trade": [None]}, index=[pd.Timestamp.utcnow()])
    quote = {"price": 1.0}
    app._handle_signal("SYM", df, quote, {"signal": "buy", "reason": "x"})
    assert played[-1] == BUY_SOUND_PATH

    app._handle_signal("SYM", df, quote, {"signal": "sell", "reason": "x"})
    assert played[-1] == SELL_SOUND_PATH


def test_v_binding_depends_on_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = _make_app(monkeypatch)
    assert "v" not in app._bindings.key_to_bindings

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    app = _make_app(monkeypatch)
    assert "v" in app._bindings.key_to_bindings


def test_intro_sound_on_start_when_voice_disabled(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = _make_app(monkeypatch)
    app.voice_agent = None
    app.ticker_symbols = ["SYM"]
    app.active_symbol_index = 0
    monkeypatch.setattr(app, "_is_splash_active", lambda: True)
    monkeypatch.setattr(app, "call_from_thread", lambda func, *a, **k: func(*a, **k))
    monkeypatch.setattr(app, "pop_screen", lambda: None)
    monkeypatch.setattr(
        app,
        "_fetch_data",
        lambda s, q: (
            pd.DataFrame({"trade": [None]}, index=[pd.Timestamp.utcnow()]),
            {"price": 1.0},
        ),
    )
    monkeypatch.setattr(app, "_analyze_indicators", lambda df: df)
    monkeypatch.setattr(
        spectr_module,
        "BROKER_API",
        SimpleNamespace(
            get_position=lambda sym: None, get_pending_orders=lambda sym: []
        ),
    )
    app.strategy_class = SimpleNamespace(detect_signals=lambda *a, **k: None)
    played = []
    monkeypatch.setattr(
        spectr_module.utils, "play_sound", lambda path: played.append(path)
    )
    app._poll_one_symbol("SYM")
    assert played[-1] == INTRO_SOUND_PATH
