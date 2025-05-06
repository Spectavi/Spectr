import pandas as pd
import backtrader as bt

from metrics import analyze_indicators
from utils import log, log_signal


class SignalStrategy(bt.Strategy):
    params = dict(
        symbol="",
    )

    @staticmethod
    def detect_signals(df, symbol, position=None, stop_loss_pct=0.01, take_profit_pct=0.05, bb_period=20, bb_dev=2.0, macd_thresh=0.005):
        if len(df) < 1:
            return None
        df = analyze_indicators(df, bb_period, bb_dev, macd_thresh)
        curr = df.iloc[-1]
        price = curr['close']

        bb_lower = curr['bb_lower']
        bb_mid = curr['bb_mid']
        bb_upper = curr['bb_upper']
        macd_angle = curr['macd_angle']
        macd_close = curr['macd_close']
        macd_signal = curr['macd_signal']


        if not position:
            ### ------- Insert buy logic here ------- ###
            return 'buy'
        else:
            ### ------- Insert sell logic here ------- ###
            return 'sell'

    # Only used for backtesting.
    def next(self):

        # Build a DataFrame from the most recent N bars
        N = 200  # Enough for MACD and BB
        data = {
            'close': [self.datas[0].close[-i] for i in reversed(range(N))],
            'open': [self.datas[0].open[-i] for i in reversed(range(N))],
            'high': [self.datas[0].high[-i] for i in reversed(range(N))],
            'low': [self.datas[0].low[-i] for i in reversed(range(N))],
            'volume': [self.datas[0].volume[-i] for i in reversed(range(N))],
        }
        df = pd.DataFrame(data)

        # Use shared signal logic
        signal = self.detect_signals(df, self.p.symbol, self.position)

        if signal == 'buy' and not self.position:
            self.buy()
        elif signal == 'sell' and self.position:
            self.sell()
