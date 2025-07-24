import asyncio
import queue
from types import SimpleNamespace
import spectr.spectr as appmod
from spectr.spectr import SpectrApp


async def _run_updates(app):
    await SpectrApp._process_updates(app)


def test_process_updates_skips_and_continues(monkeypatch):
    q = queue.Queue()
    q.put("AAA")
    q.put(None)  # sentinel for exit
    calls = []

    app = SimpleNamespace(
        _update_queue=q,
        signal_detected=[("AAA", 10.0, "sell", "r")],
        ticker_symbols=["AAA"],
        active_symbol_index=0,
        auto_trading_enabled=True,
        afterhours_enabled=True,
        trade_amount=0.0,
        voice_agent=SimpleNamespace(say=lambda *a, **k: None),
        screen_stack=[],
        strategy_signals=[],
    )

    monkeypatch.setattr(
        appmod,
        "BROKER_API",
        SimpleNamespace(has_pending_order=lambda s: True),
    )
    monkeypatch.setattr(
        appmod.broker_tools, "submit_order", lambda *a, **k: calls.append(True)
    )

    asyncio.run(_run_updates(app))

    assert calls == []
    assert app.signal_detected == []
    assert q.empty()
