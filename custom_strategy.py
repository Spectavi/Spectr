import pandas as pd
import backtrader as bt

from metrics import analyze_indicators
from utils import log, log_signal


class SignalStrategy(bt.Strategy):
    params = (
        ('symbol', ''),
        ('macd_thresh', 0.005),
        ('bb_period', 100),
        ('bb_dev', 2.0),
        ('stop_loss_pct', 0.01),
        ('take_profit_pct', 0.05),
    )

    def __init__(self):
        self.buy_signals = []
        self.sell_signals = []
        self.macd = bt.indicators.MACD(self.data)
        self.bb = bt.indicators.BollingerBands(self.data.close, period=self.p.bb_period, devfactor=self.p.bb_dev)

    @staticmethod
    def detect_signals(df, symbol, position=None, stop_loss_pct=0.01, take_profit_pct=0.05, bb_period=20, bb_dev=2.0,
                       macd_thresh=0.005):
        if len(df) < 1:
            return None

        curr = df.iloc[-1]
        price = curr['close']

        bb_angle = curr.get('bb_angle')
        bb_lower = curr.get('bb_lower')
        bb_mid = curr.get('bb_mid')
        bb_upper = curr.get('bb_upper')
        macd_angle = curr.get('macd_angle')
        macd_close = curr.get('macd_close')
        macd_signal = curr.get('macd_signal')
        is_macd_crossover = True if curr.get('macd_crossover') == 'buy' else False
        is_macd_crossunder = True if curr.get('macd_crossover') == 'sell' else False

        signal = None
        if not position:
            ### ------- Insert buy logic here ------- ###
            signal = 'buy'
            raise NotImplementedError
        else:
            ### ------- Insert sell logic here ------- ###
            signal = 'sell'
            raise NotImplementedError

        return {
            'signal': signal,
            'price': price,
        }

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
        signal = self.detect_signals(df, self.p.symbol, self.position, stop_loss_pct=self.p.stop_loss_pct,
                                     take_profit_pct=self.p.take_profit_pct, bb_period=self.p.bb_period,
                                     bb_dev=self.p.bb_dev, macd_thresh=self.p.macd_thresh)

        if signal == 'buy' and not self.position:
            self.buy()
        elif signal == 'sell' and self.position:
            self.sell()
            self.buy_signals.append({
                'type': 'buy',
                'time': self.datas[0].datetime.datetime(0),
                'price': self.datas[0].close[0],
            })
