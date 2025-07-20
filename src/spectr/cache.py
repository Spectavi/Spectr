import json
import logging
import os
import pathlib
import shutil
import time
from datetime import datetime

import pandas as pd

log = logging.getLogger(__name__)

CACHE_DIR = "cache"
CACHE_PATH_STR = ".{}.cache"

SYMBOLS_CACHE_PATH = pathlib.Path.home() / ".spectr_symbols_cache.json"  # legacy
SCANNER_CACHE_FILE = pathlib.Path.home() / ".spectr_scanner_cache.json"  # legacy
GAINERS_CACHE_FILE = pathlib.Path.home() / ".spectr_gainers_cache.json"  # legacy
STRATEGY_CACHE_FILE = pathlib.Path.home() / ".spectr_strategy_cache.json"  # legacy
STRATEGY_NAME_FILE = pathlib.Path.home() / ".spectr_selected_strategy.json"  # legacy
SCANNER_NAME_FILE = pathlib.Path.home() / ".spectr_selected_scanner.json"  # legacy
TRADE_AMOUNT_FILE = pathlib.Path.home() / ".spectr_trade_amount.json"  # legacy
ONBOARD_FILE = pathlib.Path.home() / ".spectr_onboard.json"

COMBINED_CACHE_FILE = pathlib.Path.home() / ".spectr_cache.json"


def _load_combined(path: pathlib.Path = COMBINED_CACHE_FILE) -> dict:
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _default(obj: object) -> object:
    """Fallback JSON serializer for unsupported types."""
    try:
        from datetime import date, datetime, time as dt_time

        if isinstance(obj, (datetime, date, dt_time)):
            return obj.isoformat()
    except Exception:  # pragma: no cover - import failure unlikely
        pass

    try:
        import uuid

        if isinstance(obj, uuid.UUID):
            return str(obj)
    except Exception:  # pragma: no cover - import failure unlikely
        pass

    return str(obj)


def _save_combined(data: dict, path: pathlib.Path = COMBINED_CACHE_FILE) -> None:
    try:
        path.write_text(json.dumps(data, indent=0, default=_default))
    except Exception as exc:  # pragma: no cover - logging only
        log.error(f"combined cache write failed: {exc}")


def _load_legacy_strategy_cache(path: pathlib.Path) -> list[dict]:
    try:
        rows = json.loads(path.read_text())
    except Exception:
        return []
    out = []
    for rec in rows:
        if isinstance(rec, dict):
            ts = rec.get("time")
            if ts:
                try:
                    rec["time"] = datetime.fromisoformat(ts)
                except Exception:
                    rec["time"] = None
            out.append(rec)
    return out


def _merge_legacy_caches(path: pathlib.Path = COMBINED_CACHE_FILE) -> dict:
    data = _load_combined(path)
    changed = False

    def merge(key: str, fpath: pathlib.Path, loader):
        nonlocal changed
        if fpath.exists():
            try:
                data[key] = loader(fpath)
                changed = True
            except Exception:
                pass
            try:
                fpath.unlink()
            except Exception:
                pass

    merge("symbols", SYMBOLS_CACHE_PATH, lambda p: json.loads(p.read_text()))
    merge("scanner_cache", SCANNER_CACHE_FILE, lambda p: json.loads(p.read_text()))
    merge("gainers_cache", GAINERS_CACHE_FILE, lambda p: json.loads(p.read_text()))
    merge("strategy_cache", STRATEGY_CACHE_FILE, _load_legacy_strategy_cache)
    merge("selected_strategy", STRATEGY_NAME_FILE, lambda p: json.loads(p.read_text()))
    merge("selected_scanner", SCANNER_NAME_FILE, lambda p: json.loads(p.read_text()))
    merge("trade_amount", TRADE_AMOUNT_FILE, lambda p: json.loads(p.read_text()))
    merge("onboarding", ONBOARD_FILE, lambda p: json.loads(p.read_text()))

    if changed:
        _save_combined(data, path)
    return data


