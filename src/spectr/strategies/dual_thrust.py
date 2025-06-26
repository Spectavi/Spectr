import logging
from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np
import backtrader as bt

log = logging.getLogger(__name__)


class DualThrust(bt.Strategy):
    """Dual Thrust breakout strategy."""

    params = (
        ("symbol", ""),
        ("k", 0.5),
        ("window", 4),
        ("start_time", "03:00"),
        ("end_time", "12:00"),
        ("stop_loss_pct", 0.01),
        ("take_profit_pct", 0.05),
    )

    def __init__(self) -> None:
        self.buy_signals = []
        self.sell_signals = []

    @staticmethod
    def _parse_time(ts: str):
        return datetime.strptime(ts, "%H:%M").time()

    @staticmethod
    def detect_signals(
        df: pd.DataFrame,
        symbol: str,
        position: Optional[object] = None,
        *,
        k: float = 0.5,
        window: int = 4,
        start_time: str = "03:00",
        end_time: str = "12:00",
        stop_loss_pct: float = 0.01,
        take_profit_pct: float = 0.05,
    ) -> Optional[dict]:
        """Return a signal dictionary when conditions trigger."""
        if df.empty or len(df) < 2:
            return None

        df = df.copy()
        df.index = pd.to_datetime(df.index)

        curr = df.iloc[-1]
        curr_dt = curr.name
        curr_date = curr_dt.normalize()
        prev_close = df.iloc[-2]["close"]

        daily = df.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        if curr_date not in daily.index or len(daily.loc[:curr_date]) <= window:
            return None

        hist = daily.shift(1).loc[:curr_date].tail(window)
        range1 = hist["high"].max() - hist["close"].min()
        range2 = hist["close"].max() - hist["low"].min()
        rng = max(range1, range2)

        open_today = daily.loc[curr_date, "open"]
        upper = open_today + k * rng
        lower = open_today - (1 - k) * rng

        st = DualThrust._parse_time(start_time)
        et = DualThrust._parse_time(end_time)

        signal = None
        reason = None
        price = float(curr.get("close", 0))

        qty = getattr(position, "qty", 0) if position is not None else 0
        try:
            qty = float(qty)
        except Exception:
            qty = 0.0
        in_pos = qty != 0
        pos_dir = 1 if qty > 0 else -1 if qty < 0 else 0

        current_time = curr_dt.time()

        if current_time >= et and in_pos:
            signal = "sell" if pos_dir > 0 else "buy"
            reason = "End of day exit"
        elif not in_pos and current_time >= st:
            if prev_close <= upper < price:
                signal = "buy"
                reason = "Breakout above upper"
            elif prev_close >= lower > price:
                signal = "sell"
                reason = "Breakout below lower"
        elif in_pos:
            if pos_dir > 0 and prev_close >= lower > price:
                signal = "sell"
                reason = "Reverse at lower"
            elif pos_dir < 0 and prev_close <= upper < price:
                signal = "buy"
                reason = "Reverse at upper"

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
        N = (self.p.window + 1) * 390 + 5
        data = {
            "close": [self.datas[0].close[-i] for i in reversed(range(N))],
            "open": [self.datas[0].open[-i] for i in reversed(range(N))],
            "high": [self.datas[0].high[-i] for i in reversed(range(N))],
            "low": [self.datas[0].low[-i] for i in reversed(range(N))],
            "volume": [self.datas[0].volume[-i] for i in reversed(range(N))],
        }
        index = [self.datas[0].datetime.datetime(-i) for i in reversed(range(N))]
        df = pd.DataFrame(data, index=index)

        signal = self.detect_signals(
            df,
            self.p.symbol,
            position=self.position,
            k=self.p.k,
            window=self.p.window,
            start_time=self.p.start_time,
            end_time=self.p.end_time,
            stop_loss_pct=self.p.stop_loss_pct,
            take_profit_pct=self.p.take_profit_pct,
        )
        if not signal:
            log.debug("No signal detected, skipping this bar.")
            return
        else:
            log.debug(f"Signal detected: {signal}")

        if signal.get("signal") == "buy" and not self.position.get(self.p.symbol):
            self.buy()
            self.buy_signals.append(
                {
                    "type": "buy",
                    "time": self.datas[0].datetime.datetime(0),
                    "price": self.datas[0].close[0],
                }
            )
        elif signal.get("signal") == "sell" and self.position.get(self.p.symbol):
            self.sell()
            self.sell_signals.append(
                {
                    "type": "sell",
                    "time": self.datas[0].datetime.datetime(0),
                    "price": self.datas[0].close[0],
                }
            )
