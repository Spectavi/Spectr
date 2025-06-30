import os
import logging
import pandas as pd
from datetime import datetime, timedelta, timezone
import types
from robin_stocks import robinhood as r
from dotenv import load_dotenv

from .broker_interface import BrokerInterface, OrderSide, OrderType
from .data_interface import DataInterface

log = logging.getLogger(__name__)
load_dotenv()

# Credentials are supplied via the generic BROKER_* variables for broker usage.
# If Robinhood is also the selected data provider (``DATA_PROVIDER``), allow the
# generic data variables to supply the credentials.  Otherwise fall back to the
# legacy ROBINHOOD_* names for compatibility.
DATA_PROVIDER = os.getenv("DATA_PROVIDER")
ROBIN_USER = (
    os.getenv("BROKER_API_KEY")
    or (os.getenv("DATA_API_KEY") if DATA_PROVIDER == "robinhood" else None)
    or os.getenv("ROBINHOOD_USERNAME")
)
ROBIN_PASS = (
    os.getenv("BROKER_SECRET")
    or (os.getenv("DATA_SECRET") if DATA_PROVIDER == "robinhood" else None)
    or os.getenv("ROBINHOOD_PASSWORD")
)

## WARNING: Doesn't really work unless you already have phone / email MFA enabled. It now uses the app and robin-stocks
## doesn't properly authenticate. Robinhood has sent users stating that API usage is not allowed, so user at your own risk.
## I recommend using FMP for data and Alpaca for broker. It's the most affordable way to get decent intraday 1min data.

