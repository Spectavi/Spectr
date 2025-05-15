from abc import ABC, abstractmethod
import pandas as pd


class DataInterface(ABC):
    @abstractmethod
    def fetch_chart_data(self, symbol: str, lookback: int = 5000) -> pd.DataFrame:
        """Asynchronously fetch recent market data."""
        pass

    @abstractmethod
    def fetch_quote(self, symbol: str, lookback: int = 5000) -> pd.DataFrame:
        """Asynchronously fetch recent quote"""
        pass

    @abstractmethod
    def fetch_chart_data_for_backtest(self, symbol: str, from_date: str, to_date: str, interval=None) -> pd.DataFrame:
        """Fetch historical data for backtesting."""
        pass
