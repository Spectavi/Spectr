from abc import ABC, abstractmethod
from enum import Enum

import pandas as pd


class OrderType(Enum):
    MARKET = 1
    LIMIT = 2
    STOP_LIMIT = 3
    TRAILING_STOP = 4

class OrderSide(Enum):
    BUY = 1
    SELL = 2

class OrderSubmission:
    symbol: str
    side: OrderSide

class BrokerInterface(ABC):
    @abstractmethod
    def get_balance(self, real_trades: bool = False):
        """ Return cash and portfolio metrics for the current amount. """
        pass

    @abstractmethod
    def has_pending_order(self, symbol: str, real_trades: bool = False) -> bool:
        """Check if there's a pending order."""
        pass

    @abstractmethod
    def get_pending_orders(self, symbol: str, real_trades: bool = False) -> pd.DataFrame:
        """Gets all pending orders."""
        pass

    @abstractmethod
    def get_closed_orders(self, real_trades: bool = False) -> pd.DataFrame:
        """Gets all closed orders."""
        pass

    @abstractmethod
    def get_all_orders(self, real_trades: bool = False) -> list:
        """Gets all orders on an account."""
        pass

    @abstractmethod
    def get_orders_for_symbol(self, symbol: str, real_trades: bool = False) -> pd.DataFrame:
        """Gets all orders for a given symbol."""
        pass

    @abstractmethod
    def has_position(self, symbol: str, real_trades: bool = False) -> bool:
        """Check if you currently hold the stock."""
        pass

    @abstractmethod
    def get_position(self, symbol: str, real_trades: bool = False):
        """Get details of the current position (or None)."""
        pass

    @abstractmethod
    def get_positions(self, real_trades: bool = False):
        """Get details of all current positions (or None)."""
        pass

    @abstractmethod
    def submit_order(self, symbol: str, side: OrderSide, type: OrderType, quantity: float = 1.0, real_trades: bool = False):
        """Submit a buy/sell order."""
        pass
    