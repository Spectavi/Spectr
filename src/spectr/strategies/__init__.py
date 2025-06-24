import importlib
import inspect
import logging
import pkgutil
from typing import Type

import backtrader as bt

__all__ = ["load_strategy", "list_strategies"]


def list_strategies() -> dict[str, Type[bt.Strategy]]:
    """Return mapping of strategy name to class found in this package."""
    strategies: dict[str, Type[bt.Strategy]] = {}
    package = __name__
    for _, mod_name, _ in pkgutil.iter_modules(__path__):
        try:
            module = importlib.import_module(f"{package}.{mod_name}")
        except Exception as exc:  # pragma: no cover - import failures
            logging.getLogger(__name__).error(
                "Skipping strategy module %s due to import error: %s",
                mod_name,
                exc,
            )
            continue
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, bt.Strategy) and obj is not bt.Strategy:
                strategies[name] = obj
    return strategies


def load_strategy(name: str) -> Type[bt.Strategy]:
    """Load strategy class by name from this package."""
    strategies = list_strategies()
    if name not in strategies:
        raise ValueError(f"Strategy '{name}' not found")
    return strategies[name]
