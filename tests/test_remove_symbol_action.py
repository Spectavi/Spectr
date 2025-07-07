from spectr.spectr import SpectrApp
from types import SimpleNamespace


def test_ctrl_d_binding_present():
    assert any(
        b[0] == "ctrl+d" and b[1] == "remove_current_symbol" for b in SpectrApp.BINDINGS
    )


def test_action_remove_current_symbol(monkeypatch):
    removed = []
    app = SimpleNamespace(
        ticker_symbols=["A", "B"],
        active_symbol_index=0,
        remove_symbol=lambda sym: removed.append(sym),
        _exit_backtest=lambda: None,
        _is_splash_active=lambda: False,
    )
    SpectrApp.action_remove_current_symbol(app)
    assert removed == ["A"]
