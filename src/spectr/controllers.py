from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Sequence

from .store import AppStore, StrategyState, PortfolioState


class AppController:
    """Store intents for common app updates."""

    def __init__(self, store: AppStore) -> None:
        self._store = store

    def set_mode(self, mode) -> None:
        self._store.update(mode=mode)

    def set_symbols(self, symbols: Sequence[str], active_symbol: str | None) -> None:
        self._store.update(symbols=tuple(symbols), active_symbol=active_symbol)

    def set_active_symbol(self, active_symbol: str | None) -> None:
        self._store.update(active_symbol=active_symbol)

    def set_strategy(self, name: str | None, *, enabled: bool) -> None:
        state = self._store.state
        self._store.update(strategy=replace(state.strategy, name=name, enabled=enabled))

    def set_strategy_enabled(self, enabled: bool) -> None:
        state = self._store.state
        self._store.update(strategy=replace(state.strategy, enabled=enabled))

    def set_config(self, config: object | None) -> None:
        self._store.update(config=config)

    def set_portfolio(
        self,
        *,
        cash: float | None,
        buying_power: float | None,
        portfolio_value: float | None,
        positions: Iterable[object] | None,
        orders: Iterable[object] | None,
        equity_curve: Iterable[tuple[object, float, float]] | None,
    ) -> None:
        self._store.update(
            portfolio=PortfolioState(
                cash=cash,
                buying_power=buying_power,
                portfolio_value=portfolio_value,
                positions=tuple(positions or ()),
                orders=tuple(orders or ()),
                equity_curve=tuple(equity_curve or ()),
            )
        )
