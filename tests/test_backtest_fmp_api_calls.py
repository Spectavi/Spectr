import importlib
import pathlib

import pandas as pd

from spectr import cache as cache_module


def test_fmp_backtest_fetch_uses_requested_range(monkeypatch, tmp_path):
    # Make Spectr's cache live inside the tmp_path so the saved config is the one FMP sees.
    monkeypatch.setattr(pathlib.Path, "home", lambda: tmp_path)
    importlib.reload(cache_module)

    cache_module.save_onboarding_config({"data_key": "TEST_KEY"})

    from spectr.fetch import fmp as fmp_module

    fmp = importlib.reload(fmp_module)
    captured = {}

    calls = []
    def fake_get(url, **kwargs):
        captured["url"] = url
        calls.append(url)

        class Resp:
            status_code = 200

            def json(self):
                return [
                    {
                        "date": "2024-01-01 09:30:00",
                        "open": 1,
                        "high": 1,
                        "low": 1,
                        "close": 1,
                        "volume": 10,
                    },
                    {
                        "date": "2024-01-02 09:30:00",
                        "open": 2,
                        "high": 2,
                        "low": 2,
                        "close": 2,
                        "volume": 20,
                    },
                ]

        return Resp()

    monkeypatch.setattr(fmp.requests, "get", fake_get)

    api = fmp.FMPInterface()
    df = api.fetch_chart_data_for_backtest("TEST", "2024-01-01", "2024-01-02")

    assert "api/v4/historical-price-full/TEST" in captured["url"]
    assert "timeframe=1min" in captured["url"]
    assert "limit=50000" in captured["url"]
    assert "apikey=TEST_KEY" in captured["url"]
    assert "from=2024-01-01" in captured["url"]
    assert "to=2024-01-02" in captured["url"]
    assert df.index.min().date().isoformat() == "2024-01-01"
    assert df.index.max().date().isoformat() == "2024-01-02"
    assert not df.empty


def test_fmp_backtest_fetch_chunks_and_aggregates(monkeypatch, tmp_path):
    """Ensure multiple chunks are requested and stitched."""
    monkeypatch.setattr(pathlib.Path, "home", lambda: tmp_path)
    importlib.reload(cache_module)
    cache_module.save_onboarding_config({"data_key": "TEST_KEY"})

    from spectr.fetch import fmp as fmp_module
    fmp = importlib.reload(fmp_module)

    urls = []

    def fake_get(url, **kwargs):
        urls.append(url)

        class Resp:
            status_code = 200

            def json(self):
                # Return a single row per call with distinct dates so we can detect concatenation.
                day = "2024-01-01" if len(urls) == 1 else "2024-01-05"
                return [
                    {
                        "date": f"{day} 09:30:00",
                        "open": len(urls),
                        "high": len(urls),
                        "low": len(urls),
                        "close": len(urls),
                        "volume": 10 * len(urls),
                    }
                ]

        return Resp()

    monkeypatch.setattr(fmp.requests, "get", fake_get)

    api = fmp.FMPInterface()
    df = api.fetch_chart_data_for_backtest("TEST", "2024-01-01", "2024-02-15")

    assert len(urls) >= 2
    assert df.index.min().date().isoformat() == "2024-01-01"
    assert df.index.max().date().isoformat() == "2024-01-05"
    assert df["close"].iloc[0] == 1
    assert df["close"].iloc[-1] == len(urls)


def test_fmp_backtest_fetch_paginates(monkeypatch, tmp_path):
    """Ensure pagination fetches older rows inside a chunk."""
    monkeypatch.setattr(pathlib.Path, "home", lambda: tmp_path)
    importlib.reload(cache_module)
    cache_module.save_onboarding_config({"data_key": "TEST_KEY"})

    from spectr.fetch import fmp as fmp_module
    fmp = importlib.reload(fmp_module)

    urls = []

    def fake_get(url, **kwargs):
        urls.append(url)
        page = 0
        if "page=" in url:
            try:
                page = int(url.split("page=")[-1].split("&")[0])
            except Exception:
                page = 0

        class Resp:
            status_code = 200

            def json(self_inner):
                if page == 0:
                    return [
                        {
                            "date": "2024-02-15 09:30:00",
                            "open": 2,
                            "high": 2,
                            "low": 2,
                            "close": 2,
                            "volume": 20,
                        }
                    ]
                if page == 1:
                    return [
                        {
                            "date": "2024-01-01 09:30:00",
                            "open": 1,
                            "high": 1,
                            "low": 1,
                            "close": 1,
                            "volume": 10,
                        }
                    ]
                return []

        return Resp()

    monkeypatch.setattr(fmp.requests, "get", fake_get)

    api = fmp.FMPInterface()
    df = api.fetch_chart_data_for_backtest("TEST", "2024-01-01", "2024-02-15")

    assert any("page=0" in u for u in urls)
    assert any("page=1" in u for u in urls)
    assert df.index.min().date().isoformat() == "2024-01-01"
    assert df.index.max().date().isoformat() == "2024-02-15"
