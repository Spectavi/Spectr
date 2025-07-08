import json
from types import SimpleNamespace
from datetime import datetime
from spectr import cache


def test_order_status_persist(tmp_path):
    path = tmp_path / "cache.json"
    # initial signal with pending status
    rec = {
        "time": datetime.now(),
        "symbol": "AAPL",
        "side": "buy",
        "price": 1.23,
        "reason": "test",
        "strategy": "Test",
        "order_id": "1",
        "order_status": "pending",
    }
    cache.record_signal([], rec, path=path)

    signals = cache.load_strategy_cache(path=path)
    assert signals[0]["order_status"] == "pending"

    orders = [SimpleNamespace(id="1", status="filled")]
    cache.update_order_statuses(signals, orders, path=path)

    reload_signals = cache.load_strategy_cache(path=path)
    assert reload_signals[0]["order_status"] == "filled"