import json
from spectr import cache


def test_trade_amount_cache(tmp_path, monkeypatch):
    path = tmp_path / "cache.json"
    monkeypatch.setattr(cache, "COMBINED_CACHE_FILE", path, raising=False)
    cache.save_trade_amount(123.45, path=path)
    assert path.exists()
    assert cache.load_trade_amount(path=path) == 123.45
