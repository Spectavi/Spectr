
import logging
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytz


LOG_FILE = 'signal_log.csv'
CACHE_DIR = 'cache'
CACHE_PATH_STR = ".{}.cache"

log = logging.getLogger(__name__)

def save_cache(symbol, df):
    if df is not None:
        cache_path = os.path.join(CACHE_DIR, CACHE_PATH_STR.format(symbol))
        df.to_parquet(cache_path)
        print(f"[Cache] DataFrame cached to {cache_path}")


def load_cache(symbol):
    cache_path = os.path.join(CACHE_DIR, CACHE_PATH_STR.format(symbol))
    if os.path.exists(CACHE_DIR):
        print(f"[Cache] Loading cached DataFrame from {cache_path}")
        return pd.read_parquet(cache_path)
    else:
        log.debug("Cache not found.")
    return None

def inject_quote_into_df(df: pd.DataFrame, quote: dict, tz='US/Eastern') -> pd.DataFrame:
    """
    Injects a new row into the OHLCV DataFrame using the latest quote.
    Ensures datetime index and proper column types.
    """
    if df.empty:
        raise ValueError("DataFrame is empty. Cannot append quote.")

    # Use last close and volume as fallback
    last_close = df.iloc[-1]["close"]
    last_volume = df.iloc[-1]["volume"]
    last_high = df.iloc[-1]["high"]
    last_low = df.iloc[-1]["low"]
    log.debug(f"last_close {last_close}")

    # Convert quote timestamp to datetime
    timestamp = quote.get("timestamp")
    if isinstance(timestamp, (int, float)):
        dt_index = pd.to_datetime(datetime.fromtimestamp(timestamp, pytz.timezone(tz)))
    elif isinstance(timestamp, str):
        dt_index = pd.to_datetime(timestamp)
    else:
        dt_index = pd.to_datetime(datetime.utcnow())

    # Build the new row
    price = quote["price"]
    log.debug(f"quote {quote}")
    new_row = pd.DataFrame({
        "open": [last_close],
        "high": [last_high],
        "low":  [last_low],
        "close": [price],
        "volume": [last_volume]
    }, index=pd.Index([dt_index], name="datetime"))

    # Ensure index is datetime
    df.index = pd.to_datetime(df.index, errors="coerce")
    new_row.index = pd.to_datetime(new_row.index, errors="coerce")

    df = pd.concat([df, new_row])
    df.index.name = "datetime"
    df = df[~df.index.duplicated(keep='last')]  # avoid repeated timestamps
    log.debug(f"Injected quote data into df: {df}")
    return df