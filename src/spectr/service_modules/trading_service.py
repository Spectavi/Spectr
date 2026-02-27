"""Trading service for handling trading actions and order dialogs."""
import logging
from typing import Any, Optional


log = logging.getLogger(__name__)


class TradingService:
    """Service for handling trading actions like buy/sell and order dialogs."""

    def __init__(
        self,
        broker_api: Any,
        data_api: Any,
        voice_agent: Optional[Any] = None,
        trade_amount: float = 0.0,
        auto_trading_enabled: bool = False,
        afterhours_enabled: bool = False,
    ):
        self.broker_api = broker_api
        self.data_api = data_api
        self.voice_agent = voice_agent
        self.trade_amount = trade_amount
        self.auto_trading_enabled = auto_trading_enabled
        self.afterhours_enabled = afterhours_enabled

    def can_trade_now(self) -> bool:
        """Check if trading is allowed at the current time."""
        from .. import utils
        return utils.is_market_open_now() or self.afterhours_enabled

    def has_pending_order(self, symbol: str) -> bool:
        """Check if there's a pending order for the given symbol."""
        try:
            return self.broker_api.has_pending_order(symbol)
        except Exception as e:
            log.warning(f"Failed to check pending order for {symbol}: {e}")
            return False

    def submit_buy_order(
        self,
        symbol: str,
        price: float,
        qty: Optional[float] = None,
    ) -> Optional[Any]:
        """Submit a buy order."""
        from ..fetch.broker_interface import OrderSide
        from .. import broker_tools

        try:
            if self.has_pending_order(symbol):
                log.warning(f"Pending order for {symbol}; ignoring buy signal!")
                if self.voice_agent:
                    try:
                        self.voice_agent.say(
                            f"Ignoring buy signal for {symbol}, pending order already exists."
                        )
                    except Exception as e:
                        log.warning(f"Error saying voice message: {e}")
                return None

            order = broker_tools.submit_order(
                self.broker_api,
                symbol,
                OrderSide.BUY,
                price,
                self.trade_amount,
                self.auto_trading_enabled,
                qty=qty,
                voice_agent=self.voice_agent,
                success_sound_path=None,
            )
            log.info(f"Buy order submitted: {symbol} @ {price}")
            return order
        except Exception as e:
            log.error(f"Failed to submit buy order for {symbol}: {e}")
            return None

    def submit_sell_order(
        self,
        symbol: str,
        price: float,
        amount_type: str = "all",
        qty: Optional[float] = None,
    ) -> Optional[Any]:
        """Submit a sell order."""
        from ..fetch.broker_interface import OrderSide
        from .. import broker_tools

        try:
            if self.has_pending_order(symbol):
                log.warning(f"Pending order for {symbol}; ignoring sell signal!")
                if self.voice_agent:
                    try:
                        self.voice_agent.say(
                            f"Ignoring sell signal for {symbol}, pending order already exists."
                        )
                    except Exception as e:
                        log.warning(f"Error saying voice message: {e}")
                return None

            if qty is None:
                position = self.broker_api.get_position(symbol)
                if position is None:
                    log.warning(f"No position found for {symbol} to sell")
                    return None

                qty_raw = getattr(position, "qty", None) or getattr(position, "size", None)
                try:
                    qty = float(qty_raw) if qty_raw is not None else 0.0
                except (TypeError, ValueError):
                    log.warning(f"Invalid quantity for {symbol}: {qty_raw}")
                    return None

                if amount_type == "half":
                    sell_qty = qty / 2.0
                elif amount_type == "quarter":
                    sell_qty = qty / 4.0
                else:
                    sell_qty = qty
            else:
                sell_qty = qty

            if sell_qty <= 0:
                log.warning(f"Cannot sell {amount_type} of position for {symbol}")
                return None

            order = broker_tools.submit_order(
                self.broker_api,
                symbol,
                OrderSide.SELL,
                price,
                sell_qty,
                self.auto_trading_enabled,
                voice_agent=self.voice_agent,
                success_sound_path=None,
            )
            log.info(f"Sell order submitted: {symbol} qty={sell_qty} @ {price}")
            return order
        except Exception as e:
            log.error(f"Failed to submit sell order for {symbol}: {e}")
            return None

    def get_position(self, symbol: str):
        """Get position for a specific symbol."""
        try:
            return self.broker_api.get_position(symbol)
        except Exception as e:
            log.warning(f"Failed to get position for {symbol}: {e}")
            return None

    def get_positions(self):
        """Get all open positions."""
        try:
            return self.broker_api.get_positions() or []
        except Exception as e:
            log.warning(f"Failed to get positions: {e}")
            return []

    def update_trade_amount(self, amount: float) -> None:
        """Update the trade amount."""
        self.trade_amount = amount

    def update_auto_trading(self, enabled: bool) -> None:
        """Update auto-trading setting."""
        self.auto_trading_enabled = enabled

    def update_afterhours(self, enabled: bool) -> None:
        """Update after-hours trading setting."""
        self.afterhours_enabled = enabled
