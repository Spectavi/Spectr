from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional, Tuple, List, Dict, Any

import logging

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from spectr.fetch.broker_api import BrokerInterface
    from spectr.fetch.data_api import DataAPI
    from spectr.agent import VoiceAgent
    from spectr.cache import Cache
    from spectr.controllers import AppController
    from spectr.views.portfolio import PortfolioScreen


class PortfolioService:
    """Service for portfolio tracking, equity calculations, and portfolio management."""

    def __init__(
        self,
        broker_api: "BrokerInterface",
        data_api: "DataAPI",
        voice_agent: "VoiceAgent | None",
        cache: "Cache",
        controller: "AppController",
        latest_quotes: dict[str, float],
        portfolio_screen: "PortfolioScreen | None",
        equity_curve_data: list[tuple[datetime, float, float]],
        trade_amount: float,
        auto_trading_enabled: bool,
    ):
        self.broker_api = broker_api
        self.data_api = data_api
        self.voice_agent = voice_agent
        self.cache = cache
        self.controller = controller
        self.latest_quotes = latest_quotes
        self.portfolio_screen = portfolio_screen
        self.equity_curve_data = equity_curve_data
        self.trade_amount = trade_amount
        self.auto_trading_enabled = auto_trading_enabled

        self._portfolio_balance_cache: Optional[Dict[str, float]] = None
        self._portfolio_positions_cache: Optional[List[Any]] = None
        self._portfolio_orders_cache: Optional[List[Any]] = None
        self._equity_curve_data: list[tuple[datetime, float, float]] = equity_curve_data

    def _normalize_position(self, position):
        """Return a copy of position with numeric qty/market_value fields."""
        if position is None:
            return None
        try:
            if hasattr(position, "qty"):
                val = getattr(position, "qty")
                if isinstance(val, str):
                    setattr(position, "qty", float(val))
            elif hasattr(position, "size"):
                val = getattr(position, "size")
                if isinstance(val, str):
                    setattr(position, "size", float(val))
        except Exception:
            pass

        try:
            if hasattr(position, "market_value"):
                val = getattr(position, "market_value")
                if isinstance(val, str):
                    setattr(position, "market_value", float(val))
        except Exception:
            pass

        return position

    def update_latest_quotes(self, symbol: str, price: float) -> None:
        """Update the cached quote for a symbol."""
        self.latest_quotes[symbol.upper()] = price

    def get_latest_quote(self, symbol: str) -> Optional[float]:
        """Get the cached quote for a symbol."""
        return self.latest_quotes.get(symbol.upper())

    def calculate_portfolio_value(self) -> Tuple[float, Dict[str, float], List[Any]]:
        """Calculate portfolio value using cached quotes.

        Returns:
            Tuple of (total_value, balance_cache, positions)
        """
        balance = {}
        cash = 0.0
        positions = []

        try:
            balance_data = self.broker_api.get_balance() or {}
            cash = balance_data.get("cash", 0.0)
            balance = balance_data
        except Exception as exc:
            log.warning(f"Failed to fetch balance: {exc}")
            cash = 0.0
            balance = {}

        try:
            positions = self.broker_api.get_positions() or []
        except Exception as exc:
            log.warning(f"Failed to fetch positions: {exc}")
            positions = []

        total = cash
        for pos in positions:
            pos = self._normalize_position(pos)
            sym = getattr(pos, "symbol", "").upper()
            qty_raw = getattr(pos, "qty", 0)
            try:
                qty = float(qty_raw) if qty_raw is not None else 0.0
            except (TypeError, ValueError):
                qty = 0.0
            price = self.get_latest_quote(sym)
            if price is None:
                try:
                    q = self.data_api.fetch_quote(sym)
                    price = q.get("price") if q else None
                    if price is not None:
                        self.update_latest_quotes(sym, float(price))
                except Exception as exc:
                    print(f"Failed to fetch quote for {sym}: {exc}")
                    price = None

            if price is not None:
                try:
                    total += qty * float(price)
                except (TypeError, ValueError) as e:
                    print(f"Failed to calculate position value for {sym}: {e}")
            else:
                mv = getattr(pos, "market_value", None)
                if mv is not None:
                    try:
                        total += float(mv)
                    except (TypeError, ValueError) as e:
                        print(f"Failed to add market value for {sym}: {e}")

        return total, balance, positions

    def update_portfolio_equity(self) -> None:
        """Calculate portfolio value using cached quotes and record a point."""
        total, balance, positions = self.calculate_portfolio_value()

        self._portfolio_balance_cache = {
            "cash": balance.get("cash", 0.0),
            "buying_power": balance.get("buying_power", 0.0),
            "portfolio_value": total,
        }
        self._portfolio_positions_cache = positions

        self._record_equity_point(
            self._portfolio_balance_cache["cash"],
            total
        )
        self._sync_store_portfolio()

    def _record_equity_point(self, cash: float, total: float) -> None:
        """Record an equity point and update the portfolio screen."""
        now = datetime.now()
        cutoff = now - timedelta(hours=4)
        self.equity_curve_data.append((now, cash, total))
        self.equity_curve_data = [d for d in self.equity_curve_data if d[0] >= cutoff]
        self._sync_store_portfolio()

        if self.portfolio_screen:
            screen_app = getattr(self.portfolio_screen, "app", None)
            if screen_app and self.portfolio_screen in screen_app.screen_stack:
                self.portfolio_screen.cash = cash
                self.portfolio_screen.portfolio_value = total
                self.portfolio_screen.equity_view.data = list(self.equity_curve_data)
                self.portfolio_screen.equity_view.refresh()

    def _sync_store_portfolio(self) -> None:
        """Sync portfolio state to the store."""
        balance = self._portfolio_balance_cache or {}
        self.controller.set_portfolio(
            cash=balance.get("cash") if balance else None,
            buying_power=balance.get("buying_power") if balance else None,
            portfolio_value=balance.get("portfolio_value") if balance else None,
            positions=self._portfolio_positions_cache,
            orders=self._portfolio_orders_cache,
            equity_curve=self.equity_curve_data,
        )

    def get_portfolio_cache(self) -> Dict[str, Any]:
        """Get the current portfolio cache."""
        return {
            "balance_cache": self._portfolio_balance_cache,
            "positions_cache": self._portfolio_positions_cache,
            "orders_cache": self._portfolio_orders_cache,
            "equity_curve_data": self.equity_curve_data,
            "latest_quotes": self.latest_quotes,
        }

    def clear_equity_curve(self) -> None:
        """Clear the equity curve data."""
        self.equity_curve_data = []
        self._sync_store_portfolio()

    def get_equity_curve_data(self) -> list[tuple[datetime, float, float]]:
        """Get the equity curve data."""
        return self.equity_curve_data

    def get_portfolio_balance(self) -> Optional[Dict[str, float]]:
        """Get the portfolio balance cache."""
        return self._portfolio_balance_cache

    def refresh_order_status(self) -> None:
        """Refresh the status of open orders."""
        try:
            orders = self.broker_api.get_all_orders()
            self._portfolio_orders_cache = orders
            self._sync_store_portfolio()
        except Exception as e:
            print(f"Failed to refresh order status: {e}")

    def get_positions(self) -> Optional[List[Any]]:
        """Get the cached positions."""
        return self._portfolio_positions_cache

    def get_orders(self) -> Optional[List[Any]]:
        """Get the cached orders."""
        return self._portfolio_orders_cache

    def get_cash(self) -> Optional[float]:
        """Get the cached cash balance."""
        if self._portfolio_balance_cache:
            return self._portfolio_balance_cache.get("cash")
        return None

    def get_buying_power(self) -> Optional[float]:
        """Get the cached buying power."""
        if self._portfolio_balance_cache:
            return self._portfolio_balance_cache.get("buying_power")
        return None

    def get_portfolio_value(self) -> Optional[float]:
        """Get the cached portfolio value."""
        if self._portfolio_balance_cache:
            return self._portfolio_balance_cache.get("portfolio_value")
        return None

    def has_position(self, symbol: str) -> bool:
        """Check if the portfolio has a position in the given symbol."""
        if not self._portfolio_positions_cache:
            return False
        for pos in self._portfolio_positions_cache:
            if getattr(pos, "symbol", "").upper() == symbol.upper():
                return True
        return False

    def get_position(self, symbol: str) -> Optional[Any]:
        """Get the position for the given symbol."""
        if not self._portfolio_positions_cache:
            return None
        for pos in self._portfolio_positions_cache:
            if getattr(pos, "symbol", "").upper() == symbol.upper():
                return pos
        return None
