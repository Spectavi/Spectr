import logging
import os
from datetime import datetime

import pandas as pd
import pytz
from alpaca_trade_api import TimeFrame, REST
from alpaca_trade_api.common import URL
from dotenv import load_dotenv

from .broker_interface import BrokerInterface

# Loading from .env file, you need to create one and define both ALPACA_API_KEY and ALPACA_SECRET_KEY
load_dotenv()
API_KEY = os.getenv('ALPACA_API_KEY')
SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')

log = logging.getLogger(__name__)

class AlpacaInterface(BrokerInterface):

    def get_api(self, real_trades=False):
        url = 'https://api.alpaca.markets' if real_trades else 'https://paper-api.alpaca.markets'
        api = REST(API_KEY, SECRET_KEY, base_url=URL(url))
        return api

    def get_balance(self, real_trades: bool = False):
        try:
            acct = self.get_api(real_trades).get_account()
            return {
                "cash": float(acct.cash) if acct.cash else 0.00,
                "buying_power": float(acct.buying_power) if acct.buying_power else 0.00,
                "portfolio_value": float(acct.portfolio_value) if acct.portfolio_value else 0.00,
            }
        except Exception as exc:
            log.debug(f"Failed to fetch account balance: {exc}")
            return {}

    def has_pending_order(self, symbol, real_trades=False):
        open_orders = self.get_api(real_trades).list_orders(status='open', symbols=[symbol.upper()])
        return len(open_orders) > 0

    # Return position for symbol, if present.
    def has_position(self, symbol, real_trades=False):
        try:
            pos = self.get_position(symbol.upper(), real_trades)
            return float(pos.qty) > 0
        except:
            return False

    # Return all open positions.
    def get_positions(self, real_trades: bool = False):
        try:
            return self.get_api(real_trades).list_positions()
        except Exception as exc:
            log.debug(f"Failed to fetch positions: {exc}")
            return []

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
