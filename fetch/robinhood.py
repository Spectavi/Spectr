import os
import logging
import pandas as pd
from datetime import datetime, timedelta
from robin_stocks import robinhood as r
from dotenv import load_dotenv

from fetch.broker_interface import BrokerInterface
from fetch.data_interface import DataInterface

log = logging.getLogger(__name__)
load_dotenv()

# Robinhood credentials (must be stored in .env)
ROBIN_USER = os.getenv("ROBINHOOD_USERNAME")
ROBIN_PASS = os.getenv("ROBINHOOD_PASSWORD")


class RobinhoodInterface(BrokerInterface, DataInterface):
    def __init__(self):
        self.logged_in = False
        self._login()

    def _login(self):
        if not self.logged_in:
            try:
                r.login(ROBIN_USER, ROBIN_PASS)
                self.logged_in = True
                log.debug("Logged in to Robinhood")
            except Exception as e:
                log.error(f"Robinhood login failed: {e}")

    def fetch_data(self, symbol, lookback=5000, real_trades=False):
        end = datetime.now()
        start = end - timedelta(minutes=lookback)
        interval = '5minute'  # Robinhood does not support 1min reliably

        historicals = r.stocks.get_stock_historicals(
            symbol,
            interval=interval,
            span='day',
            bounds='regular'
        )

        if not historicals:
            raise ValueError(f"No data returned for {symbol}")

        df = pd.DataFrame(historicals)
        df['datetime'] = pd.to_datetime(df['begins_at'])
        df.set_index('datetime', inplace=True)

        df = df.rename(columns={
            'open_price': 'open',
            'high_price': 'high',
            'low_price': 'low',
            'close_price': 'close',
            'volume': 'volume'
        }).astype({
            'open': float,
            'high': float,
            'low': float,
            'close': float,
            'volume': int
        })

        return df[['open', 'high', 'low', 'close', 'volume']]

    def fetch_data_for_backtest(self, symbol, from_date, to_date, interval=None):
        df = self.afetch_data(symbol, lookback=10000)  # Robinhood doesn’t support historical by date
        mask = (df.index >= pd.to_datetime(from_date)) & (df.index <= pd.to_datetime(to_date))
        return df.loc[mask]

    def has_pending_order(self, symbol, real_trades=False):
        orders = r.orders.get_all_open_stock_orders()
        for order in orders:
            if order["instrument"].lower().endswith(symbol.lower()):
                return True
        return False

    def has_position(self, symbol, real_trades=False):
        pos = self.get_position(symbol)
        return pos is not None and float(pos.get("quantity", 0)) > 0

    def get_position(self, symbol, real_trades=False):
        holdings = r.account.build_holdings()
        return holdings.get(symbol.upper(), None)

    def submit_order(self, symbol, signal, qty=1, real_trades=False):
        side = 'buy' if signal == 'buy' else 'sell'
        try:
            r.orders.order_buy_market(symbol, qty) if side == 'buy' else r.orders.order_sell_market(symbol, qty)
            log.debug(f"ORDER PLACED: {side.upper()} {qty} shares of {symbol}")
        except Exception as e:
            log.error(f"ORDER FAILED: {e}")
