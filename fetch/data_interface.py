from abc import ABC, abstractmethod
import pandas as pd


class DataInterface(ABC):
    @abstractmethod
    def fetch_data(self, symbol: str, lookback: int = 5000, real_trades: bool = False) -> pd.DataFrame:
        """Asynchronously fetch recent market data."""
        pass

    @abstractmethod
    def fetch_data_for_backtest(self, symbol: str, from_date: str, to_date: str, interval=None) -> pd.DataFrame:
        """Fetch historical data for backtesting."""
        pass
