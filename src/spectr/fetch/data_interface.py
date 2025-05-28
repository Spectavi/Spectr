from abc import ABC, abstractmethod
import pandas as pd


class DataInterface(ABC):
    @abstractmethod
    def fetch_chart_data(self, symbol: str, from_date: str, to_date: str) -> pd.DataFrame:
        """Asynchronously fetch recent market data."""
        pass

    @abstractmethod
    def fetch_quote(self, symbol: str) -> dict:
        """Asynchronously fetch recent quote"""
        pass

    @abstractmethod
    def fetch_chart_data_for_backtest(self, symbol: str, from_date: str, to_date: str, interval=None) -> pd.DataFrame:
        """Fetch historical data for backtesting."""
        pass

    @abstractmethod
    def fetch_top_movers(self, limit: int = 10) -> list[dict]:
        """Fetch the top 10 movers for the day."""
        pass

    @abstractmethod
    def has_recent_positive_news(self, symbol: str, hours: int = 12) -> bool:
         # True if FMP has any bullish news for *symbol* in the last *hours*.
        pass
