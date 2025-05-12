import os
import pandas as pd
import requests
from dotenv import load_dotenv
import pytz

from fetch.data_interface import DataInterface

load_dotenv()
FMP_API_KEY = os.getenv("FMP_API_KEY")

# FMP only provides data, no broker services.
class FMPInterface(DataInterface):
    def __init__(self):
        if not FMP_API_KEY:
            raise ValueError("FMP_API_KEY not found in environment")

    def fetch_chart_data(self, symbol: str, lookback: int = 5000) -> pd.DataFrame:
        # Fetch intraday data (limited history on free tier)
        url = f"https://financialmodelingprep.com/api/v3/historical-chart/1min/{symbol}?apikey={FMP_API_KEY}"
        resp = requests.get(url)
        data = resp.json()

        if not isinstance(data, list) or not data:
            raise ValueError(f"No data returned from FMP for {symbol}")

        df = pd.DataFrame(data)
        df['datetime'] = pd.to_datetime(df['date'])
        df.set_index('datetime', inplace=True)
        # Set timezone to US/Eastern
        df.index = df.index.tz_localize("US/Eastern")
        df = df.sort_index()

        df.rename(columns={
            'open': 'open',
            'high': 'high',
            'low': 'low',
            'close': 'close',
            'volume': 'volume'
        }, inplace=True)

        return df[['open', 'high', 'low', 'close', 'volume']]

    def fetch_quote(self, symbol: str) -> dict:
        """Fetch the latest quote for a symbol from FMP."""
        url = f"https://financialmodelingprep.com/api/v3/quote/{symbol}?apikey={FMP_API_KEY}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            if not data or not isinstance(data, list):
                raise ValueError(f"No quote data returned for {symbol}")
            return data[0]  # return the first (and only) quote object
        except Exception as e:
            raise RuntimeError(f"Failed to fetch quote for {symbol}: {e}")

    def fetch_data_for_backtest(self, symbol: str, from_date: str, to_date: str, interval=None) -> pd.DataFrame:
        df = self.afetch_data(symbol)
        df = df[(df.index >= pd.to_datetime(from_date)) & (df.index <= pd.to_datetime(to_date))]
        return df


import backtrader as bt
import requests
import pandas as pd

class FMPDataFeed(bt.feeds.DataBase):
    lines = ('open', 'high', 'low', 'close', 'volume')
    params = (('symbol', None), ('interval', '1min'), ('apikey', FMP_API_KEY), ('maxlen', 1000))

    def start(self):
        super().start()
        self.bars = self._fetch_data()
        self.idx = 0

    def _fetch_data(self):
        url = f"https://financialmodelingprep.com/api/v3/historical-chart/{self.p.interval}/{self.p.symbol}?apikey={self.p.apikey}"
        r = requests.get(url)
        r.raise_for_status()
        data = r.json()

        if not isinstance(data, list) or not data:
            raise ValueError(f"No data returned from FMP for {self.p.symbol}")

        df = pd.DataFrame(data)
        df["datetime"] = pd.to_datetime(df["date"])
        df = df.set_index("datetime").sort_index()
        return df

    def _load(self):
        if self.idx >= len(self.bars):
            return False

        row = self.bars.iloc[self.idx]
        self.datetime[0] = bt.date2num(self.bars.index[self.idx])
        self.open[0] = row['open']
        self.high[0] = row['high']
        self.low[0] = row['low']
        self.close[0] = row['close']
        self.volume[0] = row['volume']
        self.idx += 1
        return True

