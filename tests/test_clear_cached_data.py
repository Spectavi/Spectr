import json
from spectr import cache


def test_clear_cached_data(tmp_path):
    combined = tmp_path / "cache.json"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / ".AAPL.cache").write_text("dummy")
    data = {"symbols": ["AAPL"], "onboarding": {"broker_key": "b"}}
    combined.write_text(json.dumps(data))

    cache.clear_cached_data(path=combined, cache_dir=str(cache_dir))

    assert combined.exists()
    assert json.loads(combined.read_text()) == {"onboarding": {"broker_key": "b"}}
    assert not cache_dir.exists()
