from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Protocol


class Mode(Enum):
    LIVE = "live"
    BACKTEST = "backtest"


class ServiceProtocol(Protocol):
    name: str

    def pause(self) -> None:
        ...

    def resume(self) -> None:
        ...


@dataclass(frozen=True)
class ModeTransition:
    previous: Mode
    current: Mode


class ModeManager:
    """Coordinates app mode transitions and service lifecycles."""

    def __init__(
        self,
        live_services: Iterable[ServiceProtocol] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._mode = Mode.LIVE
        self._live_services = list(live_services or [])
        self._log = logger or logging.getLogger(__name__)

    @property
    def mode(self) -> Mode:
        return self._mode

    def add_live_service(self, service: ServiceProtocol) -> None:
        if service not in self._live_services:
            self._live_services.append(service)

    def remove_live_service(self, service: ServiceProtocol) -> None:
        try:
            self._live_services.remove(service)
        except ValueError:
            pass

    def set_mode(self, mode: Mode) -> ModeTransition | None:
        if mode == self._mode:
            return None

        previous = self._mode
        self._mode = mode
        self._log.info("Mode transition: %s -> %s", previous.value, mode.value)

        if mode == Mode.BACKTEST:
            for service in self._live_services:
                try:
                    service.pause()
                except Exception:
                    self._log.exception("Failed to pause service: %s", service.name)
        elif mode == Mode.LIVE:
            for service in self._live_services:
                try:
                    service.resume()
                except Exception:
                    self._log.exception("Failed to resume service: %s", service.name)

        return ModeTransition(previous=previous, current=mode)
