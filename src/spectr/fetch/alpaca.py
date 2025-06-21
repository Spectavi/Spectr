import logging
import os

import pandas as pd
from alpaca.trading import (
    TradingClient,
    MarketOrderRequest,
    LimitOrderRequest,
    OrderSide,
    TimeInForce,
    GetOrdersRequest,
    QueryOrderStatus,
)
from dotenv import load_dotenv

from .broker_interface import BrokerInterface, OrderType
from ..utils import is_crypto_symbol

# Loading from .env file, you need to create one and define both ALPACA_API_KEY and ALPACA_SECRET_KEY
load_dotenv()
PAPER_API_KEY = os.getenv("ALPACA_API_KEY_PAPER")
PAPER_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY_PAPER')
API_KEY = os.getenv('ALPACA_API_KEY')
SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')

log = logging.getLogger(__name__)

class AlpacaInterface(BrokerInterface):

    def __init__(self, real_trades: bool = False):
        self._real_trades = real_trades

    @property
    def real_trades(self) -> bool:
        return self._real_trades

    def get_api(self):
        #url = 'https://api.alpaca.markets' if real_trades else 'https://paper-api.alpaca.markets'
        return TradingClient(API_KEY if self.real_trades else PAPER_API_KEY,
                             SECRET_KEY if self.real_trades else PAPER_SECRET_KEY,
                             paper=not self.real_trades)

    # ------------------------------------------------------------------ #
    #  Returns account balance info.
    # ------------------------------------------------------------------ #
    def get_balance(self):
        try:
            acct = self.get_api().get_account()
            return {
                "cash": float(acct.cash) if acct.cash else 0.00,
                "buying_power": float(acct.buying_power) if acct.buying_power else 0.00,
                "portfolio_value": float(acct.portfolio_value) if acct.portfolio_value else 0.00,
            }
        except Exception as exc:
            log.error(f"Failed to fetch account balance: {exc}")
            return {}

    # ------------------------------------------------------------------ #
    #  Returns whether the account has a pending order on the symbol.
    # ------------------------------------------------------------------ #
    def has_pending_order(self, symbol: str) -> bool:
        """True if there is any order for ``symbol`` that is not closed."""
        try:
            tc = self.get_api()
            req = GetOrdersRequest(status=QueryOrderStatus.ALL, symbols=[symbol.upper()])
            orders = tc.get_orders(req)
            for o in orders:
                status = getattr(o, "status", "").lower()
                if status not in {"filled", "canceled", "cancelled", "expired", "rejected"}:
                    return True
            return False
        except Exception as exc:
            log.error(f"has_pending_order error: {exc}")
            return False

    # ------------------------------------------------------------------ #
    #  Returns any pending orders open on the acocunt.
    # ------------------------------------------------------------------ #
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
            tc = self.get_api()

            req = GetOrdersRequest(
                status=QueryOrderStatus.OPEN,     # "open" orders only
                symbols=[symbol.upper()] if symbol else None,
            )
            return tc.get_orders(req)

        except Exception as exc:
            log.error(f"get_pending_orders error: {exc}")
            return []

    # ------------------------------------------------------------------ #
    #  Returns ALL closed orders on the account.
    # ------------------------------------------------------------------ #
    def get_closed_orders(self, real_trades: bool = False) -> pd.DataFrame:
        """
        Return **all closed orders** for the account as a pandas DataFrame.

        Columns
        -------
        id, symbol, qty, side, order_type, filled_avg_price, filled_at,
        submitted_at, status, legs …

        Notes
        -----
        • Alpaca returns *every* historical order unless you page or
          date-filter; for small accounts that's fine.  Adjust the request with
          `after=` / `until=` if you need a time window.
        • If the API call fails, an *empty* DataFrame is returned so callers
          don't crash.
        """
        try:
            api = self.get_api()

            req = GetOrdersRequest(status=QueryOrderStatus.CLOSED)
            orders = api.get_orders(req)  # list[Order]

            if not orders:
                log.warning(f"get_closed_orders returned nothing!")
                return pd.DataFrame()  # nothing closed yet

            # Each Order is a dataclass → convert to dict → DataFrame
            order_dicts = [o.model_dump() for o in orders]
            df = pd.DataFrame(order_dicts)

            # Ensure date columns are proper datetimes
            for col in ("filled_at", "submitted_at", "updated_at", "canceled_at"):
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], utc=True, errors="ignore")

            return df

        except Exception as exc:
            log.error(f"get_closed_orders error: {exc}")
            return pd.DataFrame()

    # ------------------------------------------------------------------ #
    #  EVERY order on the account (open + closed + canceled …)
    # ------------------------------------------------------------------ #
    def get_all_orders(self, real_trades: bool = False) -> pd.DataFrame:
        """
        Fetch *all* orders for the account, across every symbol and status.

        Parameters
        ----------
        real_trades : bool, default False
            • False → paper account
            • True  → live account

        Returns
        -------
        pandas.DataFrame
            Columns include at least:
            id, symbol, qty, side, order_type, status, filled_avg_price,
            submitted_at, filled_at, canceled_at, …
            (Empty DataFrame on error or if no orders exist.)
        """
        try:
            api = self.get_api()
            # Empty request object => no filters → returns every order
            orders = api.get_orders(GetOrdersRequest(status=QueryOrderStatus.ALL))
            log.debug(f"get_all_orders returned {len(orders)} orders")
            return orders
        except Exception as exc:
            log.error(f"get_all_orders error: {exc}")
            return pd.DataFrame()

    # ------------------------------------------------------------------ #
    #  Returns ALL orders (open + closed) for a single symbol
    # ------------------------------------------------------------------ #
    def get_orders_for_symbol(
            self,
            symbol: str,
            real_trades: bool = False
    ) -> pd.DataFrame:
        """
        Return **every order** (open, partially-filled, filled, cancelled …)
        that belongs to *symbol*.

        Parameters
        ----------
        symbol : str
            Ticker symbol (case-insensitive).
        real_trades : bool, default False
            • False → paper account
            • True  → live account

        Returns
        -------
        pandas.DataFrame
            Empty DataFrame on error or when no orders exist.
        """
        try:
            trading = self.get_api()

            req = GetOrdersRequest(symbols=[symbol.upper()])  # no status filter
            orders = trading.get_orders(req)  # list[Order]

            if not orders:
                return pd.DataFrame()

            # convert Order dataclasses to dicts → DataFrame
            df = pd.DataFrame([o.model_dump() for o in orders])

            # parse ISO timestamps into true datetimes
            for col in ("created_at", "filled_at", "submitted_at",
                        "updated_at", "canceled_at"):
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], utc=True, errors="ignore")

            return df

        except Exception as exc:
            log.debug(f"get_orders_for_symbol error: {exc}")
            return pd.DataFrame()

    # ------------------------------------------------------------------ #
    #  Returns whether the account has a position open on the symbol.
    # ------------------------------------------------------------------ #
    def has_position(self, symbol: str) -> bool:
        pos = self.get_position(symbol)
        return bool(pos and float(pos.qty) > 0)

    # ------------------------------------------------------------------ #
    #  Returns ALL open positions for the account.
    # ------------------------------------------------------------------ #
    def get_positions(self):
        try:
            pos = self.get_api().get_all_positions()
            log.debug(f"get_positions: {len(pos)}")
            return pos
        except Exception as exc:
            log.debug(f"Failed to fetch positions: {exc}")
            return []

    # ------------------------------------------------------------------ #
    #  Returns any open position for the symbol on the account.
    # ------------------------------------------------------------------ #
    def get_position(self, symbol: str):
        try:
            pos = self.get_api().get_open_position(symbol.upper())
            log.debug(f"get_position for {symbol}: {len(pos)}")
            return pos
        except Exception:
            log.debug("No position")
            return None

    # ------------------------------------------------------------------ #
    #  Submits an order.
    # ------------------------------------------------------------------ #
    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        quantity: float | None = None,
        limit_price: float | None = None,
        market_price: float | None = None,
    ):
        log.debug(f"Attempting to submit {type.name}...")
        try:
            tc = self.get_api()
            tif = TimeInForce.GTC
            if quantity is not None and not float(quantity).is_integer() and not is_crypto_symbol(symbol):
                tif = TimeInForce.DAY

            if type == OrderType.MARKET:
                order_req = MarketOrderRequest(
                    symbol=symbol.upper(),
                    qty=quantity,
                    side=side.name.lower(),
                    time_in_force=tif,
                )
                price_used = market_price
            else:
                order_req = LimitOrderRequest(
                    symbol=symbol.upper(),
                    qty=quantity,
                    side=side.name.lower(),
                    time_in_force=tif,
                    limit_price=limit_price,
                )
                price_used = limit_price

            tc.submit_order(order_req)
            price_disp = price_used if price_used is not None else "MKT"
            log.info(
                f"ORDER PLACED: {side.name.upper()} {quantity or 1} shares of {symbol.upper()} @ {price_disp}"
            )
        except Exception as exc:
            log.error(f"ORDER FAILED: {exc}")
            raise

    # ------------------------------------------------------------------ #
    #  Cancel an existing open order.
    # ------------------------------------------------------------------ #
    def cancel_order(self, order_id: str) -> bool:
        try:
            api = self.get_api()
            api.cancel_order_by_id(order_id)
            log.info(f"Order cancelled: {order_id}")
            return True
        except Exception as exc:
            log.error(f"Failed to cancel order {order_id}: {exc}")
            return False
