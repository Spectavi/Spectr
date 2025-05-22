import logging
import os

from alpaca.trading import TradingClient, MarketOrderRequest, OrderSide, TimeInForce, GetOrdersRequest, QueryOrderStatus
from dotenv import load_dotenv

from .broker_interface import BrokerInterface

# Loading from .env file, you need to create one and define both ALPACA_API_KEY and ALPACA_SECRET_KEY
load_dotenv()
API_KEY = os.getenv('ALPACA_API_KEY')
SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')

log = logging.getLogger(__name__)

class AlpacaInterface(BrokerInterface):

    def get_api(self, real_trades=False):
        #url = 'https://api.alpaca.markets' if real_trades else 'https://paper-api.alpaca.markets'
        api = TradingClient(API_KEY, SECRET_KEY, paper=(not real_trades))
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

    def has_pending_order(self, symbol: str, real_trades: bool = False) -> bool:
        """
        True if there is *any* open order for `symbol` (market or limit).
        """
        try:
            tc = self.get_api(real_trades)
            req = GetOrdersRequest(status="open", symbols=[symbol.upper()])
            open_orders = tc.get_orders(req)
            return len(open_orders) > 0
        except Exception as exc:
            log.debug(f"has_pending_order error: {exc}")
            return False

    def get_pending_orders(
        self,
        symbol: str | None = None,
        real_trades: bool = False,
    ):
        """
        Return **all open / partially-filled orders**.

        Parameters
        ----------
        symbol : str | None
            • If given, only that symbol is returned (case-insensitive).
            • If None, all open orders for the account are returned.
        real_trades : bool
            • False (default) → paper account
            • True           → live account

        Returns
        -------
        list[alpaca.trading.models.Order]   (empty list if none or on error)
        """
        try:
            tc = self.get_api(real_trades)

            req = GetOrdersRequest(
                status=QueryOrderStatus.OPEN,     # "open" orders only
                symbols=[symbol.upper()] if symbol else None,
            )
            return tc.get_orders(req)

        except Exception as exc:
            log.debug(f"get_pending_orders error: {exc}")
            return []

    # Return position for symbol, if present.
    def has_position(self, symbol: str, real_trades: bool = False) -> bool:
        pos = self.get_position(symbol, real_trades)
        return bool(pos and float(pos.qty) > 0)

    # Return all open positions.
    def get_positions(self, real_trades: bool = False):
        try:
            return self.get_api(real_trades).get_all_positions()
        except Exception as exc:
            log.debug(f"Failed to fetch positions: {exc}")
            return []

    def get_position(self, symbol: str, real_trades: bool = False):
        try:
            return self.get_api(real_trades).get_open_position(symbol.upper())
        except Exception:
            log.debug("No position")
            return None


    def submit_order(
        self,
        symbol: str,
        side: str,
        quantity: int = 1,
        real_trades: bool = False,
    ):
        try:
            tc = self.get_api(real_trades)
            order_req = MarketOrderRequest(
                symbol=symbol.upper(),
                qty=quantity,
                side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
                time_in_force=TimeInForce.GTC,
            )
            tc.submit_order(order_req)
            log.debug(f"ORDER PLACED: {side.upper()} {quantity} shares of {symbol.upper()}")
        except Exception as exc:
            log.error(f"ORDER FAILED: {exc}")
            raise
