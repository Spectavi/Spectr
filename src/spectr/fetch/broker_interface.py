from abc import ABC, abstractmethod, abstractproperty
from enum import Enum

import pandas as pd


class OrderType(Enum):
    MARKET = 1
    LIMIT = 2
    # STOP_LIMIT = 3  # Not implemented yet
    # TRAILING_STOP = 4  # Not implemented yet


class OrderSide(Enum):
    BUY = 1
    SELL = 2


class OrderSubmission:
    symbol: str
    side: OrderSide


class BrokerInterface(ABC):

    @property
    @abstractmethod
    def real_trades(self) -> bool:
        """True when the interface talks to a live-money account."""
        raise NotImplementedError

    @abstractmethod
    def get_balance(self):
        """Return cash and portfolio metrics for the current amount."""
        pass

    @abstractmethod
    def has_pending_order(self, symbol: str) -> bool:
        """Check if there's a pending order."""
        pass

    @abstractmethod
    def get_pending_orders(self, symbol: str) -> pd.DataFrame:
        """Gets all pending orders."""
        pass

    @abstractmethod
    def get_closed_orders(self) -> pd.DataFrame:
        """Gets all closed orders."""
        pass

    @abstractmethod
    def get_all_orders(self) -> pd.DataFrame:
        """Gets all orders on an account."""
        pass

    @abstractmethod
    def get_orders_for_symbol(self, symbol: str) -> pd.DataFrame:
        """Gets all orders for a given symbol."""
        pass

    @abstractmethod
    def has_position(self, symbol: str) -> bool:
        """Check if you currently hold the stock."""
        pass

    @abstractmethod
    def get_position(self, symbol: str):
        """Get details of the current position (or None)."""
        pass

    @abstractmethod
    def get_positions(self):
        """Get details of all current positions (or None)."""
        pass

    @abstractmethod
    def fetch_quote(self, symbol: str) -> dict:
        """Fetch a real-time quote for *symbol* from the broker."""
        pass

    @abstractmethod
    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        quantity: float | None = None,
        limit_price: float | None = None,
        market_price: float | None = None,
        extended_hours: bool | None = None,
    ):
        """Submit a buy/sell order and return the resulting order object."""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order by its unique id. Returns True on success."""
        pass
