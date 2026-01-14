from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Sequence

from .mode import Mode


@dataclass(frozen=True)
class StrategyState:
    name: str | None
    enabled: bool


@dataclass(frozen=True)
class PortfolioState:
    cash: float | None
    buying_power: float | None
    portfolio_value: float | None
    positions: tuple[object, ...]
    orders: tuple[object, ...]
    equity_curve: tuple[tuple[object, float, float], ...]


@dataclass(frozen=True)
class AppState:
    mode: Mode
    symbols: tuple[str, ...]
    active_symbol: str | None
    config: object | None
    strategy: StrategyState
    portfolio: PortfolioState


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


def select_active_symbol(state: AppState) -> str | None:
    return state.active_symbol


def select_symbols(state: AppState) -> tuple[str, ...]:
    return state.symbols


def select_strategy(state: AppState) -> StrategyState:
    return state.strategy


def select_portfolio(state: AppState) -> PortfolioState:
    return state.portfolio


def select_config(state: AppState) -> object | None:
    return state.config
