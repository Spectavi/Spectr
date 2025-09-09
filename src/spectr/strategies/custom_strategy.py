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


class CustomStrategy(TradingStrategy):
    """Simple strategy used for both live signals and backtesting."""

    params = (
        ("symbol", ""),
        ("macd_thresh", 0.005),
        ("bb_period", 100),
        ("bb_dev", 2.0),
        ("stop_loss_pct", 0.01),
        ("take_profit_pct", 0.05),
        ("is_backtest", False),
    )

    def __init__(self):
        self.buy_signals = []
        self.sell_signals = []

    @staticmethod
    def detect_signals(
        df: pd.DataFrame,
        symbol: str,
        position=None,
        orders=None,
        stop_loss_pct: float = 0.01,
        take_profit_pct: float = 0.05,
        bb_period: int = 100,
        bb_dev: float = 2.0,
        macd_thresh: float = 0.005,
        is_backtest=False,
    ):
        """Return a signal dictionary when conditions trigger."""
        if df.empty:
            return None

        curr = df.iloc[-1]
        price = float(curr.get("close", 0))
        reason = None
        signal = None

        stop_signal = check_stop_levels(price, position, stop_loss_pct, take_profit_pct)
        if stop_signal:
            return {
                "signal": stop_signal["signal"],
                "price": price,
                "symbol": symbol,
                "reason": stop_signal["reason"],
            }

        required_cols = {
            "bb_upper",
            "bb_mid",
            "macd_crossover",
        }
        if not required_cols.issubset(df.columns) or any(
            pd.isna(curr.get(col)) for col in required_cols
        ):
            log.warning("Required indicators missing; skipping signal")
            return None

        macd_cross = curr.get("macd_crossover")
        above_bb = curr.get("close") > curr.get("bb_upper")
        below_bb = curr.get("close") < curr.get("bb_mid")

        qty = get_position_qty(position)
        in_position = qty != 0

        if not in_position:
            if macd_cross == "buy":
                signal = "buy"
                reason = "MACD crossover"
            elif above_bb:
                signal = "buy"
                reason = "Price above BB"
        else:
            if macd_cross == "sell":
                signal = "sell"
                reason = "MACD crossunder"
            elif below_bb:
                signal = "sell"
                reason = "Price below BB mid"

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
        return 200

    def get_signal_args(self) -> dict:
        return {
            "stop_loss_pct": self.p.stop_loss_pct,
            "take_profit_pct": self.p.take_profit_pct,
            "bb_period": self.p.bb_period,
            "bb_dev": self.p.bb_dev,
            "macd_thresh": self.p.macd_thresh,
        }

    @classmethod
    def get_indicators(cls) -> list[IndicatorSpec]:
        return [
            IndicatorSpec(
                name="MACD",
                params={
                    "window_fast": 12,
                    "window_slow": 26,
                    "threshold": cls.params.macd_thresh,
                },
            ),
            IndicatorSpec(
                name="BollingerBands",
                params={
                    "window": cls.params.bb_period,
                    "window_dev": cls.params.bb_dev,
                },
            ),
            IndicatorSpec(name="VWAP", params={}),
        ]
