from abc import ABC, abstractmethod

class ScannerInterface(ABC):
    """Abstract interface for background scanners."""

    @abstractmethod
    def __init__(self, data_api, exit_event) -> None:
        """Initialize the scanner with data source and exit event."""
        raise NotImplementedError

    @property
    @abstractmethod
    def scanner_results(self) -> list[dict]:
        """Return the latest filtered scan results."""
        raise NotImplementedError

    @property
    @abstractmethod
    def top_gainers(self) -> list[dict]:
        """Return the latest unfiltered top gainers."""
        raise NotImplementedError

    @abstractmethod
    async def scanner_loop(self, interval: float = 60.0) -> None:
        """Continuously run the scanner every ``interval`` seconds."""
        raise NotImplementedError
