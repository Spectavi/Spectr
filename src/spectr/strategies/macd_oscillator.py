import logging
from typing import Optional

import pandas as pd
import backtrader as bt

log = logging.getLogger(__name__)


class MACDOscillator(bt.Strategy):
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
        df["ma_fast"] = (
            df["close"].rolling(window=fast_period, min_periods=1).mean()
        )
        df["ma_slow"] = (
            df["close"].rolling(window=slow_period, min_periods=1).mean()
        )
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
            qty = getattr(position, "qty", 0)
            in_position = float(qty) != 0

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

    # ----- Backtesting -----
    def next(self) -> None:
        N = max(self.p.fast_period, self.p.slow_period) + 5
        data = {
            "close": [self.datas[0].close[-i] for i in reversed(range(N))],
            "open": [self.datas[0].open[-i] for i in reversed(range(N))],
            "high": [self.datas[0].high[-i] for i in reversed(range(N))],
            "low": [self.datas[0].low[-i] for i in reversed(range(N))],
            "volume": [self.datas[0].volume[-i] for i in reversed(range(N))],
        }
        df = pd.DataFrame(data)

        signal = self.detect_signals(
            df,
            self.p.symbol,
            position=self.position,
            fast_period=self.p.fast_period,
            slow_period=self.p.slow_period,
            stop_loss_pct=self.p.stop_loss_pct,
            take_profit_pct=self.p.take_profit_pct,
        )
        if not signal:
            log.debug("No signal detected, skipping this bar.")
            return
        else:
            log.debug(f"Signal detected: {signal}")

        if signal.get("signal") == "buy" and not self.position.get(self.symbol):
            log.debug(f"BACKTEST: Buy signal detected: {signal['reason']}")
            self.buy()
            self.buy_signals.append(
                {
                    "type": "buy",
                    "time": self.datas[0].datetime.datetime(0),
                    "price": self.datas[0].close[0],
                }
            )
        elif signal.get("signal") == "sell" and self.position.get(self.symbol):
            log.debug(f"BACKTEST: Sell signal detected: {signal['reason']}")
            self.sell()
            self.sell_signals.append(
                {
                    "type": "sell",
                    "time": self.datas[0].datetime.datetime(0),
                    "price": self.datas[0].close[0],
                }
            )
