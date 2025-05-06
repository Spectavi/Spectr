import pandas as pd
import time
import argparse
from datetime import datetime

import pytz
from alpaca_trade_api.common import URL
from alpaca_trade_api.rest import REST, TimeFrame
from pandas.errors import DataError
from playsound import playsound
import os
import csv
import backtrader as bt

from custom_strategy import CustomStrategy
from metrics import analyze_indicators
from utils import log_signal, log

# --- SOUND PATHS ---
BUY_SOUND_PATH = 'buy.mp3'
SELL_SOUND_PATH = 'sell.mp3'

LOOKBACK_MINUTES = 200
REFRESH_INTERVAL = 60  # seconds

def fetch_data(api, symbol, lookback=200):
    end = pd.Timestamp.utcnow()
    start = end - pd.Timedelta(minutes=lookback)
    bars = api.get_bars(
        symbol,
        TimeFrame.Minute,
        start=start.isoformat(),
        #end=end.isoformat(),
    ).df
    print("Fetched data")
    return bars

def fetch_data_for_backtest(api, symbol, from_date, to_date, interval=TimeFrame.Minute):
    start = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=pytz.UTC)
    end = datetime.strptime(to_date, "%Y-%m-%d").replace(tzinfo=pytz.UTC)
    bars = api.get_bars(
        symbol,
        interval,
        start=start.isoformat().replace("+00:00", "Z"),
        end=end.isoformat().replace("+00:00", "Z"),
    ).df
    return bars


def has_pending_order():
    open_orders = API.list_orders(status='open', symbols=[SYMBOL])
    return len(open_orders) > 0


def has_position():
    try:
        pos = API.get_position(SYMBOL)
        return float(pos.qty) > 0
    except:
        return False


def get_position():
    try:
        pos = API.get_position(SYMBOL)
        return pos
    except:
        return None


def submit_order(symbol, signal, qty=1):
    side = 'buy' if signal == 'buy' else 'sell'
    try:
        API.submit_order(
            symbol=symbol,
            qty=qty,
            side=side,
            type='market',
            time_in_force='gtc'
        )
        print(f"ORDER PLACED: {side.upper()} {qty} shares of {symbol}")
    except Exception as e:
        print(f"ORDER FAILED: {e}")

# --- Backtest Function ---
class CommInfoFractional(bt.CommissionInfo):
    def getsize(self, price, cash):
        '''Returns fractional size for cash operation @price'''
        return self.p.leverage * (cash / price)

def run_backtest(symbol, from_date, to_date, interval, macd_fast, macd_slow, macd_signal, bb_period, bb_stddev, macd_thresh):
    cerebro = bt.Cerebro()
    cerebro.addstrategy(CustomStrategy, symbol)

    #df = yf.download(symbol, start=from_date, end=to_date, interval=interval)
    df = fetch_data_for_backtest(API, symbol, from_date, to_date)
    df.dropna(inplace=True)
    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)

    cerebro.broker.setcash(10000.0)
    cerebro.broker.addcommissioninfo(CommInfoFractional())
    cerebro.broker.setcommission(commission=0.00)
    cerebro.addsizer(bt.sizers.AllInSizer, percents=90)

    print(f"Starting Portfolio Value: {cerebro.broker.getvalue():.2f}")
    cerebro.run()
    print(f"Final Portfolio Value: {cerebro.broker.getvalue():.2f}")
    cerebro.plot()


# --- Monitor Function ---
def monitor(symbol, macd_thresh, bb_period, bb_dev, api, real_trades):
    print(f"Monitoring {symbol} | Trading Mode: {'LIVE' if real_trades else 'PAPER'}")
    while True:
        try:
            df = fetch_data(api, symbol, LOOKBACK_MINUTES)
            df.dropna(inplace=True)
            if df.empty:
                raise DataError("No data returned.")
            log("Analyzing indicators")
            print(f"{df}")
            df = analyze_indicators(df, bb_period, bb_dev, macd_thresh)
            log("Detecting signals")
            signal = CustomStrategy.detect_signals(df, symbol, get_position())
            latest = df.iloc[-1]

            print(f"\n[{datetime.utcnow().strftime('%H:%M:%S')}] {symbol}")
            print(f"Price: {latest['close']:.2f} | MACD: {latest['macd']:.4f} | Signal: {latest['macd_signal']:.4f}")
            print(f"Bollinger Bands: {latest['bb_lower']:.2f} - {latest['bb_upper']:.2f}")

            if signal:
                if has_pending_order():
                    print("Pending order exists. Skipping new order.")
                elif signal == 'buy' and has_position():
                    print("Already in position. Skipping BUY.")
                elif signal == 'sell' and not has_position():
                    print("No position to sell. Skipping SELL.")
                else:
                    print(f">>> {signal.upper()} SIGNAL")
                    log_signal(symbol, signal, latest['close'])
                    #playsound(BUY_SOUND_PATH if signal == 'buy' else SELL_SOUND_PATH)
                    submit_order(symbol, signal, qty=100)

        except KeyboardInterrupt:
            print("\nStopped live tracking.")
        except DataError as e:
            print(f"\n{e}")
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(REFRESH_INTERVAL)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", type=str, required=True, help="Ticker symbol (e.g. AAPL)")
    parser.add_argument("--macd_thresh", type=float, default=0.05, help="MACD threshold")
    parser.add_argument("--bb_period", type=int, default=20, help="Bollinger Band period")
    parser.add_argument("--bb_dev", type=float, default=2.0, help="Bollinger Band std dev")
    parser.add_argument("--real-trades", action='store_true', help="Enable live trading (vs paper)")
    parser.add_argument('--interval', default='1m')
    parser.add_argument('--mode', choices=['live', 'backtest'], required=True)
    parser.add_argument('--from_date', default='2025-04-17')
    parser.add_argument('--to_date', default='2025-04-21')
    parser.add_argument('--stop_loss_pct', type=float, default=0.01, help="Stop loss pct")
    parser.add_argument('--take_profit_pct', type=float, default=0.05, help="Take profit pct")
    args = parser.parse_args()

    BASE_URL = 'https://api.alpaca.markets' if args.real_trades else 'https://paper-api.alpaca.markets/v2'
    API_KEY = 'PKFKJ56I8W8GYS6N5MNF'
    SECRET_KEY = 'x9bmTsqRCHHpXlMJkWVFWVR7DfgjNXtD2QScqDbj'
    API = REST(API_KEY, SECRET_KEY, base_url=URL(BASE_URL))

    SYMBOL = args.symbol.upper()

    if args.mode == 'live':
        monitor(
            symbol=SYMBOL,
            macd_thresh=args.macd_thresh,
            bb_period=args.bb_period,
            bb_dev=args.bb_dev,
            api=API,
            real_trades=args.real_trades
        )
    elif args.mode == 'backtest':
        run_backtest(
            symbol=SYMBOL,
            from_date=args.from_date,
            to_date=args.to_date,
            interval=args.interval,
            macd_thresh=args.macd_thresh,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9,
            bb_period=args.bb_period,
            bb_stddev=args.bb_dev,
        )