def save_cache(symbol: str, df: pd.DataFrame) -> None:
    if df is not None:
        if not os.path.exists(CACHE_DIR):
            os.mkdir(CACHE_DIR)
        cache_path = os.path.join(CACHE_DIR, CACHE_PATH_STR.format(symbol))

        df_to_save = df.copy()
        if (
            isinstance(df_to_save.index, pd.DatetimeIndex)
            and df_to_save.index.tz is not None
        ):
            df_to_save.index = df_to_save.index.tz_convert("UTC").tz_localize(None)

        df_to_save.to_parquet(cache_path)
        print(f"[Cache] DataFrame cached to {cache_path}")


def load_cache(symbol: str) -> pd.DataFrame:
    cache_path = os.path.join(CACHE_DIR, CACHE_PATH_STR.format(symbol))
    if os.path.exists(cache_path):
        print(f"[Cache] Loading cached DataFrame from {cache_path}")
        return pd.read_parquet(cache_path)
    log.debug("Cache not found.")
    return pd.DataFrame()


def save_scanner_cache(
    rows: list[dict], path: pathlib.Path = COMBINED_CACHE_FILE
) -> None:
    data = _load_combined(path)
    data["scanner_cache"] = {"t": time.time(), "rows": rows}
    _save_combined(data, path)


def load_scanner_cache(path: pathlib.Path = COMBINED_CACHE_FILE) -> list[dict]:
    data = _merge_legacy_caches(path)
    blob = data.get("scanner_cache", {})
    if not isinstance(blob, dict):
        return []
    if time.time() - blob.get("t", 0) > 900:
        return []
    return blob.get("rows", [])


def save_gainers_cache(
    rows: list[dict], path: pathlib.Path = COMBINED_CACHE_FILE
) -> None:
    data = _load_combined(path)
    data["gainers_cache"] = {"t": time.time(), "rows": rows}
    _save_combined(data, path)


def load_gainers_cache(path: pathlib.Path = COMBINED_CACHE_FILE) -> list[dict]:
    data = _merge_legacy_caches(path)
    blob = data.get("gainers_cache", {})
    if not isinstance(blob, dict):
        return []
    if time.time() - blob.get("t", 0) > 900:
        return []
    return blob.get("rows", [])


def save_strategy_cache(
    rows: list[dict], path: pathlib.Path = COMBINED_CACHE_FILE
) -> None:
    out = []
    for rec in rows:
        out_rec = dict(rec)
        ts = out_rec.get("time")
        if isinstance(ts, datetime):
            out_rec["time"] = ts.isoformat()
        out.append(out_rec)
    data = _load_combined(path)
    data["strategy_cache"] = out
    _save_combined(data, path)


def load_strategy_cache(path: pathlib.Path = COMBINED_CACHE_FILE) -> list[dict]:
    data = _merge_legacy_caches(path)
    rows = data.get("strategy_cache", [])
    out = []
    for rec in rows:
        if isinstance(rec, dict):
            ts = rec.get("time")
            if ts:
                try:
                    rec["time"] = datetime.fromisoformat(ts)
                except Exception:
                    rec["time"] = None
            out.append(rec)
    return out


def record_signal(
    cache_list: list[dict], sig: dict, path: pathlib.Path = COMBINED_CACHE_FILE
) -> None:
    cache_list.append(sig)
    save_strategy_cache(cache_list, path)


def attach_order_to_last_signal(
    cache_list: list[dict],
    symbol: str,
    side: str,
    order: object | None,
    *,
    reason: str | None = None,
    path: pathlib.Path = COMBINED_CACHE_FILE,
) -> None:
    """Attach order details to the most recent matching signal.

    If no matching signal exists yet, a new record is created so the order
    reason is preserved regardless of order type.
    """
    if order is None:
        return

    order_id = getattr(order, "id", None) or getattr(order, "order_id", None)
    if hasattr(order, "__getitem__"):
        try:
            order_id = order_id or order["id"]
        except Exception:
            try:
                order_id = order_id or order["order_id"]
            except Exception:
                pass

    status = getattr(order, "status", None)
    if status is None and hasattr(order, "__getitem__"):
        status = order.get("status") or order.get("state")

    found = False
    for rec in reversed(cache_list):
        if (
            rec.get("symbol") == symbol
            and rec.get("side") == side
            and "order_status" not in rec
        ):
            if order_id:
                rec["order_id"] = order_id
            if status:
                rec["order_status"] = status
            if reason is not None and "reason" not in rec:
                rec["reason"] = reason
            found = True
            break

    if not found:
        rec = {
            "time": datetime.now(),
            "symbol": symbol,
            "side": side,
            "reason": reason,
        }
        if order_id:
            rec["order_id"] = order_id
        if status:
            rec["order_status"] = status
        cache_list.append(rec)

    save_strategy_cache(cache_list, path)


