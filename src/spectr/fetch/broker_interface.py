from abc import ABC, abstractmethod
import pandas as pd


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
    def submit_order(self, symbol: str, side: str, quantity: int = 1, real_trades: bool = False):
        """Submit a buy/sell order."""
        pass
