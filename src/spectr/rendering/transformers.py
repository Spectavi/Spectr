from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from .models import (
    ChartCandles,
    ChartSeries,
    ChartText,
    ChartTicks,
    ChartViewModel,
    DateForm,
)


@dataclass(frozen=True)
class PriceChartInputs:
    df: pd.DataFrame
    symbol: str
    indicators: Sequence[object]
    args: object
    is_backtest: bool
    crop_to_width: bool
    width: int


def build_price_model(inputs: PriceChartInputs) -> ChartViewModel | None:
    df = inputs.df
    if df is None or df.empty:
        return None

    max_points = max(int(inputs.width * inputs.args.scale), 10)
    if inputs.crop_to_width and len(df) > max_points:
        df = df.tail(max_points)
    else:
        df = df.copy()

    idx = df.index
    if not isinstance(idx, pd.DatetimeIndex):
        try:
            idx = pd.to_datetime(idx, errors="coerce")
        except Exception:
            return None
    try:
        if idx.tz is not None:
            idx = idx.tz_convert("UTC")
    except Exception:
        pass

    dates = idx.strftime("%Y-%m-%d %H:%M:%S")

    df = df.rename(
        columns={
            "low": "Low",
            "high": "High",
            "open": "Open",
            "close": "Close",
            "volume": "Volume",
            "vwap": "VWAP",
        }
    )

    inds = {getattr(spec, "name", "").lower() for spec in inputs.indicators}
    if inputs.is_backtest:
        inds = set()

    series: list[ChartSeries] = []
    texts: list[ChartText] = []
    candles: ChartCandles | None = None

    ohlc_cols = ["Open", "Close", "High", "Low"]
    if getattr(inputs.args, "candles", False) and all(col in df.columns for col in ohlc_cols):
        candles = ChartCandles(dates, df[ohlc_cols])
    elif "Close" in df.columns:
        series.append(
            ChartSeries(
                dates,
                df["Close"].tolist(),
                color="green",
                marker="hd",
            )
        )
    else:
        return None

    if "bollingerbands" in inds:
        for col, color, label, marker in (
            ("bb_upper", "red", "BB Upper", "dot"),
            ("bb_mid", "blue", "BB Mid", "-"),
            ("bb_lower", "green", "BB Lower", "dot"),
        ):
            if col in df.columns and not df[col].isna().all():
                series.append(
                    ChartSeries(dates, df[col].tolist(), color=color, label=label, marker=marker)
                )

    if "vwap" in inds and "VWAP" in df.columns:
        series.append(
            ChartSeries(
                dates,
                df["VWAP"].tolist(),
                color="orange",
                label="VWAP",
                marker="hd",
            )
        )

    if "sma" in inds:
        for spec in inputs.indicators:
            if getattr(spec, "name", "").lower() != "sma":
                continue
            col_type = spec.params.get("type") if hasattr(spec, "params") else None
            if col_type:
                col = f"ma_{col_type}"
            else:
                window = spec.params.get("window", 20) if hasattr(spec, "params") else 20
                col = f"sma_{window}"
            if col in df.columns:
                series.append(
                    ChartSeries(
                        dates,
                        df[col].tolist(),
                        label=col.upper(),
                        marker="dot",
                    )
                )

    last_buy_x = last_buy_y = None
    last_sell_x = last_sell_y = None
    if "buy_signals" in df.columns:
        buy_mask = df["buy_signals"].astype(bool)
        if buy_mask.any():
            buy_x = np.array(dates)[buy_mask]
            buy_y = df.loc[buy_mask, "Close"].astype(float)
            series.append(
                ChartSeries(
                    buy_x.tolist(),
                    buy_y.tolist(),
                    color="green",
                    label="Buy",
                    marker="O",
                    kind="scatter",
                )
            )
            last_buy_x = buy_x[-1]
            last_buy_y = float(buy_y.iloc[-1])

    if "sell_signals" in df.columns:
        sell_mask = df["sell_signals"].astype(bool)
        if sell_mask.any():
            sell_x = np.array(dates)[sell_mask]
            sell_y = df.loc[sell_mask, "Close"].astype(float)
            series.append(
                ChartSeries(
                    sell_x.tolist(),
                    sell_y.tolist(),
                    color="red",
                    label="Sell",
                    marker="X",
                    kind="scatter",
                )
            )
            last_sell_x = sell_x[-1]
            last_sell_y = float(sell_y.iloc[-1])

    if last_buy_y is not None:
        texts.append(
            ChartText(
                f"${last_buy_y:.2f}",
                last_buy_x,
                last_buy_y,
                color="green",
            )
        )
    if last_sell_y is not None:
        texts.append(
            ChartText(
                f"${last_sell_y:.2f}",
                last_sell_x,
                last_sell_y,
                color="red",
            )
        )

    current_price = float(df["Close"].iloc[-1])
    price_label = f"${current_price:.2f}"
    title = inputs.symbol
    if not inputs.is_backtest:
        texts.append(
            ChartText(
                price_label,
                dates[-1],
                current_price + 0.5,
                color="green",
                alignment="right",
                style="#price_label",
            )
        )
        title = f"{inputs.symbol} - {price_label}"

    y_series: list[Iterable[float]] = []
    if getattr(inputs.args, "candles", False) and all(col in df.columns for col in ["High", "Low"]):
        y_series.append(df["High"].astype(float))
        y_series.append(df["Low"].astype(float))
    elif "Close" in df.columns:
        y_series.append(df["Close"].astype(float))

    if "bollingerbands" in inds:
        for col in ("bb_upper", "bb_mid", "bb_lower"):
            if col in df.columns and not df[col].isna().all():
                y_series.append(df[col].astype(float))

    if "vwap" in inds and "VWAP" in df.columns:
        y_series.append(df["VWAP"].astype(float))

    if "sma" in inds:
        for spec in inputs.indicators:
            if getattr(spec, "name", "").lower() != "sma":
                continue
            col_type = spec.params.get("type") if hasattr(spec, "params") else None
            if col_type:
                col = f"ma_{col_type}"
            else:
                window = spec.params.get("window", 20) if hasattr(spec, "params") else 20
                col = f"sma_{window}"
            if col in df.columns:
                y_series.append(df[col].astype(float))

    vals: list[float] = []
    for series_vals in y_series:
        try:
            arr = np.asarray(series_vals.dropna(), dtype=float)
            if arr.size:
                vals.extend(arr.tolist())
        except Exception:
            pass

    if vals:
        y_min_raw = min(vals)
        y_max_raw = max(vals)
    else:
        y_min_raw = current_price
        y_max_raw = current_price

    if y_min_raw == y_max_raw:
        pad = abs(y_min_raw) * 0.02 or 1.0
        y_min = y_min_raw - pad
        y_max = y_max_raw + pad
    else:
        diff = y_max_raw - y_min_raw
        y_min = y_min_raw - (diff * 0.1)
        y_max = y_max_raw + (diff * 0.1)

    ticks = np.linspace(y_min, y_max, 5).tolist()
    labels = [f"{t:.2f}" for t in ticks]
    if current_price not in ticks:
        ticks.append(current_price)
        labels.append(price_label)
        ticks, labels = zip(*sorted(zip(ticks, labels)))

    date_form = DateForm("Y-m-d H:M:S", "m/d/Y H:M" if inputs.is_backtest else "H:M:S")

    return ChartViewModel(
        series=series,
        candles=candles,
        title=title,
        texts=texts,
        y_limits=(y_min, y_max),
        y_ticks=ChartTicks(list(ticks), list(labels)),
        date_form=date_form,
        grid=False,
    )


