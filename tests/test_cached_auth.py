import importlib
from spectr import cache


def test_alpaca_uses_cached_creds(monkeypatch):
    cfg = {
        "broker_key": "bk",
        "broker_secret": "bs",
        "paper_key": "pk",
        "paper_secret": "ps",
        "data_key": "dk",
        "data_secret": "ds",
        "data_api": "alpaca",
    }
    for var in [
        "BROKER_API_KEY",
        "BROKER_SECRET",
        "PAPER_API_KEY",
        "PAPER_SECRET",
        "DATA_API_KEY",
        "DATA_SECRET",
        "DATA_PROVIDER",
    ]:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(cache, "load_onboarding_config", lambda: cfg)

    import spectr.fetch.alpaca as alpaca

    importlib.reload(alpaca)
    assert alpaca.DATA_PROVIDER == "alpaca"
    assert alpaca.API_KEY == "bk"
    assert alpaca.SECRET_KEY == "bs"
    assert alpaca.PAPER_KEY == "pk"
    assert alpaca.PAPER_SECRET == "ps"


def test_robinhood_uses_cached_creds(monkeypatch):
    cfg = {
        "broker_key": "user",
        "broker_secret": "pass",
        "data_key": "du",
        "data_secret": "dp",
        "data_api": "robinhood",
    }
    for var in [
        "BROKER_API_KEY",
        "BROKER_SECRET",
        "DATA_API_KEY",
        "DATA_SECRET",
        "DATA_PROVIDER",
    ]:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(cache, "load_onboarding_config", lambda: cfg)

    import spectr.fetch.robinhood as rh

    importlib.reload(rh)
    assert rh.DATA_PROVIDER == "robinhood"
    assert rh.ROBIN_USER == "user"
    assert rh.ROBIN_PASS == "pass"
