import json
from spectr import cache


def test_trade_amount_cache(tmp_path, monkeypatch):
    path = tmp_path / "amt.json"
    monkeypatch.setattr(cache, "TRADE_AMOUNT_FILE", path)
    cache.save_trade_amount(123.45)
    assert path.exists()
    assert cache.load_trade_amount() == 123.45