class RobinhoodInterface(BrokerInterface, DataInterface):
    def __init__(self, real_trades: bool = True):
        self._real_trades = real_trades
        self.logged_in = False
        self._login()

    @property
    def real_trades(self) -> bool:
        return self._real_trades

    def _login(self):
        if not self.logged_in:
            try:
                r.login(ROBIN_USER, ROBIN_PASS)
                self.logged_in = True
                log.debug("Logged in to Robinhood")
            except Exception as e:
                log.error(f"Robinhood login failed: {e}")

    # ------------- DataInterface methods -------------

    def fetch_chart_data(self, symbol: str, from_date: str, to_date: str) -> pd.DataFrame:
        # Robinhood supports intervals: 5minute, 10minute, day, week
        # We'll use 5minute as closest to 1min
        historicals = r.stocks.get_stock_historicals(
            symbol,
            interval="5minute",
            span="week"
        )
        if not historicals:
            raise ValueError(f"No data returned for {symbol}")
        df = pd.DataFrame(historicals)
        df['datetime'] = pd.to_datetime(df['begins_at'])
        df.set_index('datetime', inplace=True)
        df = df.sort_index()
        df = df.rename(columns={
            'open_price': 'open',
            'high_price': 'high',
            'low_price': 'low',
            'close_price': 'close',
            'volume': 'volume'
        })
        return df[['open', 'high', 'low', 'close', 'volume']]

    def fetch_quote(self, symbol: str) -> dict:
        quote = r.stocks.get_quotes(symbol)
        if not quote or not isinstance(quote, list):
            raise ValueError(f"No quote data returned for {symbol}")
        return quote[0]

    def fetch_chart_data_for_backtest(self, symbol: str, from_date: str, to_date: str, interval=None) -> pd.DataFrame:
        # Use the same as fetch_chart_data, but allow interval override
        interval = interval or "5minute"
        historicals = r.stocks.get_stock_historicals(
            symbol,
            interval=interval,
            span="year"
        )
        if not historicals:
            raise ValueError(f"No data returned for {symbol}")
        df = pd.DataFrame(historicals)
        df['datetime'] = pd.to_datetime(df['begins_at'])
        df.set_index('datetime', inplace=True)
        df = df.sort_index()
        df = df.rename(columns={
            'open_price': 'open',
            'high_price': 'high',
            'low_price': 'low',
            'close_price': 'close',
            'volume': 'volume'
        })
        return df[['open', 'high', 'low', 'close', 'volume']]

    def fetch_top_movers(self, limit: int = 10) -> list[dict]:
        # Robinhood does not have a direct "top movers" endpoint.
        # We'll use the "100 most popular" and sort by percent change.
        movers = r.stocks.get_most_popular()
        quotes = r.stocks.get_quotes([m['symbol'] for m in movers])
        for m, q in zip(movers, quotes):
            try:
                m['price'] = float(q['last_trade_price'])
                m['changesPercentage'] = (
                    (float(q['last_trade_price']) - float(q['previous_close'])) /
                    float(q['previous_close']) * 100
                )
            except Exception:
                m['price'] = None
                m['changesPercentage'] = None
        movers = [m for m in movers if m['changesPercentage'] is not None]
        movers = sorted(movers, key=lambda d: d['changesPercentage'], reverse=True)
        return movers[:limit]

    def has_recent_positive_news(self, symbol: str, hours: int = 12) -> bool:
        # Robinhood news does not provide sentiment, so just check for recent news
        news = r.stocks.get_news(symbol)
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        for article in news:
            published = pd.to_datetime(article['published_at'])
            if published > since:
                return True
        return False

    def fetch_company_profile(self, symbol: str) -> dict:
        """Return basic company info. Robinhood does not expose float shares."""
        try:
            profile = r.stocks.get_fundamentals(symbol)
            if isinstance(profile, list) and profile:
                return profile[0]
            return {}
        except Exception as exc:
            log.debug(f"profile lookup failed for {symbol}: {exc}")
            return {}

    # ------------- BrokerInterface methods -------------

    def get_balance(self):
        """Return basic account metrics."""
        try:
            profile = r.profiles.load_account_profile()
            return {
                "cash": float(profile.get("cash", 0.0)),
                "buying_power": float(profile.get("buying_power", 0.0)),
                "portfolio_value": float(profile.get("equity", 0.0)),
            }
        except Exception as exc:
            log.error(f"Failed to fetch account balance: {exc}")
            return {}

    def has_pending_order(self, symbol: str) -> bool:
        orders = r.orders.get_all_open_stock_orders()
        for order in orders:
            if order["instrument"].lower().endswith(symbol.lower()):
                return True
        return False

    def get_pending_orders(self, symbol: str) -> pd.DataFrame:
        try:
            orders = r.orders.get_all_open_stock_orders()
            if symbol:
                orders = [o for o in orders if o["instrument"].lower().endswith(symbol.lower())]
            return pd.DataFrame(orders)
        except Exception as exc:
            log.error(f"Failed to fetch pending orders: {exc}")
            return pd.DataFrame()

    def get_closed_orders(self) -> pd.DataFrame:
        try:
            orders = r.orders.get_all_stock_orders()
            closed = [o for o in orders if o.get("state") in ("filled", "cancelled", "rejected", "failed")]
            return pd.DataFrame(closed)
        except Exception as exc:
            log.error(f"Failed to fetch closed orders: {exc}")
            return pd.DataFrame()

    def get_all_orders(self) -> pd.DataFrame:
        try:
            orders = r.orders.get_all_stock_orders()
            return pd.DataFrame(orders)
        except Exception as exc:
            log.error(f"Failed to fetch orders: {exc}")
            return pd.DataFrame()

    def get_orders_for_symbol(self, symbol: str) -> pd.DataFrame:
        try:
            orders = r.orders.get_all_stock_orders()
            orders = [o for o in orders if o["instrument"].lower().endswith(symbol.lower())]
            return pd.DataFrame(orders)
        except Exception as exc:
            log.error(f"Failed to fetch orders for {symbol}: {exc}")
            return pd.DataFrame()

    def has_position(self, symbol: str) -> bool:
        pos = self.get_position(symbol)
        if not pos:
            return False
        return float(getattr(pos, "qty", pos.get("quantity", 0))) > 0

    def get_position(self, symbol: str):
        for pos in self.get_positions():
            if getattr(pos, "symbol", "").upper() == symbol.upper():
                return pos
        return None

    def get_positions(self):
        try:
            holdings = r.account.build_holdings()
            positions = []
            for sym, data in holdings.items():
                qty = float(data.get("quantity", 0))
                pos = types.SimpleNamespace(symbol=sym.upper(), qty=qty, **data)
                positions.append(pos)
            return positions
        except Exception as exc:
            log.debug(f"Failed to fetch positions: {exc}")
            return []

    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        quantity: float | None = None,
        limit_price: float | None = None,
        market_price: float | None = None,
    ):
        try:
            if type != OrderType.MARKET:
                log.error("RobinhoodInterface only supports market orders")
                return None
            if side == OrderSide.BUY:
                order = r.orders.order_buy_market(symbol, quantity or 1)
            else:
                order = r.orders.order_sell_market(symbol, quantity or 1)
            price_disp = market_price if market_price is not None else "MKT"
            log.debug(
                f"ORDER PLACED: {side.name.upper()} {quantity or 1} shares of {symbol} @ {price_disp}"
            )
            return order
        except Exception as exc:
            log.error(f"ORDER FAILED: {exc}")
            
    def cancel_order(self, order_id: str) -> bool:
        try:
            r.orders.cancel_stock_order(order_id)
            log.debug(f"Cancelled order {order_id}")
            return True
        except Exception as exc:
            log.error(f"Failed to cancel order {order_id}: {exc}")
            return False
