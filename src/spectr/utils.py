
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
    if os.path.exists(cache_path):
        print(f"[Cache] Loading cached DataFrame from {cache_path}")
        return pd.read_parquet(cache_path)
    else:
        log.debug("Cache not found.")
    return pd.DataFrame() # Return empty dataframe.

def inject_quote_into_df(
    df: pd.DataFrame,
    quote: dict,
    tz=datetime.now().astimezone().tzinfo,                        # default to system zone
) -> pd.DataFrame:
    """
    Append the latest quote as a new bar and guarantee the entire frame
    ends up in *tz*.
    """
    if df.empty:
        raise ValueError("DataFrame is empty; cannot append quote.")

    # ---------- build timestamp in *tz* ---------------------------------
    ts_raw = quote.get("timestamp")
    if isinstance(ts_raw, (int, float)):
        ts = pd.to_datetime(ts_raw, unit="s", utc=True).tz_convert(tz)
    else:                               # assume str or datetime-like
        ts = pd.to_datetime(ts_raw, utc=True, errors="coerce").tz_convert(tz)

    # ---------- normalise df’s index to *tz* ----------------------------
    if df.index.tz is None:
        # If the historical data are naïve (FMP says “US/Eastern” but values
        # are really UTC), assume they were UTC and convert
        df.index = df.index.tz_localize("UTC").tz_convert(tz)
    else:
        df.index = df.index.tz_convert(tz)

    # ---------- create the new row --------------------------------------
    last_row = df.iloc[-1]
    new_row = pd.DataFrame(
        {
            "open":   last_row["close"],
            "high":   last_row["high"],
            "low":    last_row["low"],
            "close":  quote["price"],
            "volume": last_row["volume"],
        },
        index=pd.Index([ts], name="datetime"),
    )

    # ---------- concatenate & dedupe ------------------------------------
    out = pd.concat([df, new_row])
    out = out[~out.index.duplicated(keep="last")]

    log.debug("Injected quote row:\n%s", out.tail(3))
    return out