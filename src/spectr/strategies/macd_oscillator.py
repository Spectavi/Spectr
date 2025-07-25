import logging
from typing import Optional

import pandas as pd
from .trading_strategy import (
    TradingStrategy,
    IndicatorSpec,
    get_order_sides,
    check_stop_levels,
    get_position_qty,
)

log = logging.getLogger(__name__)


class MACDOscillator(TradingStrategy):
    """Simple MACD Oscillator based on two moving averages."""

    params = (
        ("symbol", ""),
        ("fast_period", 12),
        ("slow_period", 26),
        ("stop_loss_pct", 0.01),
        ("take_profit_pct", 0.05),
    )

    def __init__(self) -> None:
        self.buy_signals = []
        self.sell_signals = []

    @staticmethod
    def detect_signals(
        df: pd.DataFrame,
        symbol: str,
        position: Optional[object] = None,
        orders=None,
        *,
        fast_period: int = 12,
        slow_period: int = 26,
        stop_loss_pct: float = 0.01,
        take_profit_pct: float = 0.05,
    ) -> Optional[dict]:
        """Return a signal dictionary when conditions trigger."""
        if df.empty:
            return None

        df = df.copy()
        df["ma_fast"] = df["close"].rolling(window=fast_period, min_periods=1).mean()
        df["ma_slow"] = df["close"].rolling(window=slow_period, min_periods=1).mean()
        df["osc"] = df["ma_fast"] - df["ma_slow"]

        if len(df) < 2:
            return None

        curr = df.iloc[-1]
        prev_osc = df["osc"].iloc[-2]
        curr_osc = curr["osc"]
        price = float(curr.get("close", 0))
        signal = None
        reason = None

        stop_signal = check_stop_levels(price, position, stop_loss_pct, take_profit_pct)
        if stop_signal:
            return {
                "signal": stop_signal["signal"],
                "price": price,
                "symbol": symbol,
                "reason": stop_signal["reason"],
            }

        qty = get_position_qty(position)
        in_position = qty != 0

        if not in_position:
            if curr_osc > 0 and prev_osc <= 0:
                signal = "buy"
                reason = "Oscillator crossed above zero"
        else:
            if curr_osc < 0 and prev_osc >= 0:
                signal = "sell"
                reason = "Oscillator crossed below zero"

        if signal:
            sides = get_order_sides(orders)
            if signal.lower() in sides:
                return None
            return {
                "signal": signal,
                "price": price,
                "symbol": symbol,
                "reason": reason,
            }
        return None

    def get_lookback(self) -> int:
        return max(self.p.fast_period, self.p.slow_period) + 5

    def get_signal_args(self) -> dict:
        return {
            "fast_period": self.p.fast_period,
            "slow_period": self.p.slow_period,
            "stop_loss_pct": self.p.stop_loss_pct,
            "take_profit_pct": self.p.take_profit_pct,
        }

    @classmethod
    def get_indicators(cls) -> list[IndicatorSpec]:
        return [
            IndicatorSpec(
                name="MACD",
                params={
                    "window_fast": cls.params.fast_period,
                    "window_slow": cls.params.slow_period,
                },
            )
        ]
