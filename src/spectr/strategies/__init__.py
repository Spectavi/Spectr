import importlib
import inspect
import logging
import pkgutil
from typing import Type

import backtrader as bt
from .trading_strategy import TradingStrategy

__all__ = ["load_strategy", "list_strategies", "get_strategy_code"]


def list_strategies() -> dict[str, Type[bt.Strategy]]:
    """Return mapping of strategy name to class found in this package."""
    strategies: dict[str, Type[bt.Strategy]] = {}
    package = __name__
    for _, mod_name, _ in pkgutil.iter_modules(__path__):
        if mod_name == "trading_strategy":
            continue
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
            if issubclass(obj, bt.Strategy) and obj not in (
                bt.Strategy,
                TradingStrategy,
            ):
                strategies[name] = obj
    return strategies


def load_strategy(name: str) -> Type[bt.Strategy]:
    """Load strategy class by name from this package."""
    strategies = list_strategies()
    if name not in strategies:
        raise ValueError(f"Strategy '{name}' not found")
    return strategies[name]


def get_strategy_code(name: str) -> str:
    """Return the full source for the given strategy class."""
    if not name:
        return ""
    try:
        cls = load_strategy(name)
        module = inspect.getmodule(cls)
        assert module is not None
        return pathlib.Path(module.__file__).read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover - best effort
        logging.getLogger(__name__).error(
            "Unable to load strategy code for %s: %s", name, exc
        )
        return f"Unable to load strategy code: {exc}"
