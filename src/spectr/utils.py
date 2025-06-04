
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from tzlocal import get_localzone

import pandas as pd
import pytz


LOG_FILE = 'signal_log.csv'
CACHE_DIR = 'cache'
CACHE_PATH_STR = ".{}.cache"

log = logging.getLogger(__name__)

def save_cache(symbol, df):
    if df is not None:
        cache_path = os.path.join(CACHE_DIR, CACHE_PATH_STR.format(symbol))

        # Fastparquet (the default engine) struggles with timezone aware
        # datetimes.  Convert any tz-aware index to UTC and drop the timezone
        # before persisting so we always write timezone naive timestamps.
        df_to_save = df.copy()
        if isinstance(df_to_save.index, pd.DatetimeIndex) and df_to_save.index.tz is not None:
            df_to_save.index = df_to_save.index.tz_convert("UTC").tz_localize(None)

        df_to_save.to_parquet(cache_path)
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
    tz=get_localzone(),                        # default to system zone
) -> pd.DataFrame:
    """
    Append the latest quote as a new bar and guarantee the entire frame
    ends up in *tz*.
    """
    if df.empty:
        raise ValueError("DataFrame is empty; cannot append quote.")

    if df.index.tz is None:  # naïve → assume UTC
        df.index = df.index.tz_localize("America/New_York")

    log.debug(f"tz before: {df.index.tz}")
    df.index = df.index.tz_convert(tz)  # now local-time

    ts_raw = quote.get("timestamp") or datetime.utcnow().timestamp()

    if isinstance(ts_raw, (int, float)):
        ts = pd.to_datetime(ts_raw, unit="s", utc=True).tz_convert(tz)
    else:  # ISO string from FMP
        ts = (
            pd.to_datetime(ts_raw, utc=True, errors="coerce")
            .tz_convert(tz)
        )

    ts = ts.floor("T")  # align to minute grid

    # ------------------------------------------------------------------
    # 3. Compose the new row (fallback to last OHLC/vol)
    # ------------------------------------------------------------------
    last = df.iloc[-1]
    new_row = pd.DataFrame(
        {
            "open": last["close"],
            "high": last["high"],
            "low": last["low"],
            "close": quote["price"],
            "volume": last["volume"],
        },
        index=pd.Index([ts], name="datetime"),
    )

    out = pd.concat([df, new_row]).sort_index()
    out = out[~out.index.duplicated(keep="last")]

    log.debug("Injected quote row:\n%s", out.tail(3))
    return out