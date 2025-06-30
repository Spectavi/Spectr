import logging

import pandas as pd
from .trading_strategy import TradingStrategy

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
    )

    def __init__(self):
        self.buy_signals = []
        self.sell_signals = []

    @staticmethod
    def detect_signals(df: pd.DataFrame, symbol: str, position=None,
                       stop_loss_pct: float = 0.01, take_profit_pct: float = 0.05,
                       bb_period: int = 20, bb_dev: float = 2.0,
                       macd_thresh: float = 0.005):
        """Return a signal dictionary when conditions trigger."""
        if df.empty:
            return None

        curr = df.iloc[-1]
        price = float(curr.get("close", 0))
        reason = None
        signal = None

        macd_cross = curr.get("macd_crossover")
        above_bb = curr.get("close", 0) > curr.get("bb_upper", 0)
        below_bb = curr.get("close", 0) < curr.get("bb_mid", 0)

        qty = 0
        if position is not None:
            qty = getattr(position, "qty", getattr(position, "size", 0))
            try:
                qty = float(qty)
            except Exception:
                qty = 0.0

        if position is None or qty == 0:
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

