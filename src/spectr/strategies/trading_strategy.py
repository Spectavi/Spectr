import logging
from typing import Optional, Any

import pandas as pd
import backtrader as bt

log = logging.getLogger(__name__)


class TradingStrategy(bt.Strategy):
    """Common ``next`` implementation shared by many strategies."""

    params = (("symbol", ""),)

    def get_lookback(self) -> int:
        """Return how many bars to include in the DataFrame."""
        return 200

    def get_signal_args(self) -> dict[str, Any]:
        """Return keyword arguments to pass to :meth:`detect_signals`."""
        return {}

    def build_dataframe(self, lookback: int) -> pd.DataFrame:
        data = {
            "close": [self.datas[0].close[-i] for i in reversed(range(lookback))],
            "open": [self.datas[0].open[-i] for i in reversed(range(lookback))],
            "high": [self.datas[0].high[-i] for i in reversed(range(lookback))],
            "low": [self.datas[0].low[-i] for i in reversed(range(lookback))],
            "volume": [self.datas[0].volume[-i] for i in reversed(range(lookback))],
        }
        return pd.DataFrame(data)

    def handle_signal(self, signal: Optional[dict]) -> None:
        if not signal:
            log.debug("No signal detected, skipping this bar.")
            return

        log.debug(f"Signal detected: {signal}")

        if signal.get("signal") == "buy" and not self.position:
            self.buy()
            self.buy_signals.append(
                {
                    "type": "buy",
                    "time": self.datas[0].datetime.datetime(0),
                    "price": self.datas[0].close[0],
                }
            )
        elif signal.get("signal") == "sell" and self.position:
            self.sell()
            self.sell_signals.append(
                {
                    "type": "sell",
                    "time": self.datas[0].datetime.datetime(0),
                    "price": self.datas[0].close[0],
                }
            )

    def next(self) -> None:
        lookback = self.get_lookback()
        df = self.build_dataframe(lookback)
        signal = self.detect_signals(
            df, self.p.symbol, position=self.position, **self.get_signal_args()
        )
        self.handle_signal(signal)
