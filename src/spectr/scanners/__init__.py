import importlib
import inspect
import logging
import pkgutil
from typing import Type

from .scanner_interface import ScannerInterface

__all__ = ["load_scanner", "list_scanners", "ScannerInterface"]


def list_scanners() -> dict[str, Type[ScannerInterface]]:
    """Return mapping of scanner name to class found in this package."""
    scanners: dict[str, Type[ScannerInterface]] = {}
    package = __name__
    for _, mod_name, _ in pkgutil.iter_modules(__path__):
        try:
            module = importlib.import_module(f"{package}.{mod_name}")
        except Exception as exc:  # pragma: no cover - import failures
            logging.getLogger(__name__).warning(
                "Skipping scanner module %s due to import error: %s",
                mod_name,
                exc,
            )
            continue
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, ScannerInterface) and obj is not ScannerInterface:
                scanners[name] = obj
    return scanners


def load_scanner(name: str) -> Type[ScannerInterface]:
    """Load scanner class by name from this package."""
    scanners = list_scanners()
    if name not in scanners:
        raise ValueError(f"Scanner '{name}' not found")
    return scanners[name]
