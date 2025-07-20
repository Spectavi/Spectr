import types
from spectr.fetch.alpaca import AlpacaInterface, OrderSide, OrderType, TimeInForce
import spectr.fetch.alpaca as alpaca


def test_alpaca_afterhours_time_in_force(monkeypatch):
    captured = {}

    class DummyTradingClient:
        def __init__(self, *a, **kw):
            pass

        def submit_order(self, req):
            captured['tif'] = req.time_in_force
            captured['extended_hours'] = getattr(req, 'extended_hours', None)
            captured['req_type'] = type(req)
            return 'ok'

    class DummyLimitOrderRequest:
        def __init__(self, **kwargs):
            self.time_in_force = kwargs['time_in_force']
            self.extended_hours = kwargs.get('extended_hours')

    monkeypatch.setattr(alpaca, 'TradingClient', DummyTradingClient)
    monkeypatch.setattr(alpaca, 'LimitOrderRequest', DummyLimitOrderRequest)
    monkeypatch.setattr(alpaca, 'MarketOrderRequest', DummyLimitOrderRequest)

    iface = AlpacaInterface()
    iface.submit_order(
        symbol='AAPL',
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=1,
        limit_price=10.0,
        market_price=None,
        extended_hours=True,
    )

    assert captured['tif'] == TimeInForce.DAY
    assert captured['extended_hours'] is True
