from types import SimpleNamespace

from spectr.strategies import trading_strategy as ts
from spectr.strategies.trading_strategy import check_stop_levels


def _pos(qty, entry):
    return SimpleNamespace(qty=qty, avg_entry_price=entry)


def test_trailing_stop_long_tracks_high_and_triggers(monkeypatch):
    ts._TRAIL_STATE.clear()
    pos = _pos(1, 10.0)

    assert check_stop_levels(10.0, pos, 0.05, 0.2, trailing_stop=True) is None
    assert check_stop_levels(11.0, pos, 0.05, 0.2, trailing_stop=True) is None
    stop = check_stop_levels(10.2, pos, 0.05, 0.2, trailing_stop=True)

    assert stop == {"signal": "sell", "reason": "Trailing stop loss"}


def test_trailing_stop_short_tracks_low_and_triggers(monkeypatch):
    ts._TRAIL_STATE.clear()
    pos = _pos(-1, 10.0)

    assert check_stop_levels(10.0, pos, 0.05, 0.2, trailing_stop=True) is None
    assert check_stop_levels(9.0, pos, 0.05, 0.2, trailing_stop=True) is None
    stop = check_stop_levels(9.6, pos, 0.05, 0.2, trailing_stop=True)

    assert stop == {"signal": "buy", "reason": "Trailing stop loss"}


def test_trailing_state_cleared_when_flat():
    ts._TRAIL_STATE.clear()
    pos = _pos(1, 10.0)
    check_stop_levels(10.5, pos, 0.05, 0.2, trailing_stop=True)

    # Flat position clears trailing state
    pos.qty = 0
    check_stop_levels(10.0, pos, 0.05, 0.2, trailing_stop=True)
    assert len(ts._TRAIL_STATE) == 0
