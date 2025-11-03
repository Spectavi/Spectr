import logging
import os
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo
from tzlocal import get_localzone

import pandas as pd
import threading
import warnings

from .strategies import metrics

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API.*",
    category=UserWarning,
    module="pygame.pkgdata",
)
import pygame

from .fetch import data_interface

LOG_FILE = "signal_log.csv"

log = logging.getLogger(__name__)


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


def is_market_open_now(tz: ZoneInfo | None = None) -> bool:
    """Return True if the current time is within regular US market hours (9:30am-4pm ET)."""
    tz = tz or ZoneInfo("America/New_York")
    now = datetime.now(tz)
    if now.weekday() >= 5:  # Saturday/Sunday
        return False
    market_open = datetime.combine(now.date(), dtime(hour=9, minute=30), tzinfo=tz)
    market_close = datetime.combine(now.date(), dtime(hour=16, minute=0), tzinfo=tz)
    return market_open <= now <= market_close


CRYPTO_SUFFIXES = ("USD", "USDT", "USDC")


def is_crypto_symbol(symbol: str) -> bool:
    """Return True if *symbol* looks like a cryptocurrency pair."""
    sym = symbol.upper()
    return any(sym.endswith(sfx) and len(sym) > len(sfx) for sfx in CRYPTO_SUFFIXES)


def inject_quote_into_df(
    df: pd.DataFrame,
    quote: dict,
    tz=get_localzone(),  # default to system zone
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
        ts = pd.to_datetime(ts_raw, utc=True, errors="coerce").tz_convert(tz)

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
def get_historical_data(
    data_api: data_interface,
    bb_period,
    bb_dev,
    macd_thresh,
    symbol: str,
    from_date: str,
    to_date: str,
    *,
    indicators: list[metrics.IndicatorSpec] | None = None,
):
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
    df = data_api.fetch_chart_data_for_backtest(
        symbol, from_date=extended_from, to_date=to_date
    )

    # Fallback to 5min data if 1min isn't present.
    if df.empty:
        df = data_api.fetch_chart_data_for_backtest(
            symbol, from_date=extended_from, to_date=to_date, interval="5min"
        )
    # Compute indicators on the *full* frame (needs the extra bar)
    if indicators is None:
        indicators = [
            metrics.IndicatorSpec(
                name="MACD",
                params={"window_fast": 12, "window_slow": 26, "threshold": macd_thresh},
            ),
            metrics.IndicatorSpec(
                name="BollingerBands",
                params={"window": bb_period, "window_dev": bb_dev},
            ),
            metrics.IndicatorSpec(name="VWAP", params={}),
        ]
    df = metrics.analyze_indicators(df, indicators)
    quote = None
    try:
        quote = data_api.fetch_quote(symbol)
    except Exception:
        log.warning(f"Failed to fetch quote for {symbol}")

    # Trim back to the exact range the caller requested
    df = df.loc[from_date:to_date]  # string slice → inclusive

    return df, quote


def get_live_data(data_api: data_interface, symbol: str):
    df = data_api.fetch_chart_data(
        symbol,
        from_date=datetime.now().date().strftime("%Y-%m-%d"),
        to_date=datetime.now().date().strftime("%Y-%m-%d"),
    )
    quote = data_api.fetch_quote(symbol)
    return df, quote


def simulate_portfolio_end_value(trades: list[dict], price_df: pd.DataFrame, starting_cash: float) -> float:
    """Simulate end-of-period portfolio value from trades and last close.

    Assumes buys invest available cash and sells exit the recorded quantity.
    Ignores fees/commissions.
    """
    cash = float(starting_cash)
    qty = 0.0

    def _key(t: dict):
        return t.get("time")

    for tr in sorted(trades, key=_key):
        typ = str(tr.get("type", "")).lower()
        price = float(tr.get("price", 0) or 0)
        if typ == "buy":
            q = tr.get("quantity")
            if q is None:
                q = cash / price if price else 0.0
            qty = float(q)
            cash = 0.0
        elif typ == "sell":
            q = tr.get("quantity")
            if q is None:
                q = qty
            cash += float(q) * price
            qty = 0.0

    # Value any remaining position at final close
    last_close = None
    if price_df is not None and not price_df.empty:
        close_col = "close" if "close" in price_df.columns else "Close"
        last_close = float(price_df[close_col].iloc[-1])
    return cash + (qty * (last_close or 0.0))
