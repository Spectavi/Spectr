import pandas as pd
from types import SimpleNamespace
import asyncio
from textual.app import App
import spectr.spectr as appmod
from spectr.spectr import SpectrApp
from spectr.views.strategy_screen import StrategyScreen


def test_poll_one_symbol_inactive(monkeypatch):
    df = pd.DataFrame(
        {"open": [1], "high": [1], "low": [1], "close": [1], "volume": [1]},
        index=[pd.Timestamp("2024-01-01")],
    )

    dummy_broker = SimpleNamespace(
        get_position=lambda symbol: None,
        get_pending_orders=lambda symbol: None,
    )
    monkeypatch.setattr(appmod, "BROKER_API", dummy_broker)

    calls = []

    def detect(*a, **k):
        calls.append(True)
        return {"signal": "buy"}

    overlay = SimpleNamespace(flash_message=lambda *a, **k: None)

    app = SimpleNamespace(
        _fetch_data=lambda sym, quote=None: (df, {"price": 1}),
        _analyze_indicators=lambda d: d,
        _normalize_position=lambda p: p,
        strategy_class=SimpleNamespace(detect_signals=detect),
        _handle_signal=lambda *a: None,
        df_cache={},
        _update_queue=SimpleNamespace(put=lambda sym: None),
        ticker_symbols=["AAA"],
        active_symbol_index=0,
        _is_splash_active=lambda: False,
        pop_screen=lambda: None,
        call_from_thread=lambda func, *a, **k: func(*a, **k),
        voice_agent=SimpleNamespace(say=lambda *a, **k: None),
        update_view=lambda sym: None,
        query_one=lambda sel, cls: overlay,
        strategy_active=False,
    )

    SpectrApp._poll_one_symbol(app, "AAA")

    assert calls == []


def test_strategy_screen_buttons_toggle():
    class ToggleApp(App):
        def __init__(self) -> None:
            super().__init__()
            self.toggled = []

        async def on_mount(self) -> None:
            self.scr = StrategyScreen([], ["CustomStrategy"], "CustomStrategy")
            await self.push_screen(self.scr)

        def set_strategy_active(self, enabled: bool) -> None:
            self.toggled.append(enabled)

    async def run() -> None:
        async with ToggleApp().run_test() as pilot:
            screen = pilot.app.scr
            overlay = SimpleNamespace(flash_message=lambda *a, **k: None)
            pilot.app.query_one = lambda *a, **k: overlay
            await screen.on_button_pressed(
                SimpleNamespace(button=SimpleNamespace(id="strategy-activate"))
            )
            await screen.on_button_pressed(
                SimpleNamespace(button=SimpleNamespace(id="strategy-deactivate"))
            )
            assert pilot.app.toggled == [True, False]

    asyncio.run(run())


def test_set_auto_trading_activates_strategy():
    calls = []

    def _set_strategy_active(enabled: bool) -> None:
        calls.append(enabled)

    app = SimpleNamespace(
        auto_trading_enabled=False,
        screen_stack=[],
        query_one=lambda *a, **k: None,
        update_status_bar=lambda: None,
        set_strategy_active=_set_strategy_active,
    )

    SpectrApp.set_auto_trading(app, True)

    assert app.auto_trading_enabled
    assert calls == [True]
