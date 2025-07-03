import json
import importlib
import pathlib
from spectr import cache


def test_merge_legacy(tmp_path, monkeypatch):
    monkeypatch.setattr(pathlib.Path, "home", lambda: tmp_path)
    # create legacy files
    (tmp_path / ".spectr_scanner_cache.json").write_text(
        json.dumps({"t": 1, "rows": [{"a": 1}]})
    )
    importlib.reload(cache)
    combined = tmp_path / ".spectr_cache.json"
    assert combined.exists()
    data = json.loads(combined.read_text())
    assert data["scanner_cache"]["rows"][0]["a"] == 1
    assert not (tmp_path / ".spectr_scanner_cache.json").exists()
