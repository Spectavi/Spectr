"""Data service for handling market data operations."""

import logging
from typing import Any, Optional

log = logging.getLogger(__name__)


class DataService:
    """Service for managing market data fetching and caching."""

    def __init__(
        self,
        data_api: Any,
        broker_api: Any,
        latest_quotes: Optional[dict[str, float]] = None,
    ):
        """Initialize the data service.

        Args:
            data_api: Data API interface for market data
            broker_api: Broker API interface for price data
        """
        self.data_api = data_api
        self.broker_api = broker_api
        self._latest_quotes: dict[str, float] = latest_quotes if latest_quotes is not None else {}

    def fetch_chart_data(
        self, symbol: str, from_date: str, to_date: str
    ) -> Any:
        """Fetch chart data for a symbol.

        Args:
            symbol: Trading symbol
            from_date: Start date in YYYY-MM-DD format
            to_date: End date in YYYY-MM-DD format

        Returns:
            DataFrame with chart data
        """
        try:
            return self.data_api.fetch_chart_data(symbol, from_date, to_date)
        except Exception as e:
            log.warning(f"Failed to fetch chart data for {symbol}: {e}")
            return None

    def fetch_quote(self, symbol: str) -> Optional[dict]:
        """Fetch current quote for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Quote dictionary or None if failed
        """
        try:
            quote = self.data_api.fetch_quote(symbol)
            price = quote.get("price") if quote else None
            if price is not None:
                self._latest_quotes[symbol.upper()] = float(price)
            return quote
        except Exception as e:
            log.warning(f"Failed to fetch quote for {symbol}: {e}")
            return None

    def fetch_price(self, symbol: str) -> Optional[float]:
        """Fetch current price for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Current price or None if failed
        """
        try:
            quote = self.fetch_quote(symbol)
            if quote and "price" in quote:
                price = float(quote["price"])
                self._latest_quotes[symbol.upper()] = price
                return price
            return None
        except Exception as e:
            log.warning(f"Failed to fetch price for {symbol}: {e}")
            return None

    def get_latest_quote(self, symbol: str) -> Optional[float]:
        """Get the latest cached quote for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Latest quote price or None if not available
        """
        return self._latest_quotes.get(symbol.upper())

    def update_latest_quote(self, symbol: str, price: float) -> None:
        """Update the latest quote for a symbol.

        Args:
            symbol: Trading symbol
            price: New quote price
        """
        self._latest_quotes[symbol.upper()] = price

    def fetch_and_update_quote(self, symbol: str) -> Optional[float]:
        """Fetch and update the latest quote for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Updated quote price or None if failed
        """
        try:
            quote = self.fetch_quote(symbol)
            if quote and "price" in quote:
                price = float(quote["price"])
                self.update_latest_quote(symbol, price)
                return price
            return None
        except Exception as e:
            print(f"Failed to fetch and update quote for {symbol}: {e}")
            return None

    def get_latest_quotes(self) -> dict[str, float]:
        """Get all latest quotes.

        Returns:
            Dictionary of symbol to price
        """
        return self._latest_quotes.copy()

    def get_chart_data_and_quote(
        self, symbol: str, from_date: str, to_date: str
    ) -> tuple[Any, Optional[dict]]:
        """Fetch chart data and quote for a symbol.

        Args:
            symbol: Trading symbol
            from_date: Start date in YYYY-MM-DD format
            to_date: End date in YYYY-MM-DD format

        Returns:
            Tuple of (DataFrame, quote_dict)
        """
        try:
            df = self.fetch_chart_data(symbol, from_date, to_date)
            quote = self.fetch_quote(symbol)
            return df, quote
        except Exception as e:
            log.warning(f"Failed to fetch chart data and quote for {symbol}: {e}")
            return None, None

    def inject_quote_into_df(
        self, df: Any, quote: Optional[dict]
    ) -> Any:
        """Inject quote into DataFrame.

        Args:
            df: DataFrame to inject quote into
            quote: Quote dictionary

        Returns:
            DataFrame with injected quote
        """
        try:
            if df is None or quote is None:
                return df

            price = quote.get("price")
            if price is not None:
                from .. import utils

                df = utils.inject_quote_into_df(df, quote)

            return df
        except Exception as e:
            print(f"Failed to inject quote into DataFrame: {e}")
            return df

    def clear_quote_cache(self, symbol: Optional[str] = None) -> None:
        """Clear quote cache.

        Args:
            symbol: Specific symbol to clear, or None for all
        """
        if symbol:
            self._latest_quotes.pop(symbol.upper(), None)
        else:
            self._latest_quotes.clear()

    def clear_quote_cache_for_symbols(self, symbols: list[str]) -> None:
        """Clear quote cache for specific symbols.

        Args:
            symbols: List of symbols to clear
        """
        for symbol in symbols:
            self._latest_quotes.pop(symbol.upper(), None)
