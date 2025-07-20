from types import SimpleNamespace
from spectr import cache


def test_attach_creates_record_with_reason(tmp_path):
    path = tmp_path / "cache.json"
    signals = []
    order = SimpleNamespace(id="1", status="pending")
    cache.attach_order_to_last_signal(
        signals, "AAPL", "buy", order, reason="test", path=path
    )

    loaded = cache.load_strategy_cache(path=path)
    assert len(loaded) == 1
    rec = loaded[0]
    assert rec["reason"] == "test"
    assert rec["order_id"] == "1"
    assert rec["order_status"] == "pending"
