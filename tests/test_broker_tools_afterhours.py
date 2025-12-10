import types

import pytest

from spectr import broker_tools
from spectr.fetch.broker_interface import OrderSide, OrderType


class _DummyBroker:
    def __init__(self, quote):
        self.quote = quote
        self.calls = []

    def fetch_quote(self, symbol, afterhours=False):
        self.calls.append(afterhours)
        return self.quote

    def submit_order(self, **kwargs):
        raise AssertionError("submit_order should not be called in this test")

    def get_position(self, symbol):
        return types.SimpleNamespace(qty=1)


def test_prepare_order_details_uses_afterhours_and_ticks(monkeypatch):
    monkeypatch.setattr(broker_tools, "is_market_open_now", lambda: False)
    monkeypatch.setattr(broker_tools, "is_crypto_symbol", lambda s: False)

    broker = _DummyBroker({"ask": 10.0})
    order_type, limit_price = broker_tools.prepare_order_details(
        "ABC", OrderSide.BUY, broker
    )

    assert order_type == OrderType.LIMIT
    assert limit_price == pytest.approx(10.03)
    assert broker.calls == [True]  # afterhours flag passed through


def test_prepare_order_details_sub_dollar_rounds_to_tick(monkeypatch):
    monkeypatch.setattr(broker_tools, "is_market_open_now", lambda: False)
    monkeypatch.setattr(broker_tools, "is_crypto_symbol", lambda s: False)

    broker = _DummyBroker({"ask": 0.015})
    _, limit_price = broker_tools.prepare_order_details("PENNY", OrderSide.BUY, broker)

    assert limit_price == pytest.approx(0.0151)  # 0.015 * 1.003 rounded up to 0.0001


def test_submit_order_aborts_without_limit_price(monkeypatch):
    monkeypatch.setattr(broker_tools, "prepare_order_details", lambda *a, **k: (OrderType.LIMIT, None))
    broker = _DummyBroker({})
    broker.submit_order = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("should not submit"))

    res = broker_tools.submit_order(
        broker,
        "XYZ",
        OrderSide.BUY,
        price=1.0,
        trade_amount=10.0,
        auto_trading_enabled=True,
        voice_agent=None,
    )

    assert res is None
