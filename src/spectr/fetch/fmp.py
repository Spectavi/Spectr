import logging
import os
import pandas as pd
import requests
from dotenv import load_dotenv
from .. import cache
from datetime import datetime, timedelta, timezone

from tzlocal import get_localzone

from .data_interface import DataInterface
from ..exceptions import DataApiRateLimitError

load_dotenv()
CFG = cache.load_onboarding_config() or {}

# Prefer the generic DATA_API_KEY environment variable set by the onboarding
# dialog, but fall back to the legacy FMP_API_KEY if present for backwards
# compatibility.  This value is looked up at runtime rather than import time so
# that keys entered in the onboarding UI are respected when the module is
# imported after setup has completed.


def _get_api_key() -> str | None:
    return os.getenv("DATA_API_KEY") or CFG.get("data_key") or os.getenv("FMP_API_KEY")


log = logging.getLogger(__name__)


# FMP only provides data, no broker services.
class FMPInterface(DataInterface):
    def __init__(self) -> None:
        self.api_key = _get_api_key()
        if not self.api_key:
            raise ValueError("DATA_API_KEY not found in environment")

    def _check_rate_limit(self, resp: requests.Response) -> None:
        """Raise DataApiRateLimitError if the response status is 429."""
        if resp.status_code == 429:
            raise DataApiRateLimitError("FMP API rate limit exceeded")

    def fetch_chart_data(
        self, symbol: str, from_date: str, to_date: str, interval: str = "1min"
    ) -> pd.DataFrame:
        # Fetch intraday data
        url = f"https://financialmodelingprep.com/api/v3/historical-chart/{interval}/{symbol}?from_date={from_date}&to_date={to_date}&extended=true&timeseries=390&apikey={self.api_key}"
        resp = requests.get(url)
        self._check_rate_limit(resp)
        data = resp.json()

        if not isinstance(data, list) or not data:
            raise ValueError(f"No data returned from FMP for {symbol}")

        df = pd.DataFrame(data)
        df["datetime"] = pd.to_datetime(df["date"], utc=False)
        df.set_index("datetime", inplace=True)
        # Set timezone to US/Eastern
        df.index = df.index.tz_localize("America/New_York").tz_convert(get_localzone())
        df = df.sort_index()

        df.rename(
            columns={
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
            },
            inplace=True,
        )

        return df[["open", "high", "low", "close", "volume"]]

    def fetch_quote(self, symbol: str, afterhours: bool = False) -> dict:
        """Fetch the latest quote for a symbol from FMP."""
        if afterhours:
            url = f"https://financialmodelingprep.com/api/v4/pre-post-market/{symbol}?apikey={self.api_key}"
        else:
            url = f"https://financialmodelingprep.com/api/v3/quote/{symbol}?apikey={self.api_key}"
        try:
            response = requests.get(url)
            self._check_rate_limit(response)
            response.raise_for_status()
            data = response.json()
            if not data or not isinstance(data, list):
                try:
                    return self.fetch_quote(symbol, not afterhours)
                except Exception as e:
                    raise ValueError(f"No quote data returned for {symbol}")
            log.debug(f"Fetched quote for {symbol}.")
            return data[0]  # return the first (and only) quote object
        except Exception as e:
            log.error(f"Failed to fetch quote for {symbol}: {e}")
            return None

    def fetch_quotes(
        self, symbols: list[str], afterhours: bool = False
    ) -> dict[str, dict | None]:
        """Fetch quotes for multiple symbols using FMP's batch endpoint."""
        if not symbols:
            return {}

        joined = ",".join(symbols)
        if afterhours:
            url = f"https://financialmodelingprep.com/api/v4/pre-post-market/{joined}?apikey={self.api_key}"
        else:
            url = f"https://financialmodelingprep.com/api/v3/quote/{joined}?apikey={self.api_key}"
        try:
            resp = requests.get(url)
            self._check_rate_limit(resp)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                raise ValueError("Invalid batch quote response")
            quotes = {item.get("symbol", "").upper(): item for item in data}
            return {sym.upper(): quotes.get(sym.upper()) for sym in symbols}
        except Exception as exc:
            log.error(f"Failed to fetch quotes for {symbols}: {exc}")
            return {sym.upper(): None for sym in symbols}

    def fetch_chart_data_for_backtest(
        self, symbol: str, from_date: str, to_date: str, interval="1min"
    ) -> pd.DataFrame:
        # Fetch intraday data (limited history on free tier)
        url = f"https://financialmodelingprep.com/api/v3/historical-chart/{interval}/{symbol}?from={from_date}&to={to_date}&apikey={self.api_key}"
        resp = requests.get(url)
        self._check_rate_limit(resp)
        data = resp.json()

        if not isinstance(data, list) or not data:
            raise ValueError(f"No data returned from FMP for {symbol}")

        df = pd.DataFrame(data)
        df["datetime"] = pd.to_datetime(df["date"], utc=True)
        df.set_index("datetime", inplace=True)
        # Set timezone to US/Eastern
        # df.index = df.index.tz_localize("US/Eastern")
        df = df.sort_index()

        df.rename(
            columns={
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
            },
            inplace=True,
        )

        return df[["open", "high", "low", "close", "volume"]]

    def fetch_top_movers(self, limit: int = 10) -> list[dict]:
        """
        Return a list of the day’s *up* movers sorted by %-gain
        Each result dict has at least: symbol, price, changesPercentage.
        """
        url = f"https://financialmodelingprep.com/api/v3/stock_market/gainers?apikey={self.api_key}"
        try:
            resp = requests.get(url, timeout=10)
            self._check_rate_limit(resp)
            data = resp.json()
            log.debug(f"Fetched {len(data)} gainers.")
            # sort numerically just in case
            data = sorted(
                data, key=lambda d: float(d["changesPercentage"]), reverse=True
            )
            log.debug(f"fetched {len(data)} gainers.")
            return data[:limit]
        except Exception as exc:
            log.error(f"Failed to fetch top movers: {exc}")
            return []

    def has_recent_positive_news(self, symbol: str, hours: int = 12) -> bool:
        """
        Return True if the News-Sentiment endpoint contains at least one
        article with *overall_sentiment_score* > 0 in the last *hours*.
        """

        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
            "%Y-%m-%d"
        )
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        url = f"https://financialmodelingprep.com/api/v3/stock_news?tickers={symbol.upper()}&from_date={since}&to_date={now}&apikey={self.api_key}"

        try:
            resp = requests.get(url, timeout=10)
            self._check_rate_limit(resp)
            news = resp.json()
            log.debug(f"Fetched {len(news)} news articles for {symbol} since {since}")
            if len(news) > 0:
                return True

            # TODO: add in sentiment analysis.

            return False
        except Exception as exc:
            log.error(f"news lookup failed for {symbol}: {exc}")
            return False

    def fetch_company_profile(self, symbol: str) -> dict:
        """Fetch profile information such as share float."""
        url = f"https://financialmodelingprep.com/api/v3/profile/{symbol}?apikey={self.api_key}"
        try:
            resp = requests.get(url, timeout=10)
            self._check_rate_limit(resp)
            data = resp.json()
            log.debug(f"Fetched {len(data)} profiles for {symbol}")
            if isinstance(data, list) and data:
                return data[0]
            return {}
        except Exception as exc:
            log.error(f"Failed to fetch profile for {symbol}: {exc}")
            return {}
