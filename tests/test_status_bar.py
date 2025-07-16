from types import SimpleNamespace
from spectr.spectr import SpectrApp
from spectr.views.top_overlay import TopOverlay


def test_update_status_bar_no_strategy():
    overlay = TopOverlay()
    app = SimpleNamespace(
        auto_trading_enabled=False,
        ticker_symbols=["AAA"],
        active_symbol_index=0,
        overlay=overlay,
        strategy_name=None,
        strategy_class=None,
    )

    SpectrApp.update_status_bar(app)

    assert "NO STRATEGY" in overlay.status_text


def test_update_status_bar_inactive_strategy():
    overlay = TopOverlay()
    app = SimpleNamespace(
        auto_trading_enabled=False,
        ticker_symbols=["AAA"],
        active_symbol_index=0,
        overlay=overlay,
        strategy_name="Test",
        strategy_class=object(),
        strategy_active=False,
    )

    SpectrApp.update_status_bar(app)

    assert "Test (INACTIVE)" in overlay.status_text
