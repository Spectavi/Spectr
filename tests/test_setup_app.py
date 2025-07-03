import json
import asyncio
import importlib
import pathlib
from spectr import cache
from spectr.views.setup_app import SetupApp


def test_setup_app_uses_cached_config(tmp_path, monkeypatch):
    monkeypatch.setattr(pathlib.Path, "home", lambda: tmp_path)
    cfg = {
        "broker": "alpaca",
        "paper": "alpaca",
        "data_api": "fmp",
        "broker_key": "b",
        "broker_secret": "bs",
        "paper_key": "p",
        "paper_secret": "ps",
        "data_key": "d",
        "data_secret": "ds",
        "openai_key": "o",
    }
    (tmp_path / ".spectr_onboard.json").write_text(json.dumps(cfg))
    importlib.reload(cache)
    app = SetupApp()

    async def run_mount():
        await app.on_mount()

    asyncio.run(run_mount())
    assert app.result == cfg
