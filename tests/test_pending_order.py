import asyncio
from types import SimpleNamespace

from spectr.trading_operations import TradingOperationsHandler
from spectr.views.order_dialog import OrderDialog
from spectr.fetch.broker_interface import OrderSide, OrderType


def test_on_order_dialog_submit_skips_when_pending(monkeypatch):
    calls = []
    overlay = SimpleNamespace(flash_message=lambda *a, **k: calls.append("flash"))
    
    class MockBroker:
        def has_pending_order_with_side(self, symbol, side):
            return True
    
    app = SimpleNamespace(
        trade_amount=0.0,
        auto_trading_enabled=True,
        voice_agent=SimpleNamespace(say=lambda *a, **k: None),
        strategy_signals=[],
        df_cache={},
        ticker_symbols=["AAA"],
        active_symbol_index=0,
        overlay=overlay,
        broker_api=MockBroker(),
    )
    
    trading_ops = TradingOperationsHandler(app)
    
    monkeypatch.setattr(
        "spectr.trading_operations.cache", 
        SimpleNamespace(attach_order_to_last_signal=lambda *a, **k: None)
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

    trading_ops.on_order_dialog_submit(msg)

    assert calls == ["flash"]
