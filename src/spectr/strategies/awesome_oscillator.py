import logging
from typing import Optional

import pandas as pd
from .trading_strategy import TradingStrategy

log = logging.getLogger(__name__)


class AwesomeOscillator(TradingStrategy):
    """Awesome Oscillator strategy using two simple moving averages."""

    params = (
        ("symbol", ""),
        ("fast_period", 5),
        ("slow_period", 34),
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
        fast_period: int = 5,
        slow_period: int = 34,
        stop_loss_pct: float = 0.01,
        take_profit_pct: float = 0.05,
    ) -> Optional[dict]:
        """Return a signal dictionary when conditions trigger."""
        if df.empty or len(df) < 3:
            return None

        df = df.copy()
        mid = (df["high"] + df["low"]) / 2
        df["ma_fast"] = mid.rolling(window=fast_period, min_periods=1).mean()
        df["ma_slow"] = mid.rolling(window=slow_period, min_periods=1).mean()
        df["osc"] = df["ma_fast"] - df["ma_slow"]

        curr = df.iloc[-1]
        prev1 = df.iloc[-2]
        prev2 = df.iloc[-3]

        curr_osc = df["osc"].iloc[-1]
        prev1_osc = df["osc"].iloc[-2]
        prev2_osc = df["osc"].iloc[-3]

        price = float(curr.get("close", 0))
        signal = None
        reason = None

        in_position = False
        if position is not None:
            qty = getattr(position, "qty", 0)
            try:
                in_position = float(qty) != 0
            except Exception:
                in_position = bool(qty)

        if not in_position:
            if (
                curr["open"] > curr["close"]
                and prev1["open"] < prev1["close"]
                and prev2["open"] < prev2["close"]
                and prev1_osc > prev2_osc
                and prev1_osc < 0
                and curr_osc < 0
            ):
                signal = "buy"
                reason = "Bearish saucer"
            elif (
                curr["ma_fast"] > curr["ma_slow"]
                and prev1["ma_fast"] <= prev1["ma_slow"]
            ):
                signal = "buy"
                reason = "MA crossover"
        else:
            if (
                curr["open"] < curr["close"]
                and prev1["open"] > prev1["close"]
                and prev2["open"] > prev2["close"]
                and prev1_osc < prev2_osc
                and prev1_osc > 0
                and curr_osc > 0
            ):
                signal = "sell"
                reason = "Bullish saucer"
            elif (
                curr["ma_fast"] < curr["ma_slow"]
                and prev1["ma_fast"] >= prev1["ma_slow"]
            ):
                signal = "sell"
                reason = "MA crossunder"

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

