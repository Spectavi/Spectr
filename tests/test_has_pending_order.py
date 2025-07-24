import types
from spectr.fetch.alpaca import AlpacaInterface


class DummyTradingClient:
    def __init__(self, statuses):
        self.statuses = statuses

    def get_orders(self, req):
        return [types.SimpleNamespace(status=s) for s in self.statuses]


def test_has_pending_order_filters_cancelled(monkeypatch):
    iface = AlpacaInterface()
    monkeypatch.setattr(
        iface, "get_api", lambda: DummyTradingClient(["canceled", "cancelled"])
    )
    assert iface.has_pending_order("AAA") is False

    monkeypatch.setattr(
        iface, "get_api", lambda: DummyTradingClient(["new", "canceled"])
    )
    assert iface.has_pending_order("AAA") is True
