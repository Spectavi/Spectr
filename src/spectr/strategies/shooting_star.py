import logging
from typing import Optional

import pandas as pd
import backtrader as bt

log = logging.getLogger(__name__)


class ShootingStar(bt.Strategy):
    """Shooting Star candlestick pattern strategy."""

    params = (
        ("symbol", ""),
        ("lower_bound", 0.2),
        ("body_size", 0.5),
        ("stop_threshold", 0.05),
        ("holding_period", 7),
    )

    def __init__(self) -> None:
        self.buy_signals = []
        self.sell_signals = []
        self.entry_price: Optional[float] = None
        self.bars_since_entry = 0

    @staticmethod
    def detect_signals(
        df: pd.DataFrame,
        symbol: str,
        position: Optional[object] = None,
        *,
        lower_bound: float = 0.2,
        body_size: float = 0.5,
        stop_threshold: float = 0.05,
        holding_period: int = 7,
    ) -> Optional[dict]:
        """Return a signal dictionary when conditions trigger."""
        if len(df) < 4:
            return None

        df = df.copy()
        curr = df.iloc[-1]
        cand = df.iloc[-2]
        prev1 = df.iloc[-3]
        prev2 = df.iloc[-4]

        cond1 = cand["open"] >= cand["close"]
        cond2 = (cand["close"] - cand["low"]) < lower_bound * abs(cand["close"] - cand["open"])
        avg_body = abs(df["open"] - df["close"]).mean()
        cond3 = abs(cand["open"] - cand["close"]) < abs(avg_body) * body_size
        cond4 = (cand["high"] - cand["open"]) >= 2 * (cand["open"] - cand["close"])
        cond5 = cand["close"] >= prev1["close"]
        cond6 = prev1["close"] >= prev2["close"]
        cond7 = curr["high"] <= cand["high"]
        cond8 = curr["close"] <= cand["close"]

        in_position = False
        if position is not None:
            qty = getattr(position, "qty", 0)
            try:
                in_position = float(qty) != 0
            except Exception:
                in_position = bool(qty)

        if not in_position and all([cond1, cond2, cond3, cond4, cond5, cond6, cond7, cond8]):
            return {
                "signal": "sell",
                "price": float(curr.get("close", 0)),
                "symbol": symbol,
                "reason": "shooting star",
            }
        return None

    # ----- Backtesting -----
    def next(self) -> None:
        N = 10
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
            lower_bound=self.p.lower_bound,
            body_size=self.p.body_size,
            stop_threshold=self.p.stop_threshold,
            holding_period=self.p.holding_period,
        )

        if signal:
            log.debug(f"Signal detected: {signal}")
        else:
            log.debug("No signal detected, skipping this bar.")

        if signal and signal.get("signal") == "sell" and not self.position.get(self.p.symbol):
            log.debug(f"BACKTEST: Sell signal detected: {signal['reason']}")
            self.sell()
            self.sell_signals.append(
                {
                    "type": "sell",
                    "time": self.datas[0].datetime.datetime(0),
                    "price": self.datas[0].close[0],
                }
            )
            self.entry_price = self.datas[0].close[0]
            self.bars_since_entry = 0
            return

        if self.position.get(self.p.symbol):
            self.bars_since_entry += 1
            if self.entry_price is None:
                self.entry_price = float(self.datas[0].close[0])
            change = abs(self.datas[0].close[0] / self.entry_price - 1)
            if change > self.p.stop_threshold or self.bars_since_entry >= self.p.holding_period:
                log.debug("BACKTEST: Exiting short position")
                self.buy()
                self.buy_signals.append(
                    {
                        "type": "buy",
                        "time": self.datas[0].datetime.datetime(0),
                        "price": self.datas[0].close[0],
                    }
                )
                self.entry_price = None
                self.bars_since_entry = 0

