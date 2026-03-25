"""Signal handling for trading strategy detection and order processing."""
import logging
from typing import TYPE_CHECKING

from .fetch.broker_interface import OrderSide
from . import cache
from . import broker_tools

if TYPE_CHECKING:
    import pandas as pd
    from .agent import VoiceAgent
    from .strategies import Strategy

log = logging.getLogger(__name__)


class SignalHandler:
    """Handles signal detection and order processing for trading strategies."""

    def __init__(
        self,
        broker_api,
        data_api,
        auto_trading_enabled: bool,
        voice_agent: "VoiceAgent | None" = None,
        trade_amount: float = 0.0,
        strategy_name: str = "CustomStrategy",
        success_sound_path: str = "order_success",
    ):
        self.broker_api = broker_api
        self.data_api = data_api
        self.auto_trading_enabled = auto_trading_enabled
        self.voice_agent = voice_agent
        self.trade_amount = trade_amount
        self.strategy_name = strategy_name
        self.strategy_signals = cache.load_strategy_cache()
        self.success_sound_path = success_sound_path

    def handle_signal(
        self,
        symbol: str,
        df: "pd.DataFrame",
        quote: dict,
        signal_dict: dict,
    ) -> None:
        """Process trading signal with order submission if enabled."""
        signal = signal_dict.get("signal")
        curr_price = quote.get("price")
        reason = signal_dict.get("reason")

        log.debug(f"Signal detected for {symbol}. Reason: {reason}")

        self._record_signal_to_dataframe(df, symbol, signal)

        if not self._should_process_signal(symbol, signal, curr_price):
            return

        side = self._determine_order_side(signal)
        if not side:
            return

        if not self._can_submit_order(symbol, side):
            return

        order = self._submit_order(symbol, side, curr_price)
        if not order:
            return

        self._attach_order_to_signal(symbol, side, order, reason)
        self._record_signal(symbol, curr_price, signal, reason)
        self._play_signal_sound(signal)

    def _record_signal_to_dataframe(
        self, df: "pd.DataFrame", symbol: str, signal: str | None
    ) -> None:
        """Record signal to DataFrame."""
        try:
            df.at[df.index[-1], "trade"] = signal
        except Exception as e:
            log.warning(f"Failed to set trade signal in DataFrame for {symbol}: {e}")

    def _should_process_signal(
        self, symbol: str, signal: str | None, curr_price: float | None
    ) -> bool:
        """Determine if signal should be processed."""
        if not signal or not curr_price:
            return False

        if not self.auto_trading_enabled:
            return True

        return self._can_trade_now()

    def _can_trade_now(self) -> bool:
        """Check if trading is allowed at current time."""
        try:
            from . import utils
            return utils.is_market_open_now()
        except Exception as e:
            log.warning(f"Error checking market status: {e}")
            return True

    def _determine_order_side(self, signal: str) -> OrderSide | None:
        """Determine the order side from signal."""
        if signal == "buy":
            return OrderSide.BUY
        if signal == "sell":
            return OrderSide.SELL
        return None

    def _can_submit_order(self, symbol: str, side: OrderSide) -> bool:
        """Check if order can be submitted."""
        try:
            if hasattr(self.broker_api, "has_pending_order_with_side") and self.broker_api.has_pending_order_with_side(symbol, side):
                log.warning(f"Pending {side.name.lower()} order for {symbol}; ignoring signal!")
                return False
        except Exception as e:
            log.warning(f"Failed to check pending order for {symbol}: {e}")
            return False
        return True

    def _submit_order(
        self, symbol: str, side: OrderSide, curr_price: float
    ) -> dict | None:
        """Submit order to broker."""
        try:
            return broker_tools.submit_order(
                self.broker_api,
                symbol,
                side,
                curr_price,
                self.trade_amount,
                self.auto_trading_enabled,
                voice_agent=self.voice_agent,
                success_sound_path=self.success_sound_path,
            )
        except Exception as e:
            log.error(f"Failed to submit order for {symbol}: {e}")
            return None

    def _attach_order_to_signal(
        self, symbol: str, side: OrderSide, order: dict, reason: str
    ) -> None:
        """Attach order to strategy signals."""
        try:
            cache.attach_order_to_last_signal(
                self.strategy_signals,
                symbol.upper(),
                side.name.lower(),
                order,
                reason=reason,
            )
        except Exception as e:
            log.warning(f"Failed to attach order to signal for {symbol}: {e}")

    def _record_signal(
        self,
        symbol: str,
        curr_price: float,
        signal: str,
        reason: str,
    ) -> None:
        """Record signal to cache."""
        try:
            cache.record_signal(
                self.strategy_signals,
                {
                    "time": __import__("datetime").datetime.now(),
                    "symbol": symbol,
                    "side": signal,
                    "price": curr_price,
                    "reason": reason,
                    "strategy": self.strategy_name,
                },
            )
        except Exception as e:
            log.warning(f"Failed to record signal for {symbol}: {e}")

    def _play_signal_sound(self, signal: str) -> None:
        """Play sound based on signal type."""
        if signal == "buy":
            from . import utils
            try:
                utils.play_sound("buy")
            except Exception as e:
                log.warning(f"Failed to play sound for {signal}: {e}")
        elif signal == "sell":
            from . import utils
            try:
                utils.play_sound("sell")
            except Exception as e:
                log.warning(f"Failed to play sound for {signal}: {e}")
