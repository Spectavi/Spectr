import logging
import os
from datetime import datetime

import pandas as pd
import pytz
from alpaca_trade_api import TimeFrame, REST
from alpaca_trade_api.common import URL
from dotenv import load_dotenv

from fetch.broker_interface import BrokerInterface
from fetch.data_interface import DataInterface

# Loading from .env file, you need to create one and define both ALPACA_API_KEY and ALPACA_SECRET_KEY
load_dotenv()
API_KEY = os.getenv('ALPACA_API_KEY')
SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')

log = logging.getLogger(__name__)

class AlpacaInterface(BrokerInterface, DataInterface):

    def get_api(self, real_trades=False):
        url = 'https://api.alpaca.markets' if real_trades else 'https://paper-api.alpaca.markets/v2'
        api = REST(API_KEY, SECRET_KEY, base_url=URL(url))
        return api


    def fetch_chart_data(self, symbol, lookback=5000):
        end = pd.Timestamp.utcnow()
        start = end - pd.Timedelta(minutes=lookback)
        bars = self.get_api(True).get_bars(
            symbol,
            TimeFrame.Minute,
            start=start.isoformat(),
            # end=end.isoformat(),
        ).df
        log.debug("Fetched data for live trading")
        return bars

    def fetch_quote(self, symbol: str) -> dict:
        """Fetch the latest quote (bid/ask/last trade) for a symbol."""
        try:
            quote = self.get_api(True).get_latest_quote(symbol)
            return {
                "symbol": symbol,
                "price": quote.ask_price,  # or use quote.bid_price or last trade
                "timestamp": quote.timestamp.isoformat()
            }
        except Exception as e:
            raise RuntimeError(f"Failed to fetch quote for {symbol}: {e}")

    def fetch_data_for_backtest(self, symbol, from_date, to_date, interval=TimeFrame.Minute):
        start = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=pytz.UTC)
        end = datetime.strptime(to_date, "%Y-%m-%d").replace(tzinfo=pytz.UTC)
        bars = self.get_api(False).get_bars(
            symbol,
            interval,
            start=start.isoformat().replace("+00:00", "Z"),
            end=end.isoformat().replace("+00:00", "Z"),
        ).df
        log.debug("Fetched data for backtest")
        return bars


    def has_pending_order(self, symbol, real_trades=False):
        open_orders = self.get_api(real_trades).list_orders(status='open', symbols=[symbol.upper()])
        return len(open_orders) > 0


    def has_position(self, symbol, real_trades=False):
        try:
            pos = self.get_position(symbol.upper(), real_trades)
            return float(pos.qty) > 0
        except:
            return False


    def get_position(self, symbol, real_trades=False):
        try:
            pos = self.get_api(real_trades).get_position(symbol.upper())
            return pos
        except:
            log.debug("No position")
            return None


    def submit_order(self, symbol, signal, qty=1, real_trades=False):
        side = 'buy' if signal == 'buy' else 'sell'
        try:
            self.get_api(real_trades).submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                type='market',
                time_in_force='gtc'
            )
            log.debug(f"ORDER PLACED: {side.upper()} {qty} shares of {symbol}")
        except Exception as e:
            log.debug(f"ORDER FAILED: {e}")
