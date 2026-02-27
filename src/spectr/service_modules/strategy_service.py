"""Strategy service for handling strategy detection and signal processing."""

from typing import Any, Optional


class StrategyService:
    """Service for managing trading strategies and signal detection."""

    def __init__(
        self,
        exit_event: Any,
        logger: Any,
        strategy_name: str,
        strategy_class: Any,
        auto_trading_enabled: bool = False,
    ):
        """Initialize the strategy service.

        Args:
            exit_event: Event to signal when the service should stop
            logger: Logger instance for the service
            strategy_name: Name of the strategy
            strategy_class: Strategy class instance
            auto_trading_enabled: Whether auto-trading is enabled
        """
        self.exit_event = exit_event
        self.logger = logger
        self.strategy_name = strategy_name
        self.strategy_class = strategy_class
        self.auto_trading_enabled = auto_trading_enabled
        self._signals: list[dict] = []

    def set_strategy(self, strategy_name: str, strategy_class: Any) -> None:
        """Set the active strategy.

        Args:
            strategy_name: Name of the strategy
            strategy_class: Strategy class instance
        """
        self.strategy_name = strategy_name
        self.strategy_class = strategy_class
        self.logger.debug(f"Strategy changed to: {strategy_name}")

    def set_auto_trading(self, enabled: bool) -> None:
        """Set auto-trading status.

        Args:
            enabled: Whether auto-trading is enabled
        """
        self.auto_trading_enabled = enabled
        self.logger.debug(f"Auto-trading set to: {enabled}")

    async def detect_signals(
        self,
        df: Any,
        symbol: str,
        position: Optional[Any] = None,
        orders: Optional[list[Any]] = None,
    ) -> Optional[dict]:
        """Detect trading signals using the active strategy.

        Args:
            df: DataFrame with market data
            symbol: Trading symbol
            position: Current position for the symbol
            orders: Pending orders for the symbol

        Returns:
            Signal dictionary with signal and reason, or None if no signal
        """
        try:
            if self.strategy_class is None:
                self.logger.warning("Strategy class not set, cannot detect signals")
                return None

            return self.strategy_class.detect_signals(
                df,
                symbol,
                position=position,
                orders=orders,
            )
        except Exception as e:
            self.logger.error(f"Error detecting signals for {symbol}: {e}")
            return None

    def analyze_indicators(self, df: Any) -> Any:
        """Analyze indicators in the DataFrame.

        Args:
            df: DataFrame with market data

        Returns:
            DataFrame with analyzed indicators
        """
        try:
            if self.strategy_class is None:
                return df

            from ..strategies import metrics

            indicators = self.strategy_class.get_indicators()
            df = metrics.analyze_indicators(df, indicators)
            df["trade"] = None
            df["signal"] = None

            return df
        except Exception as e:
            self.logger.error(f"Error analyzing indicators: {e}")
            return df

    def record_signal(
        self,
        signals: list[dict],
        signal_data: dict,
    ) -> None:
        """Record a trading signal.

        Args:
            signals: List of signals to append to
            signal_data: Signal data dictionary
        """
        try:
            signals.append(signal_data)
            self.logger.debug(f"Signal recorded: {signal_data}")
        except Exception as e:
            self.logger.warning(f"Failed to record signal: {e}")

    def get_signals(self) -> list[dict]:
        """Get all recorded signals.

        Returns:
            List of signal dictionaries
        """
        return self._signals.copy()

    def clear_signals(self) -> None:
        """Clear all recorded signals."""
        self._signals.clear()
        self.logger.debug("Signals cleared")

    def update_signal_order(self, signals: list[dict], order: Any) -> None:
        """Update order status for a signal.

        Args:
            signals: List of signals to update
            order: Order object
        """
        try:
            from .. import cache

            last_signal = signals[-1] if signals else None
            if last_signal and "order_id" in last_signal:
                cache.attach_order_to_last_signal(
                    signals,
                    order.symbol.upper(),
                    order.side.name.lower(),
                    order,
                )
        except Exception as e:
            self.logger.warning(f"Failed to update signal order: {e}")

    def get_strategy_indicators(self) -> dict:
        """Get the current strategy's indicators.

        Returns:
            Dictionary of indicators
        """
        try:
            if self.strategy_class is None:
                return {}

            return self.strategy_class.get_indicators()
        except Exception as e:
            self.logger.warning(f"Failed to get strategy indicators: {e}")
            return {}

    def get_strategy_code(self) -> str:
        """Get the current strategy's code.

        Returns:
            Strategy code string
        """
        try:
            from ..strategies import get_strategy_code

            return get_strategy_code(self.strategy_name)
        except Exception as e:
            self.logger.warning(f"Failed to get strategy code: {e}")
            return ""

    def is_strategy_active(self) -> bool:
        """Check if the strategy is active.

        Returns:
            True if strategy is active, False otherwise
        """
        return self.strategy_class is not None

    def set_strategy_active(self, active: bool) -> None:
        """Set strategy active status.

        Args:
            active: Whether the strategy should be active
        """
        self.auto_trading_enabled = active
        self.logger.debug(f"Strategy active set to: {active}")
