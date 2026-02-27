"""Base service classes for Spectr application services."""

from typing import Any


class Service:
    """Base class for Spectr services."""

    def __init__(self, exit_event: Any, logger: Any):
        """Initialize the service.

        Args:
            exit_event: Event to signal when the service should stop
            logger: Logger instance for the service
        """
        self.exit_event = exit_event
        self.logger = logger
        self._running = False

    @property
    def is_running(self) -> bool:
        """Check if the service is currently running."""
        return self._running

    def start(self) -> None:
        """Start the service."""
        if not self._running:
            self._running = True
            self.logger.debug(f"Service started: {self.__class__.__name__}")

    def stop(self) -> None:
        """Stop the service."""
        if self._running:
            self._running = False
            self.logger.debug(f"Service stopped: {self.__class__.__name__}")
