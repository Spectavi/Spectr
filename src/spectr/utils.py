
import logging
import os
from datetime import datetime, timedelta
from tzlocal import get_localzone

import pandas as pd
import threading
import pygame

import metrics
from fetch import data_interface

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


def human_format(num: float) -> str:
    """Return a human friendly string for large integers."""
    num = float(num)
    for unit in ("", "K", "M", "B", "T"):
        if abs(num) < 1000.0:
            if unit:
                return f"{num:.1f}{unit}"
            return f"{num:.0f}"
        num /= 1000.0
    return f"{num:.1f}P"


_mixer_initialized = False
_mixer_lock = threading.Lock()


def _ensure_mixer() -> None:
    """Initialize ``pygame``'s mixer if it hasn't been already."""
    global _mixer_initialized
    with _mixer_lock:
        if not _mixer_initialized:
            try:
                pygame.mixer.init()
                _mixer_initialized = True
            except Exception as exc:  # pragma: no cover - just in case
                log.error("pygame mixer init failed: %s", exc)


def play_sound(path: str) -> None:
    """Play a sound in a daemon thread to avoid blocking app exit.

    ``playsound`` caused Windows MCI errors; ``pygame`` provides a more
    reliable cross-platform backend.
    """

    if not os.path.exists(path):
        log.error("Sound file does not exist: %s", path)
        return

    def _play() -> None:
        _ensure_mixer()
        if not _mixer_initialized:
            return
        try:
            pygame.mixer.Sound(path).play()
        except Exception as exc:  # pragma: no cover - just in case
            log.error("play_sound failed: %s", exc)

    threading.Thread(target=_play, daemon=True).start()

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

# Grabs 1-day more than requested, calculates indicators, then trims to requested range.
def get_historical_data(data_api: data_interface, bb_period, bb_dev, macd_thresh, symbol: str, from_date: str, to_date: str):
    """
    Fetch OHLCV + quote for *symbol* in [from_date .. to_date] **inclusive**,
    but ensure that indicators that need a look-back window are fully
    initialised by pulling an extra day of data before `from_date`.
    """
    log.debug(f"Fetching historical data for {symbol}…")

    # Extend the request one calendar day back
    dt_from = datetime.strptime(from_date, "%Y-%m-%d").date()
    extended_from = (dt_from - timedelta(days=1)).strftime("%Y-%m-%d")
    log.debug(f"dt_from: {dt_from}")
    log.debug(f"extended_from: {extended_from}")

    # Pull the data and quote
    df = data_api.fetch_chart_data_for_backtest(symbol, from_date=extended_from, to_date=to_date)

    # Fallback to 5min data if 1min isn't present.
    if df.empty:
        df = data_api.fetch_chart_data_for_backtest(symbol, from_date=extended_from, to_date=to_date,
                                                    interval="5min")
    # Compute indicators on the *full* frame (needs the extra bar)
    df = metrics.analyze_indicators(df, bb_period, bb_dev, macd_thresh)
    quote = None
    try:
        quote = data_api.fetch_quote(symbol)
    except Exception:
        log.warning(f"Failed to fetch quote for {symbol}")

    # Trim back to the exact range the caller requested
    df = df.loc[from_date:to_date]  # string slice → inclusive

    return df, quote


def get_live_data(data_api: data_interface, symbol: str):
    df = data_api.fetch_chart_data(symbol, from_date=datetime.now().date().strftime("%Y-%m-%d"),
                                   to_date=datetime.now().date().strftime("%Y-%m-%d"))
    quote = data_api.fetch_quote(symbol)
    return df, quote