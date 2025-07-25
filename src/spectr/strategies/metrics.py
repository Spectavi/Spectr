import math
import pandas as pd
import ta
from ta.trend import MACD
from ta.volatility import BollingerBands

from .trading_strategy import IndicatorSpec


def analyze_indicators(
    df: pd.DataFrame, indicators: list[IndicatorSpec]
) -> pd.DataFrame:
    """Calculate and append indicators defined by ``indicators``."""
    df = df.copy()

    for spec in indicators:
        name = spec.name.lower()
        params = spec.params or {}

        if name == "macd" and len(df.index) > 2:
            fast = params.get("window_fast", 12)
            slow = params.get("window_slow", 26)
            thresh = params.get("threshold", 0.0)
            macd = MACD(close=df["close"], window_fast=fast, window_slow=slow)
            df["macd"] = macd.macd()
            df["macd_signal"] = macd.macd_signal()
            df["macd_close"] = (df["macd"] - df["macd_signal"]).abs() < thresh
            df["macd_angle"] = macd_angle(df["close"], fast, slow, 9)

            df["macd_crossover"] = None
            crossover = (df["macd"] > df["macd_signal"]) & (
                df["macd"].shift(1) <= df["macd_signal"].shift(1)
            )
            crossunder = (df["macd"] < df["macd_signal"]) & (
                df["macd"].shift(1) >= df["macd_signal"].shift(1)
            )
            df.loc[crossover, "macd_crossover"] = "buy"
            df.loc[crossunder, "macd_crossover"] = "sell"

        elif name == "bollingerbands" and len(df.index) > params.get("window", 20):
            window = params.get("window", 20)
            window_dev = params.get("window_dev", 2.0)
            bb = BollingerBands(
                close=df["close"], window=window, window_dev=window_dev, fillna=False
            )
            df["bb_upper"] = bb.bollinger_hband()
            df["bb_lower"] = bb.bollinger_lband()
            df["bb_angle"] = bollinger_band_angle(df["close"], period=3)  # Very short window to get angle.
            df["bb_mid"] = (df["bb_upper"] + df["bb_lower"]) / 2

        elif name == "vwap" and {"close", "volume"}.issubset(df.columns):
            pv = df["close"] * df["volume"]
            df["vwap"] = pv.cumsum() / df["volume"].cumsum()

        elif name == "sma":
            window = params.get("window", 20)
            col_type = params.get("type")
            if col_type:
                col = f"ma_{col_type}"
            else:
                col = f"sma_{window}"
            df[col] = df["close"].rolling(window=window, min_periods=1).mean()

    return df


def bollinger_band_angle(close_series, period=20):
    """
    Calculates the angle (in degrees) of the middle Bollinger Band line.

    Parameters:
        close_series (pd.Series): The closing price series.
        period (int): The period for the moving average (default 20).

    Returns:
        float: The angle in degrees. Positive = upward slope, Negative = downward.
    """
    if len(close_series) < period + 1:
        return None  # Not enough data

    middle_band = close_series.rolling(window=period).mean()
    recent = middle_band.dropna().iloc[-2:]

    if len(recent) < 2:
        return None

    dy = recent.iloc[1] - recent.iloc[0]
    dx = 1  # time step is 1 unit (e.g., 1 minute)
    radians = math.atan2(dy, dx)
    degrees = math.degrees(radians)

    return degrees


def macd_angle(close_series, fast=12, slow=26, signal=9):
    """
    Calculates the angle (in degrees) of the MACD line using its last two values.

    Parameters:
        close_series (pd.Series): Series of closing prices.
        fast (int): Fast EMA period.
        slow (int): Slow EMA period.
        signal (int): Signal EMA period.

    Returns:
        float: Angle of MACD line in degrees. Positive = upward slope, Negative = downward.
    """
    if len(close_series) < slow + signal + 2:
        return None  # not enough data

    macd_indicator = ta.trend.MACD(
        close=close_series, window_slow=slow, window_fast=fast, window_sign=signal
    )
    macd_series = macd_indicator.macd().dropna()

    if len(macd_series) < 2:
        return None

    recent = macd_series.iloc[-2:]
    dy = recent.iloc[1] - recent.iloc[0]
    dx = 1  # time step (1 bar)

    radians = math.atan2(dy, dx)
    degrees = math.degrees(radians)

    return degrees
