import pandas as pd
import backtrader as bt

class CustomStrategy(bt.Strategy):
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

        if position is None or float(getattr(position, "qty", 0)) == 0:
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

    # ----- Backtesting -----
    def next(self):
        if len(self.data) < 2:
            return

        N = 200
        data = {
            "close": [self.datas[0].close[-i] for i in reversed(range(N))],
        }
        df = pd.DataFrame(data)
        res = self.detect_signals(
            df,
            self.p.symbol,
            position=self.position,
            stop_loss_pct=self.p.stop_loss_pct,
            take_profit_pct=self.p.take_profit_pct,
            bb_period=self.p.bb_period,
            bb_dev=self.p.bb_dev,
            macd_thresh=self.p.macd_thresh,
        )
        if res and res["signal"] == "buy" and not self.position:
            self.buy()
            self.buy_signals.append({
                "type": "buy",
                "time": self.datas[0].datetime.datetime(0),
                "price": self.datas[0].close[0],
            })
        elif res and res["signal"] == "sell" and self.position:
            self.sell()
            self.sell_signals.append({
                "type": "sell",
                "time": self.datas[0].datetime.datetime(0),
                "price": self.datas[0].close[0],
            })

