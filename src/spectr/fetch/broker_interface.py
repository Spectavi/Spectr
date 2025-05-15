from abc import ABC, abstractmethod
import pandas as pd


class BrokerInterface(ABC):
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
    def submit_order(self, symbol: str, signal: str, qty: int = 1, real_trades: bool = False):
        """Submit a buy/sell order."""
        pass