def build_macd_model(df: pd.DataFrame, *, args: object, is_backtest: bool, width: int) -> ChartViewModel | None:
    if df is None or df.empty or "macd" not in df.columns or "macd_signal" not in df.columns:
        return None

    df = df.dropna(subset=["macd", "macd_signal"]).copy()
    max_points = max(int(width * args.scale), 10)
    if not is_backtest and len(df) > max_points:
        df = df.tail(max_points)

    if len(df) < 2:
        return None

    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index, errors="coerce")
        except Exception:
            return None

    times = df.index.strftime("%Y-%m-%d %H:%M:%S")

    series = [
        ChartSeries([times[0], times[-1]], [0, 0], color="gray", marker="-", label=""),
        ChartSeries(times.tolist(), df["macd"].tolist(), color="green", label="MACD", marker="hd"),
        ChartSeries(times.tolist(), df["macd_signal"].tolist(), color="red", label="Signal", marker="hd"),
    ]

    macd_range = float(df["macd"].max()) - float(df["macd_signal"].min())
    center = float(df["macd"].iloc[-1])
    margin = macd_range * 1.2 if macd_range else 1.0

    return ChartViewModel(
        series=series,
        y_limits=(center - margin, center + margin),
        date_form=DateForm("Y-m-d H:M:S", "Y-m-d H:M:S"),
        ticks_color="grey",
        hide_xticks=True,
        grid=False,
    )


def build_volume_model(df: pd.DataFrame, *, args: object, width: int) -> ChartViewModel | None:
    if df is None or df.empty or "volume" not in df.columns or "close" not in df.columns:
        return None

    df = df.copy()
    max_points = max(int(width * args.scale), 10)
    if len(df) > max_points:
        df = df.tail(max_points)

    times = df.index.strftime("%Y-%m-%d %H:%M")
    prev_close = df["close"].shift(1).fillna(df["close"])
    colors = np.where(df["close"] >= prev_close, "green", "red")

    max_vol = float(df["volume"].astype(float).max())
    top = int(np.ceil(max_vol * 1.1)) if max_vol > 0 else 1
    tick_step = max(1, top // 4)
    ticks = np.arange(0, top + tick_step, tick_step)

    series = [
        ChartSeries(
            times.tolist(),
            df["volume"].to_numpy(dtype=float).tolist(),
            label="Volume",
            kind="bar",
            colors=colors.tolist(),
            marker="hd",
            width=0.4,
        )
    ]

    return ChartViewModel(
        series=series,
        hide_xticks=True,
        y_limits=(0, top),
        y_ticks=ChartTicks(ticks.tolist(), [str(t) for t in ticks]),
        grid=False,
    )


def build_equity_model(data: Sequence[tuple[object, float, float]]) -> ChartViewModel | None:
    if not data:
        return None

    raw_times = [d[0] for d in data]
    cash_vals = [d[1] for d in data]
    total_vals = [d[2] for d in data]
    x_vals = list(range(len(raw_times)))

    series = [
        ChartSeries(x_vals, cash_vals, color="blue", marker="hd", label="Cash"),
        ChartSeries(x_vals, total_vals, color="red", marker="hd", label="Total"),
    ]

    step = max(1, len(x_vals) // 10)
    tick_positions = x_vals[::step]
    tick_labels = [raw_times[i].strftime("%H:%M:%S") for i in tick_positions]

    ymin = min(min(cash_vals), min(total_vals)) * 0.95
    ymax = max(max(cash_vals), max(total_vals)) * 1.05

    return ChartViewModel(
        series=series,
        x_ticks=ChartTicks(tick_positions, tick_labels, yside="right"),
        y_limits=(ymin, ymax),
        grid=False,
    )
