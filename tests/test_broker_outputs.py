import pandas as pd
from types import SimpleNamespace

import spectr.fetch.alpaca as alpaca
import spectr.fetch.robinhood as robinhood

class DummyOrder:
    def __init__(self, id="1", symbol="TEST"):
        self.id = id
        self.symbol = symbol
        self.qty = 1
        self.side = "buy"
        self.order_type = "market"
        self.status = "new"
        self.created_at = "2024-01-01T00:00:00Z"
        self.submitted_at = "2024-01-01T00:00:00Z"

    def model_dump(self):
        return {
            "id": self.id,
            "symbol": self.symbol,
            "qty": self.qty,
            "side": self.side,
            "order_type": self.order_type,
            "status": self.status,
            "created_at": self.created_at,
            "submitted_at": self.submitted_at,
        }

class DummyAlpacaAPI:
    def get_orders(self, req):
        return [DummyOrder(), DummyOrder(id="2")]

class DummyRobinOrders:
    def get_all_stock_orders(self):
        return [{"id": "1", "instrument": "foo/TEST", "quantity": "1"}]

    def get_all_open_stock_orders(self):
        return [{"id": "1", "instrument": "foo/TEST", "quantity": "1"}]


def test_alpaca_outputs(monkeypatch):
    iface = alpaca.AlpacaInterface()
    monkeypatch.setattr(iface, "get_api", lambda: DummyAlpacaAPI())

    df_all = iface.get_all_orders()
    assert isinstance(df_all, pd.DataFrame)
    assert not df_all.empty
    assert "symbol" in df_all.columns

    df_pending = iface.get_pending_orders(symbol="TEST")
    assert isinstance(df_pending, pd.DataFrame)
    assert not df_pending.empty
    assert "symbol" in df_pending.columns


def test_robinhood_outputs(monkeypatch):
    monkeypatch.setattr(robinhood.RobinhoodInterface, "_login", lambda self: None)
    dummy = DummyRobinOrders()
    monkeypatch.setattr(robinhood, "r", SimpleNamespace(orders=dummy))

    iface = robinhood.RobinhoodInterface(real_trades=False)

    df_all = iface.get_all_orders()
    assert isinstance(df_all, pd.DataFrame)
    assert not df_all.empty

    df_pending = iface.get_pending_orders("TEST")
    assert isinstance(df_pending, pd.DataFrame)
    assert not df_pending.empty

    df_symbol = iface.get_orders_for_symbol("TEST")
    assert isinstance(df_symbol, pd.DataFrame)
    assert not df_symbol.empty

