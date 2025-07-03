import logging
from typing import Optional

import pandas as pd
from .trading_strategy import TradingStrategy, IndicatorSpec

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

        in_position = False
        if position is not None:
            qty = getattr(position, "qty", getattr(position, "size", 0))
            try:
                in_position = float(qty) != 0
            except Exception:
                in_position = bool(qty)

        if not in_position:
            if curr_osc > 0 and prev_osc <= 0:
                signal = "buy"
                reason = "Oscillator crossed above zero"
        else:
            if curr_osc < 0 and prev_osc >= 0:
                signal = "sell"
                reason = "Oscillator crossed below zero"

        if signal:
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
                name="SMA",
                params={"window": cls.params.fast_period, "type": "fast"},
            ),
            IndicatorSpec(
                name="SMA",
                params={"window": cls.params.slow_period, "type": "slow"},
            ),
        ]
