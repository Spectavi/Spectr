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

SYMBOLS_CACHE_PATH = pathlib.Path.home() / ".spectr_symbols_cache.json"
SCANNER_CACHE_FILE = pathlib.Path.home() / ".spectr_scanner_cache.json"
GAINERS_CACHE_FILE = pathlib.Path.home() / ".spectr_gainers_cache.json"
STRATEGY_CACHE_FILE = pathlib.Path.home() / ".spectr_strategy_cache.json"
STRATEGY_NAME_FILE = pathlib.Path.home() / ".spectr_selected_strategy.json"
SCANNER_NAME_FILE = pathlib.Path.home() / ".spectr_selected_scanner.json"


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


def save_scanner_cache(rows: list[dict], path: pathlib.Path = SCANNER_CACHE_FILE) -> None:
    try:
        path.write_text(json.dumps({"t": time.time(), "rows": rows}, indent=0))
    except Exception as exc:
        log.error(f"cache write failed: {exc}")


def load_scanner_cache(path: pathlib.Path = SCANNER_CACHE_FILE) -> list[dict]:
    try:
        blob = json.loads(path.read_text())
        if time.time() - blob.get("t", 0) > 900:
            return []
        return blob.get("rows", [])
    except Exception:
        return []


def save_gainers_cache(rows: list[dict], path: pathlib.Path = GAINERS_CACHE_FILE) -> None:
    try:
        path.write_text(json.dumps({"t": time.time(), "rows": rows}, indent=0))
    except Exception as exc:
        log.error(f"gainers cache write failed: {exc}")


def load_gainers_cache(path: pathlib.Path = GAINERS_CACHE_FILE) -> list[dict]:
    try:
        blob = json.loads(path.read_text())
        if time.time() - blob.get("t", 0) > 900:
            return []
        return blob.get("rows", [])
    except Exception:
        return []


def save_strategy_cache(rows: list[dict], path: pathlib.Path = STRATEGY_CACHE_FILE) -> None:
    try:
        out = []
        for rec in rows:
            out_rec = dict(rec)
            ts = out_rec.get("time")
            if isinstance(ts, datetime):
                out_rec["time"] = ts.isoformat()
            out.append(out_rec)
        path.write_text(json.dumps(out, indent=0))
    except Exception as exc:
        log.error(f"strategy cache write failed: {exc}")


def load_strategy_cache(path: pathlib.Path = STRATEGY_CACHE_FILE) -> list[dict]:
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


def record_signal(cache_list: list[dict], sig: dict, path: pathlib.Path = STRATEGY_CACHE_FILE) -> None:
    cache_list.append(sig)
    save_strategy_cache(cache_list, path)


def save_symbols_cache(symbols: list[str], path: pathlib.Path = SYMBOLS_CACHE_PATH) -> None:
    try:
        path.write_text(json.dumps(symbols))
    except Exception as exc:
        log.error(f"symbols cache write failed: {exc}")


def load_symbols_cache(path: pathlib.Path = SYMBOLS_CACHE_PATH) -> list[str]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return []

def save_selected_strategy(name: str, path: pathlib.Path = STRATEGY_NAME_FILE) -> None:
    """Persist the currently selected strategy name."""
    try:
        path.write_text(json.dumps(name))
    except Exception as exc:
        log.error(f"strategy name cache write failed: {exc}")


def load_selected_strategy(path: pathlib.Path = STRATEGY_NAME_FILE) -> str | None:
    """Load the last selected strategy name from cache."""
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def save_selected_scanner(name: str, path: pathlib.Path = SCANNER_NAME_FILE) -> None:
    """Persist the currently selected scanner name."""
    try:
        path.write_text(json.dumps(name))
    except Exception as exc:
        log.error(f"scanner name cache write failed: {exc}")


def load_selected_scanner(path: pathlib.Path = SCANNER_NAME_FILE) -> str | None:
    """Load the last selected scanner name from cache."""
    try:
        return json.loads(path.read_text())
    except Exception:
        return None