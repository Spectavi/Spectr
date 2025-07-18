import asyncio
from types import SimpleNamespace
import spectr.spectr as appmod
from spectr.spectr import SpectrApp
from spectr.views.order_dialog import OrderDialog
from spectr.fetch.broker_interface import OrderSide, OrderType


def test_on_order_dialog_submit_skips_when_pending(monkeypatch):
    calls = []
    overlay = SimpleNamespace(flash_message=lambda *a, **k: calls.append("flash"))
    app = SimpleNamespace(
        trade_amount=0.0,
        auto_trading_enabled=True,
        voice_agent=SimpleNamespace(say=lambda *a, **k: None),
        strategy_signals=[],
        df_cache={},
        ticker_symbols=["AAA"],
        active_symbol_index=0,
        overlay=overlay,
    )

    monkeypatch.setattr(
        appmod, "BROKER_API", SimpleNamespace(has_pending_order=lambda s: True)
    )
    monkeypatch.setattr(
        appmod.broker_tools, "submit_order", lambda *a, **k: calls.append("submit")
    )
    monkeypatch.setattr(
        appmod.cache, "attach_order_to_last_signal", lambda *a, **k: None
    )

    msg = OrderDialog.Submit(
        sender=None,
        symbol="AAA",
        side=OrderSide.BUY,
        price=10.0,
        qty=1.0,
        total=10.0,
        order_type=OrderType.MARKET,
        limit_price=None,
    )

    asyncio.run(SpectrApp.on_order_dialog_submit(app, msg))

    assert calls == ["flash"]
