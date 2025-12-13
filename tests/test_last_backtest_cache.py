import json
import importlib
import pathlib

from spectr import cache as cache_module


def test_last_backtest_save_and_load(monkeypatch, tmp_path):
    monkeypatch.setattr(cache_module, "LAST_BACKTEST_FILE", tmp_path / "last.json")

    payload = {
        "symbol": "TEST",
        "from": "2025-01-01",
        "to": "2025-01-05",
        "summary": {"final_value": 1234.56},
    }
    cache_module.save_last_backtest(payload, path=cache_module.LAST_BACKTEST_FILE)
    loaded = cache_module.load_last_backtest(path=cache_module.LAST_BACKTEST_FILE)
    assert loaded.get("symbol") == "TEST"
    assert loaded.get("summary", {}).get("final_value") == 1234.56
