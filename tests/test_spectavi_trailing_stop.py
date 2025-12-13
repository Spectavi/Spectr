import pandas as pd

from spectr.strategies import spectavi_strategy
from spectr.strategies import trading_strategy


class DummyPosition:
    def __init__(self, qty: float, entry: float):
        self.size = qty
        self.avg_entry_price = entry


def _frame(price: float) -> pd.DataFrame:
    """Return a minimal indicator frame with the given close price."""
    return pd.DataFrame(
        [
            {
                "close": price,
                "macd_angle": 0.0,
                "macd_close": 0.0,
                "macd_signal": 0.0,
                "macd_crossover": "",
                "bb_mid": price,
                "bb_lower": price * 0.99,
                "bb_upper": price * 1.01,
                "bb_angle": 0.0,
            }
        ]
    )


def test_spectavi_trailing_stop_triggers_after_rally_and_pullback():
    # Ensure a clean trailing state for the dummy position.
    trading_strategy._TRAIL_STATE.clear()

    position = DummyPosition(qty=1, entry=100.0)

    # Price rallies first: no stop should trigger, but trail should advance.
    df_up = _frame(110.0)
    stop_loss_pct = 0.05  # 5% trail from the high
    take_profit_pct = 0.5  # Irrelevant for this check
    assert (
        spectavi_strategy.SpectaviStrategy.detect_signals(
            df_up,
            "TEST",
            position=position,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            trailing_stop=True,
        )
        is None
    )

    # Pull back more than the trailing threshold → should emit a sell.
    df_down = _frame(104.0)  # >5% off the 110 high
    signal = spectavi_strategy.SpectaviStrategy.detect_signals(
        df_down,
        "TEST",
        position=position,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        trailing_stop=True,
    )

    assert signal is not None
    assert signal["signal"] == "sell"
    assert signal["reason"] == "Trailing stop loss"


def test_spectavi_trailing_stop_triggers_on_drop_sequence():
    """NVDA-like drop from 208 → 194 should trigger trailing stop."""
    trading_strategy._TRAIL_STATE.clear()
    position = DummyPosition(qty=1, entry=208.0)

    # Initial check at entry/high: no stop.
    assert (
        spectavi_strategy.SpectaviStrategy.detect_signals(
            _frame(208.0),
            "NVDA",
            position=position,
            stop_loss_pct=0.01,  # same as Spectavi default
            take_profit_pct=0.20,
            trailing_stop=True,
        )
        is None
    )

    # Drop to 194 (≈6.7% off the high) should trigger trailing sell.
    signal = spectavi_strategy.SpectaviStrategy.detect_signals(
        _frame(194.0),
        "NVDA",
        position=position,
        stop_loss_pct=0.01,
        take_profit_pct=0.20,
        trailing_stop=True,
    )

    assert signal is not None
    assert signal["signal"] == "sell"
    assert signal["reason"] == "Trailing stop loss"