def update_order_statuses(
    cache_list: list[dict],
    orders: list,
    path: pathlib.Path = COMBINED_CACHE_FILE,
) -> None:
    """Refresh order status values in the strategy cache."""

    if not orders:
        return

    # Build a mapping of order_id -> status for quick lookup
    status_map: dict[str, str] = {}
    for order in orders:
        order_id = getattr(order, "id", None) or getattr(order, "order_id", None)
        if hasattr(order, "__getitem__"):
            order_id = order_id or order.get("id") or order.get("order_id")
        if not order_id:
            continue

        status = getattr(order, "status", None)
        if status is None and hasattr(order, "__getitem__"):
            status = order.get("status") or order.get("state")
        if status is None:
            continue

        status_map[str(order_id)] = status

    updated = False
    for rec in cache_list:
        rec_id = rec.get("order_id")
        if rec_id is None:
            continue
        new_status = status_map.get(str(rec_id))
        if new_status and rec.get("order_status") != new_status:
            rec["order_status"] = new_status
            updated = True

    if updated:
        save_strategy_cache(cache_list, path)


def save_symbols_cache(
    symbols: list[str], path: pathlib.Path = COMBINED_CACHE_FILE
) -> None:
    data = _load_combined(path)
    data["symbols"] = symbols
    _save_combined(data, path)


def load_symbols_cache(path: pathlib.Path = COMBINED_CACHE_FILE) -> list[str]:
    data = _merge_legacy_caches(path)
    return data.get("symbols", [])


def save_selected_strategy(
    name: str | None, path: pathlib.Path = COMBINED_CACHE_FILE
) -> None:
    """Persist the currently selected strategy name."""
    data = _load_combined(path)
    data["selected_strategy"] = name
    _save_combined(data, path)


def load_selected_strategy(path: pathlib.Path = COMBINED_CACHE_FILE) -> str | None:
    """Load the last selected strategy name from cache."""
    data = _merge_legacy_caches(path)
    return data.get("selected_strategy")


def save_selected_scanner(name: str, path: pathlib.Path = COMBINED_CACHE_FILE) -> None:
    """Persist the currently selected scanner name."""
    data = _load_combined(path)
    data["selected_scanner"] = name
    _save_combined(data, path)


def load_selected_scanner(path: pathlib.Path = COMBINED_CACHE_FILE) -> str | None:
    """Load the last selected scanner name from cache."""
    data = _merge_legacy_caches(path)
    return data.get("selected_scanner")


def save_onboarding_config(
    config: dict, path: pathlib.Path = COMBINED_CACHE_FILE
) -> None:
    """Persist onboarding configuration."""
    data = _load_combined(path)
    data["onboarding"] = config
    _save_combined(data, path)


def load_onboarding_config(path: pathlib.Path = COMBINED_CACHE_FILE) -> dict | None:
    """Load onboarding configuration if present."""
    data = _merge_legacy_caches(path)
    return data.get("onboarding")


def save_trade_amount(amount: float, path: pathlib.Path = COMBINED_CACHE_FILE) -> None:
    """Persist the last trade amount value."""
    data = _load_combined(path)
    data["trade_amount"] = float(amount)
    _save_combined(data, path)


def load_trade_amount(path: pathlib.Path = COMBINED_CACHE_FILE) -> float | None:
    """Load the cached trade amount if available."""
    data = _merge_legacy_caches(path)
    value = data.get("trade_amount")
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def clear_cached_data(
    path: pathlib.Path = COMBINED_CACHE_FILE, cache_dir: str = CACHE_DIR
) -> None:
    """Remove cached data while keeping onboarding credentials."""
    data = _load_combined(path)
    onboarding = data.get("onboarding")
    if path.exists():
        try:
            path.unlink()
        except Exception:
            pass
    if onboarding is not None:
        _save_combined({"onboarding": onboarding}, path)
    if os.path.isdir(cache_dir):
        try:
            shutil.rmtree(cache_dir)
        except Exception:
            pass


_merge_legacy_caches()
