from spectr import cache


def test_save_and_load_strategy_configs_roundtrip(tmp_path):
    path = tmp_path / "cache.json"
    cache.save_strategy_configs(
        {
            "aapl": {
                "current": "CustomStrategy",
                "active": True,
                "autoTradeEnabled": False,
                "tradeAmount": 123.45,
            },
            "MSFT": {
                "current": "DualThrust",
                "active": False,
                "autoTradeEnabled": True,
                "tradeAmount": "250.5",
            },
        },
        path=path,
    )

    loaded = cache.load_strategy_configs(path=path)
    assert loaded["AAPL"]["current"] == "CustomStrategy"
    assert loaded["AAPL"]["active"] is True
    assert loaded["AAPL"]["tradeAmount"] == 123.45
    assert loaded["MSFT"]["current"] == "DualThrust"
    assert loaded["MSFT"]["autoTradeEnabled"] is True
    assert loaded["MSFT"]["tradeAmount"] == 250.5
