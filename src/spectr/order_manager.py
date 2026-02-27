"""Order management for trading operations."""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd
    from types import SimpleNamespace

from .fetch.broker_interface import OrderSide

log = logging.getLogger(__name__)


class OrderManager:
    """Manages order submission and status tracking."""

    def __init__(self, broker_api):
        self.broker_api = broker_api
        self.strategy_signals = []

    def has_pending_order(self, symbol: str) -> bool:
        """Check if there's a pending order for the given symbol."""
        try:
            return self.broker_api.has_pending_order(symbol)
        except Exception as e:
            log.warning(f"Failed to check pending order for {symbol}: {e}")
            return False

    def get_pending_orders(self, symbol: str) -> list | None:
        """Get pending orders for the given symbol."""
        try:
            return self.broker_api.get_pending_orders(symbol)
        except Exception as e:
            log.warning(f"Failed to get pending orders for {symbol}: {e}")
            return None

    def get_all_orders(self) -> list | None:
        """Get all orders from broker."""
        try:
            orders = self.broker_api.get_all_orders()
            if isinstance(orders, pd.DataFrame):
                if not orders.empty:
                    return [
                        self._convert_to_simple_namespace(rec)
                        for rec in orders.to_dict(orient="records")
                    ]
                return []
            return orders
        except Exception as e:
            log.warning(f"Failed to get all orders: {e}")
            return None

    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        price: float,
        amount: float,
        auto_trading: bool,
        voice_agent,
        success_sound_path: str,
    ) -> dict | None:
        """Submit order to broker with voice feedback."""
        try:
            from . import broker_tools
            return broker_tools.submit_order(
                self.broker_api,
                symbol,
                side,
                price,
                amount,
                auto_trading,
                voice_agent=voice_agent,
                success_sound_path=success_sound_path,
            )
        except Exception as e:
            log.error(f"Failed to submit order for {symbol}: {e}")
            return None

    def update_order_statuses(self) -> None:
        """Update statuses for all open orders in strategy signals."""
        try:
            open_ids = {
                str(rec["order_id"])
                for rec in self.strategy_signals
                if rec.get("order_id")
                and str(rec.get("order_status", "")).lower()
                not in {"filled", "canceled", "cancelled", "expired", "rejected"}
            }

            if not open_ids:
                return

            orders = self.get_all_orders()
            if orders:
                cache.update_order_statuses(self.strategy_signals, orders)
        except Exception as e:
            log.warning(f"Failed to update order statuses: {e}")

    @staticmethod
    def _convert_to_simple_namespace(record: dict) -> "SimpleNamespace":
        """Convert dictionary record to SimpleNamespace."""
        return SimpleNamespace(**record)
