import pandas as pd
from types import SimpleNamespace

from spectr.strategies.trading_strategy import IndicatorSpec
from spectr.strategies import metrics
from spectr.spectr import SpectrApp


def _dummy_df():
    idx = pd.date_range("2024-01-01", periods=2, freq="min")
    return pd.DataFrame(
        {
            "open": [1, 1],
            "high": [1, 1],
            "low": [1, 1],
            "close": [1, 1],
            "volume": [1, 1],
        },
        index=idx,
    )


def test_set_strategy_updates_cache(monkeypatch):
    df = _dummy_df()
    new_col = "added"

    def fake_analyze(data, specs):
        data = data.copy()
        data[new_col] = 1
        return data

    monkeypatch.setattr(metrics, "analyze_indicators", fake_analyze)

    updated = []

    def fake_update_view(symbol):
        updated.append(symbol)

    app = SimpleNamespace(
        available_strategies={"Old": object(), "New": object()},
        strategy_name="Old",
        strategy_class=SimpleNamespace(
            get_indicators=lambda: [IndicatorSpec(name="MACD", params={})]
        ),
        df_cache={"SYM": df},
        ticker_symbols=["SYM"],
        active_symbol_index=0,
        update_status_bar=lambda: None,
        update_view=fake_update_view,
    )

    def fake_load_strategy(name):
        return SimpleNamespace(
            get_indicators=lambda: [IndicatorSpec(name="VWAP", params={})]
        )

    monkeypatch.setattr("spectr.spectr.load_strategy", fake_load_strategy)

    SpectrApp.set_strategy(app, "New")

    assert new_col in app.df_cache["SYM"]
    assert updated == ["SYM"]


def test_set_strategy_none(monkeypatch):
    saved = []
    monkeypatch.setattr(
        "spectr.cache.save_selected_strategy", lambda n: saved.append(n)
    )
    app = SimpleNamespace(
        available_strategies={"Test": object()},
        strategy_name="Test",
        strategy_class=object(),
        df_cache={},
        ticker_symbols=["SYM"],
        active_symbol_index=0,
        update_status_bar=lambda: None,
        update_view=lambda *a: None,
    )

    SpectrApp.set_strategy(app, None)

    assert app.strategy_name is None
    assert app.strategy_class is None
    assert saved == [None]
