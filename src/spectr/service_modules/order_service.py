import pandas as pd

"""Order service for handling trading operations."""

import logging
from typing import Any, Optional

log = logging.getLogger(__name__)


class OrderService:
    """Service for managing trading orders and positions."""

    def __init__(
        self,
        broker_api: Any,
        trade_amount: float = 0.0,
        auto_trading_enabled: bool = False,
    ):
        """Initialize the order service.

        Args:
            broker_api: Broker API interface for order operations
            trade_amount: Default trade amount in dollars
            auto_trading_enabled: Whether auto-trading is enabled
        """
        self.broker_api = broker_api
        self.trade_amount = trade_amount
        self.auto_trading_enabled = auto_trading_enabled

    def submit_order(
        self,
        symbol: str,
        side: str,
        price: float,
        voice_agent: Optional[Any] = None,
        success_sound_path: Optional[str] = None,
    ) -> Optional[Any]:
        """Submit an order to the broker.

        Args:
            symbol: Trading symbol
            side: Order side ('buy' or 'sell')
            price: Order price
            voice_agent: Optional voice agent for notifications
            success_sound_path: Optional path to success sound file

        Returns:
            The submitted order or None if failed
        """
        try:
            from ..fetch.broker_interface import OrderSide
            
            side_enum = (
                OrderSide.BUY if side == "buy" else OrderSide.SELL if side == "sell" else None
            )
            
            if hasattr(self.broker_api, "has_pending_order_with_side") and self.broker_api.has_pending_order_with_side(
                symbol, side_enum
            ):
                log.warning(f"Pending {side} order for {symbol}; ignoring signal!")
                if voice_agent:
                    try:
                        voice_agent.say(
                            f"Ignoring {side.capitalize()} signal for {symbol}, pending {side} order already exists."
                        )
                    except Exception as e:
                        log.warning(f"Error saying voice message: {e}")
                    return None

            order = self._submit_order_internal(
                symbol,
                side,
                price,
                voice_agent,
                success_sound_path,
            )
            return order
        except Exception as e:
            log.error(f"Failed to submit order for {symbol}: {e}")
            return None

    def _submit_order_internal(
        self,
        symbol: str,
        side: str,
        price: float,
        voice_agent: Optional[Any],
        success_sound_path: Optional[str],
    ) -> Any:
        """Internal method to actually submit the order.

        Args:
            symbol: Trading symbol
            side: Order side ('buy' or 'sell')
            price: Order price
            voice_agent: Optional voice agent for notifications
            success_sound_path: Optional path to success sound file

        Returns:
            The submitted order
        """
        from ..fetch.broker_interface import OrderSide
        from .. import broker_tools

        side_enum = (
            OrderSide.BUY
            if side == "buy"
            else OrderSide.SELL if side == "sell" else None
        )

        if not side_enum:
            log.warning(f"Invalid order side: {side}")
            raise ValueError(f"Invalid order side: {side}")

        order = broker_tools.submit_order(
            self.broker_api,
            symbol,
            side_enum,
            price,
            self.trade_amount,
            self.auto_trading_enabled,
            voice_agent=voice_agent,
            success_sound_path=success_sound_path,
        )
        log.info(f"Order submitted: {symbol} {side_enum.name} @ {price}")
        return order

    def check_pending_order(self, symbol: str) -> bool:
        """Check if there's a pending order for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            True if a pending order exists, False otherwise
        """
        try:
            if hasattr(self.broker_api, "has_pending_order"):
                return self.broker_api.has_pending_order(symbol)
            return False
        except Exception as e:
            log.warning(f"Failed to check pending order for {symbol}: {e}")
            return False

    def has_pending_order_with_side(self, symbol: str, side) -> bool:
        """Check if there's a pending order with the given side for a symbol.

        Args:
            symbol: Trading symbol
            side: OrderSide enum value

        Returns:
            True if a pending order exists with the given side, False otherwise
        """
        try:
            if hasattr(self.broker_api, "has_pending_order_with_side"):
                return self.broker_api.has_pending_order_with_side(symbol, side)
            elif hasattr(self.broker_api, "has_pending_order"):
                orders = self.broker_api.get_pending_orders(symbol)
                if isinstance(orders, pd.DataFrame) and not orders.empty:
                    if "side" in orders.columns:
                        return (orders["side"].str.lower() == str(side).lower()).any()
            return False
        except Exception as e:
            log.warning(f"Failed to check pending order with side for {symbol}: {e}")
            return False

    def get_position(self, symbol: str) -> Optional[Any]:
        """Get the current position for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Position object or None if not found
        """
        try:
            return self.broker_api.get_position(symbol)
        except Exception as e:
            log.warning(f"Failed to get position for {symbol}: {e}")
            return None

    def get_positions(self) -> list[Any]:
        """Get all open positions.

        Returns:
            List of position objects
        """
        try:
            positions = self.broker_api.get_positions()
            if positions is None:
                return []
            return positions
        except Exception as e:
            log.warning(f"Failed to get positions: {e}")
            return []

    def get_all_orders(self) -> Optional[Any]:
        """Get all orders from the broker.

        Returns:
            DataFrame of orders or None if failed
        """
        try:
            return self.broker_api.get_all_orders()
        except Exception as e:
            log.warning(f"Failed to get all orders: {e}")
            return None

    def get_pending_orders(self, symbol: str) -> Optional[list[Any]]:
        """Get pending orders for a specific symbol.

        Args:
            symbol: Trading symbol

        Returns:
            List of pending order objects or None if failed
        """
        try:
            orders = self.broker_api.get_pending_orders(symbol)
            return orders
        except Exception as e:
            log.warning(f"Failed to get pending orders for {symbol}: {e}")
            return None

    def update_trade_amount(self, amount: float) -> None:
        """Update the trade amount.

        Args:
            amount: New trade amount in dollars
        """
        self.trade_amount = amount

    def update_auto_trading(self, enabled: bool) -> None:
        """Update auto-trading setting.

        Args:
            enabled: Whether auto-trading is enabled
        """
        self.auto_trading_enabled = enabled