import os
import pandas as pd
import requests
from dotenv import load_dotenv

from fetch.data_interface import DataInterface

load_dotenv()
FMP_API_KEY = os.getenv("FMP_API_KEY")

# FMP only provides data, no broker services.
class FMPInterface(DataInterface):
    def __init__(self):
        if not FMP_API_KEY:
            raise ValueError("FMP_API_KEY not found in environment")

    def fetch_data(self, symbol: str, lookback: int = 5000, real_trades: bool = False) -> pd.DataFrame:
        # Fetch intraday data (limited history on free tier)
        url = f"https://financialmodelingprep.com/api/v3/historical-chart/1min/{symbol}?apikey={FMP_API_KEY}"
        resp = requests.get(url)
        data = resp.json()

        if not isinstance(data, list) or not data:
            raise ValueError(f"No data returned from FMP for {symbol}")

        df = pd.DataFrame(data)
        df['datetime'] = pd.to_datetime(df['date'])
        df.set_index('datetime', inplace=True)
        df = df.sort_index()

        df.rename(columns={
            'open': 'open',
            'high': 'high',
            'low': 'low',
            'close': 'close',
            'volume': 'volume'
        }, inplace=True)

        return df[['open', 'high', 'low', 'close', 'volume']]

    def fetch_data_for_backtest(self, symbol: str, from_date: str, to_date: str, interval=None) -> pd.DataFrame:
        df = self.afetch_data(symbol)
        df = df[(df.index >= pd.to_datetime(from_date)) & (df.index <= pd.to_datetime(to_date))]
        return df
