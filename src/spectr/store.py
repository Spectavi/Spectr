from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from .mode import Mode


@dataclass(frozen=True)
class AppState:
    mode: Mode
    symbols: tuple[str, ...]
    active_symbol: str | None


Subscriber = Callable[[AppState], None]


class AppStore:
    """Minimal app store with immutable state updates."""

    def __init__(self, state: AppState) -> None:
        self._state = state
        self._subscribers: list[Subscriber] = []

    @property
    def state(self) -> AppState:
        return self._state

    def update(self, **changes) -> AppState:
        new_state = replace(self._state, **changes)
        if new_state == self._state:
            return self._state
        self._state = new_state
        for callback in list(self._subscribers):
            callback(new_state)
        return new_state

    def subscribe(self, callback: Subscriber) -> Callable[[], None]:
        self._subscribers.append(callback)

        def _unsubscribe() -> None:
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass

        return _unsubscribe
