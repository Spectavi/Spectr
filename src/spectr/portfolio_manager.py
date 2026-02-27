"""Portfolio management for trading operations."""
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

log = logging.getLogger(__name__)


class PortfolioManager:
    """Manages portfolio data, equity tracking, and position management."""

    def __init__(self, broker_api, data_api):
        self.broker_api = broker_api
        self.data_api = data_api

        self._latest_quotes: dict[str, float] = {}
        self._equity_curve_data: list[tuple[datetime, float, float]] = []

        self._portfolio_balance_cache: dict | None = None
        self._portfolio_positions_cache: list | None = None
        self._portfolio_orders_cache: list | None = None

    def update_portfolio_equity(self) -> None:
        """Calculate portfolio value using cached quotes and record a point."""
        try:
            balance = self.broker_api.get_balance() or {}
            cash = balance.get("cash", 0.0)
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
            price = self._latest_quotes.get(sym)
            if price is None:
                try:
                    q = self.data_api.fetch_quote(sym)
                    price = q.get("price") if q else None
                    if price is not None:
                        self._latest_quotes[sym] = float(price)
                except Exception as exc:
                    log.debug(f"Failed to fetch quote for {sym}: {exc}")
                    price = None

            if price is not None:
                try:
                    total += qty * float(price)
                except (TypeError, ValueError) as e:
                    log.warning(f"Failed to calculate position value for {sym}: {e}")
            else:
                mv = getattr(pos, "market_value", None)
                if mv is not None:
                    try:
                        total += float(mv)
                    except (TypeError, ValueError) as e:
                        log.warning(f"Failed to add market value for {sym}: {e}")

        self._portfolio_balance_cache = {
            "cash": cash,
            "buying_power": balance.get("buying_power", 0.0),
            "portfolio_value": total,
        }

        try:
            self._record_equity_point(cash, total)
        except Exception as e:
            log.error(f"Failed to record equity point: {e}")

    def _record_equity_point(self, cash: float, total: float) -> None:
        now = datetime.now()
        cutoff = now - timedelta(hours=4)
        self._equity_curve_data.append((now, cash, total))
        self._equity_curve_data = [d for d in self._equity_curve_data if d[0] >= cutoff]
        self._portfolio_orders_cache = []
        self._portfolio_positions_cache = []

    def get_portfolio_data(self) -> dict:
        """Get current portfolio data from cache."""
        if not self._portfolio_balance_cache:
            self.update_portfolio_equity()
        return {
            "cash": self._portfolio_balance_cache.get("cash"),
            "buying_power": self._portfolio_balance_cache.get("buying_power"),
            "portfolio_value": self._portfolio_balance_cache.get("portfolio_value"),
            "positions": self._portfolio_positions_cache or [],
            "orders": self._portfolio_orders_cache or [],
            "equity_curve": list(self._equity_curve_data),
        }

    def update_latest_quotes(self, symbol: str, price: float) -> None:
        """Update latest quote for a symbol."""
        try:
            self._latest_quotes[symbol.upper()] = float(price)
        except (TypeError, ValueError) as e:
            log.warning(f"Failed to convert price for {symbol}: {e}")

    def get_latest_quote(self, symbol: str) -> float | None:
        """Get latest quote for a symbol."""
        return self._latest_quotes.get(symbol.upper())

    def _normalize_position(self, position):
        """Return a copy of ``position`` with numeric qty/market_value fields."""
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

    def get_open_positions(self) -> list:
        """Get all open positions."""
        try:
            positions = self.broker_api.get_positions() or []
            return [self._normalize_position(pos) for pos in positions]
        except Exception as exc:
            log.warning(f"Failed to fetch open positions: {exc}")
            return []

    def get_position(self, symbol: str):
        """Get position for a specific symbol."""
        try:
            position = self.broker_api.get_position(symbol)
            return self._normalize_position(position)
        except Exception as exc:
            log.warning(f"Failed to get position for {symbol}: {exc}")
            return None
