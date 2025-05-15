import csv
import logging
import os
from datetime import datetime
from pathlib import Path
import pandas as pd
import pytz


LOG_FILE = 'signal_log.csv'
CACHE_PATH_STR = ".spectr_cache.parquet"

log = logging.getLogger(__name__)

def save_cache(df):
    if df is not None and not df.empty:
        cache_path = CACHE_PATH_STR
        df.to_parquet(cache_path)
        print(f"[Cache] DataFrame cached to {cache_path}")


def load_cache(mode):
    cache_path = Path(CACHE_PATH_STR.format(mode))
    if cache_path.exists():
        print(f"[Cache] Loading cached DataFrame from {cache_path}")
        return pd.read_parquet(cache_path)
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
        "open": [quote.get("open", last_close)],
        "high": [max(price, quote.get("dayHigh", price))],
        "low":  [min(price, quote.get("dayLow", price))],
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