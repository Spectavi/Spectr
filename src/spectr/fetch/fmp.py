import logging
import os
import pandas as pd
import requests
from dotenv import load_dotenv
from .. import cache
from datetime import datetime, timedelta, timezone, date

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
        # Fetch extended intryaday history via FMP intraday endpoints.
        # Chunk requests to avoid server-side limits and large payloads, and
        # fall back across multiple endpoints in case one is unavailable.
        timeframe = interval or "1min"
        start_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
        # Keep chunks small to limit pagination depth; adjust dynamically if we
        # get stuck.
        if timeframe == "1min":
            default_chunk_days = 10
        elif timeframe == "5min":
            default_chunk_days = 14
        else:
            default_chunk_days = 90

        frames = []
        errors: list[str] = []

        def _parse_payload(payload):
            """Return list payload (or empty list) and the original object."""
            original = payload
            if isinstance(payload, dict):
                for key in ("results", "historical", "data", "items", "intraday", "prices"):
                    if key in payload:
                        payload = payload[key]
                        break
            if not isinstance(payload, list):
                return [], original
            return payload, original

        def _parse_datetime_column(df: pd.DataFrame) -> pd.DataFrame:
            """Coerce whatever datetime column is present into the index."""
            dt_col = None
            for cand in ("date", "datetime", "timestamp", "time"):
                if cand in df.columns:
                    dt_col = cand
                    break
            if dt_col is None:
                log.warning(f"No datetime column found in intraday payload columns={df.columns.tolist()}")
                return pd.DataFrame()
            if dt_col == "timestamp":
                df["datetime"] = pd.to_datetime(df[dt_col], unit="s", utc=True)
            else:
                df["datetime"] = pd.to_datetime(df[dt_col], utc=True, errors="coerce")
            df = df.dropna(subset=["datetime"])
            df.set_index("datetime", inplace=True)
            return df

        cur = start_dt
        chunk_days = default_chunk_days
        while cur <= end_dt:
            chunk_end = min(cur + timedelta(days=chunk_days - 1), end_dt)
            # Hard cap pagination per chunk to avoid runaway loops when the API
            # keeps returning the same page.
            max_pages = 50 if timeframe == "1min" else 20
            urls = [
                # Prefer premium intraday first.
                f"https://financialmodelingprep.com/api/v4/historical-price-full/"
                f"{symbol}?from={cur}&to={chunk_end}&timeframe={timeframe}&limit=50000&apikey={self.api_key}",
                f"https://financialmodelingprep.com/api/v4/historical-price/"
                f"{symbol}?from={cur}&to={chunk_end}&timeframe={timeframe}&limit=50000&apikey={self.api_key}",
                # Fallback to v3 intraday with explicit timeseries + extended flags (often limited).
                f"https://financialmodelingprep.com/api/v3/historical-chart/"
                f"{timeframe}/{symbol}?from={cur}&to={chunk_end}&extended=true&timeseries=50000&apikey={self.api_key}",
            ]

            chunk_df = pd.DataFrame()
            for url in urls:
                # Paginate backwards if needed to cover the full chunk window.
                page = 0
                frames_page = []
                prev_earliest: date | None = None
                repeat_count = 0
                stopped_due_to_limit = False
                stopped_due_to_stall = False
                partial_chunk = None
                while True:
                    paged_url = f"{url}&page={page}"
                    resp = requests.get(paged_url, timeout=15)
                    self._check_rate_limit(resp)
                    payload, original = _parse_payload(resp.json())

                    if not payload:
                        # No more data on this URL.
                        if page == 0:
                            errors.append(str(original))
                        break

                    df = pd.DataFrame(payload)
                    df = _parse_datetime_column(df)
                    if df.empty:
                        break

                    df = df.sort_index()
                    earliest = df.index.min().date()

                    # Abort if paging is not moving the window earlier or we hit the cap.
                    if prev_earliest is not None and earliest >= prev_earliest:
                        repeat_count += 1
                        if repeat_count >= 3:
                            log.warning(
                                "Stopping pagination for %s (%s→%s, timeframe=%s) at page %s "
                                "because earliest date %s is not progressing after %s repeats (prev %s)",
                                symbol,
                                cur,
                                chunk_end,
                                timeframe,
                                page,
                                earliest,
                                repeat_count,
                                prev_earliest,
                            )
                            errors.append(f"stuck paging {url} page={page} earliest={earliest}")
                            stopped_due_to_stall = True
                            break
                    if page >= max_pages:
                        log.warning(
                            "Stopping pagination for %s (%s→%s, timeframe=%s) at page limit %s",
                            symbol,
                            cur,
                            chunk_end,
                            timeframe,
                            max_pages,
                        )
                        errors.append(f"page limit {url} page={page}")
                        stopped_due_to_limit = True
                        break

                    frames_page.append(df)
                    prev_earliest = earliest
                    if prev_earliest != earliest:
                        repeat_count = 0

                    # Stop paging if we've reached or passed the chunk start.
                    if earliest <= cur:
                        break
                    page += 1

                if frames_page:
                    chunk_df = pd.concat(frames_page).sort_index()
                    earliest_chunk = chunk_df.index.min().date()
                    if earliest_chunk > cur and (stopped_due_to_limit or stopped_due_to_stall):
                        partial_chunk = chunk_df
                        log.warning(
                            "Incomplete chunk for %s (%s→%s, timeframe=%s): earliest %s > chunk start (keeping partial data)",
                            symbol,
                            cur,
                            chunk_end,
                            timeframe,
                            earliest_chunk,
                        )
                        errors.append(
                            f"incomplete chunk {url} earliest={earliest_chunk} > {cur}"
                        )
                        chunk_df = pd.DataFrame()
                        continue
                    break

                if chunk_df.empty and partial_chunk is not None:
                    # Fall back to the best partial data we fetched on this URL.
                    chunk_df = partial_chunk

            if chunk_df.empty:
                log.debug(
                    f"No intraday data chunk for {symbol} "
                    f"({cur}→{chunk_end}, timeframe={timeframe}); "
                    f"server responses: {errors[-len(urls):]}"
                )
                # Retry with a smaller chunk if possible before advancing.
                if chunk_days > 1:
                    chunk_days = max(1, chunk_days // 2)
                    log.info(
                        "Retrying %s (%s→%s) with smaller chunk window=%sd",
                        symbol,
                        cur,
                        chunk_end,
                        chunk_days,
                    )
                    continue
                cur = chunk_end + timedelta(days=1)
                chunk_days = default_chunk_days
                continue

            frames.append(chunk_df)
            cur = chunk_end + timedelta(days=1)
            chunk_days = default_chunk_days

        if not frames:
            if errors:
                log.error(
                    f"No intraday data returned from FMP for {symbol} "
                    f"({from_date}→{to_date}, timeframe={timeframe}); "
                    f"server responses: {errors}"
                )
            else:
                log.warning(
                    f"No intraday data returned from FMP for {symbol} "
                    f"({from_date}→{to_date}, timeframe={timeframe})"
                )
            return pd.DataFrame()

        df = pd.concat(frames)
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
