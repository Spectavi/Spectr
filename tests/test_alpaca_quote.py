from types import SimpleNamespace
import spectr.fetch.alpaca as alpaca


def test_fetch_quote_crypto(monkeypatch):
    called = {}

    class DummyClient:
        def __init__(self, *a, **kw):
            called["init"] = True

        def get_crypto_latest_quote(self, req):
            called["symbol"] = req.symbol_or_symbols
            return {
                req.symbol_or_symbols: SimpleNamespace(ask_price=10.0, bid_price=9.0)
            }

    class FailStockClient:
        def __init__(self, *a, **kw):
            raise AssertionError("stock client used")

    monkeypatch.setattr(alpaca, "CryptoHistoricalDataClient", DummyClient)
    monkeypatch.setattr(alpaca, "StockHistoricalDataClient", FailStockClient)

    iface = alpaca.AlpacaInterface()
    q = iface.fetch_quote("BTCUSD")
    assert q == {"ask": 10.0, "bid": 9.0, "price": 10.0}
    assert called["symbol"] == "BTC/USD"
