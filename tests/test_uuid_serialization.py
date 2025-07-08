import json
import uuid
from spectr import cache


def test_save_combined_handles_uuid(tmp_path):
    path = tmp_path / "cache.json"
    cache._save_combined({"uuid": uuid.uuid4()}, path)
    data = json.loads(path.read_text())
    assert isinstance(data["uuid"], str)