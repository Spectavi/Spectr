import json
import logging
import os
import pathlib
import time
from datetime import datetime

import pandas as pd

log = logging.getLogger(__name__)

CACHE_DIR = "cache"
CACHE_PATH_STR = ".{}.cache"

CACHE_FILE = pathlib.Path.home() / ".spectr_cache.json"


def _load_cache(path: pathlib.Path = CACHE_FILE) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _save_cache(data: dict, path: pathlib.Path = CACHE_FILE) -> None:
    try:
        path.write_text(json.dumps(data, indent=0))
    except Exception as exc:
        log.error(f"cache write failed: {exc}")


def save_cache(symbol: str, df: pd.DataFrame) -> None:
    if df is not None:
        if not os.path.exists(CACHE_DIR):
            os.mkdir(CACHE_DIR)
        cache_path = os.path.join(CACHE_DIR, CACHE_PATH_STR.format(symbol))

        df_to_save = df.copy()
        if isinstance(df_to_save.index, pd.DatetimeIndex) and df_to_save.index.tz is not None:
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


def save_scanner_cache(rows: list[dict], path: pathlib.Path = CACHE_FILE) -> None:
    data = _load_cache(path)
    data["scanner_cache"] = {"t": time.time(), "rows": rows}
    _save_cache(data, path)


def load_scanner_cache(path: pathlib.Path = CACHE_FILE) -> list[dict]:
    data = _load_cache(path)
    blob = data.get("scanner_cache", {})
    if time.time() - blob.get("t", 0) > 900:
        return []
    return blob.get("rows", [])


def save_gainers_cache(rows: list[dict], path: pathlib.Path = CACHE_FILE) -> None:
    data = _load_cache(path)
    data["gainers_cache"] = {"t": time.time(), "rows": rows}
    _save_cache(data, path)


def load_gainers_cache(path: pathlib.Path = CACHE_FILE) -> list[dict]:
    data = _load_cache(path)
    blob = data.get("gainers_cache", {})
    if time.time() - blob.get("t", 0) > 900:
        return []
    return blob.get("rows", [])


def save_strategy_cache(rows: list[dict], path: pathlib.Path = CACHE_FILE) -> None:
    out = []
    for rec in rows:
        out_rec = dict(rec)
        ts = out_rec.get("time")
        if isinstance(ts, datetime):
            out_rec["time"] = ts.isoformat()
        out.append(out_rec)
    data = _load_cache(path)
    data["strategy_cache"] = out
    _save_cache(data, path)


def load_strategy_cache(path: pathlib.Path = CACHE_FILE) -> list[dict]:
    data = _load_cache(path)
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


def record_signal(cache_list: list[dict], sig: dict, path: pathlib.Path = CACHE_FILE) -> None:
    cache_list.append(sig)
    save_strategy_cache(cache_list, path)


def attach_order_to_last_signal(
    cache_list: list[dict],
    symbol: str,
    side: str,
    order: object | None,
    path: pathlib.Path = CACHE_FILE,
) -> None:
    """Attach order details to the most recent matching signal."""
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

    for rec in reversed(cache_list):
        if rec.get("symbol") == symbol and rec.get("side") == side and "order_status" not in rec:
            if order_id:
                rec["order_id"] = order_id
            if status:
                rec["order_status"] = status
            break

    save_strategy_cache(cache_list, path)


def update_order_statuses(
    cache_list: list[dict],
    orders: list,
    path: pathlib.Path = CACHE_FILE,
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


def save_symbols_cache(symbols: list[str], path: pathlib.Path = CACHE_FILE) -> None:
    data = _load_cache(path)
    data["symbols_cache"] = symbols
    _save_cache(data, path)


def load_symbols_cache(path: pathlib.Path = CACHE_FILE) -> list[str]:
    data = _load_cache(path)
    return data.get("symbols_cache", [])

def save_selected_strategy(name: str, path: pathlib.Path = CACHE_FILE) -> None:
    """Persist the currently selected strategy name."""
    try:
        data = _load_cache(path)
        data["selected_strategy"] = name
        _save_cache(data, path)
    except Exception as exc:
        log.error(f"strategy name cache write failed: {exc}")


def load_selected_strategy(path: pathlib.Path = CACHE_FILE) -> str | None:
    """Load the last selected strategy name from cache."""
    data = _load_cache(path)
    return data.get("selected_strategy")


def save_selected_scanner(name: str, path: pathlib.Path = CACHE_FILE) -> None:
    """Persist the currently selected scanner name."""
    try:
        data = _load_cache(path)
        data["selected_scanner"] = name
        _save_cache(data, path)
    except Exception as exc:
        log.error(f"scanner name cache write failed: {exc}")


def load_selected_scanner(path: pathlib.Path = CACHE_FILE) -> str | None:
    """Load the last selected scanner name from cache."""
    data = _load_cache(path)
    return data.get("selected_scanner")
def save_onboarding_config(config: dict, path: pathlib.Path = CACHE_FILE) -> None:
    """Persist onboarding configuration."""
    try:
        data = _load_cache(path)
        data["onboarding_config"] = config
        _save_cache(data, path)
    except Exception as exc:
        log.error(f"onboarding cache write failed: {exc}")


def load_onboarding_config(path: pathlib.Path = CACHE_FILE) -> dict | None:
    """Load onboarding configuration if present."""
    data = _load_cache(path)
    cfg = data.get("onboarding_config")
    return cfg if isinstance(cfg, dict) else None
