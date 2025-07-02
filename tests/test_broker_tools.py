import pytest
from types import SimpleNamespace

from spectr import broker_tools
from spectr.fetch.broker_interface import OrderSide, OrderType


class DummyBroker:
    def __init__(self, qty=1, quote=None):
        self.position_qty = qty
        self.quote = quote or {}
        self.submitted = None

    def get_position(self, symbol):
        if self.position_qty is None:
            return None
        return SimpleNamespace(qty=self.position_qty)

    def submit_order(
        self,
        *,
        symbol,
        side,
        type,
        quantity=None,
        limit_price=None,
        market_price=None,
        real_trades=False,
    ):
        self.submitted = {
            "symbol": symbol,
            "side": side,
            "type": type,
            "quantity": quantity,
            "limit_price": limit_price,
            "market_price": market_price,
            "real_trades": real_trades,
        }
        return self.submitted

    def fetch_quote(self, symbol):
        return self.quote


@pytest.mark.parametrize(
    "side,is_open,expected_type,expected_price_key",
    [
        (OrderSide.BUY, True, OrderType.MARKET, None),
        (OrderSide.SELL, True, OrderType.MARKET, None),
        (OrderSide.BUY, False, OrderType.LIMIT, "ask"),
        (OrderSide.SELL, False, OrderType.LIMIT, "bid"),
    ],
)
def test_prepare_order_details_equity(
    monkeypatch, side, is_open, expected_type, expected_price_key
):
    quote = {"ask": 10.0, "bid": 9.0, "price": 9.5}
    broker = DummyBroker(qty=1, quote=quote)
    monkeypatch.setattr(broker_tools, "is_market_open_now", lambda tz=None: is_open)

    order_type, limit_price = broker_tools.prepare_order_details("NVDA", side, broker)
    assert order_type is expected_type
    if expected_price_key is None:
        assert limit_price is None
    elif expected_price_key == "ask":
        expected = round(quote["ask"] * 1.003, 2)
        assert limit_price == expected
    else:
        expected = round(quote["bid"] * 0.997, 2)
        assert limit_price == expected


@pytest.mark.parametrize(
    "side,is_open",
    [
        (OrderSide.BUY, True),
        (OrderSide.SELL, True),
        (OrderSide.BUY, False),
        (OrderSide.SELL, False),
    ],
)
def test_prepare_order_details_crypto(monkeypatch, side, is_open):
    broker = DummyBroker(qty=1, quote={"ask": 100.0, "bid": 99.0})
    monkeypatch.setattr(broker_tools, "is_market_open_now", lambda tz=None: is_open)
    order_type, limit_price = broker_tools.prepare_order_details("BTCUSD", side, broker)
    assert order_type is OrderType.MARKET
    assert limit_price is None


@pytest.mark.parametrize(
    "side,is_open,expected_type",
    [
        (OrderSide.BUY, True, OrderType.MARKET),
        (OrderSide.SELL, True, OrderType.MARKET),
        (OrderSide.BUY, False, OrderType.LIMIT),
        (OrderSide.SELL, False, OrderType.LIMIT),
    ],
)
def test_submit_order_equity(monkeypatch, side, is_open, expected_type):
    quote = {"ask": 10.0, "bid": 9.0, "price": 9.5}
    broker = DummyBroker(qty=5, quote=quote)
    monkeypatch.setattr(broker_tools, "is_market_open_now", lambda tz=None: is_open)

    price = quote["ask"] if side == OrderSide.BUY else quote["bid"]
    broker_tools.submit_order(
        broker,
        "NVDA",
        side,
        price,
        trade_amount=20.0,
        auto_trading_enabled=True,
    )
    assert broker.submitted["type"] is expected_type
    if is_open:
        assert broker.submitted["limit_price"] is None
    else:
        if side == OrderSide.BUY:
            exp = round(quote["ask"] * 1.003, 2)
        else:
            exp = round(quote["bid"] * 0.997, 2)
        assert broker.submitted["limit_price"] == exp


@pytest.mark.parametrize("is_open", [True, False])
def test_submit_order_crypto(monkeypatch, is_open):
    broker = DummyBroker(qty=2, quote={"ask": 100.0, "bid": 99.0})
    monkeypatch.setattr(broker_tools, "is_market_open_now", lambda tz=None: is_open)

    broker_tools.submit_order(
        broker,
        "BTCUSD",
        OrderSide.BUY,
        price=100.0,
        trade_amount=100.0,
        auto_trading_enabled=True,
    )
    assert broker.submitted["type"] is OrderType.MARKET
    assert broker.submitted["limit_price"] is None
