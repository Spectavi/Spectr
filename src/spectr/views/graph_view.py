import asyncio
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotext as plt
from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static
import numpy

log = logging.getLogger(__name__)


class GraphView(Static):
    symbol: reactive[str] = reactive("")
    quote: reactive[dict] = reactive(None)
    is_backtest: reactive[bool] = reactive(False)
    indicators: reactive[list] = reactive([])
    frozen: reactive[bool] = reactive(False)
    # When True, limit data to what fits widget width; when False, plot all rows
    crop_to_width: reactive[bool] = reactive(True)
    # Disable periodic refresh loop (used by backtest results modal)
    auto_refresh_enabled: bool = True

    # Internal: handle to periodic refresh timer
    _refresh_timer = None

    def update_symbol(self, value: str):
        self.symbol = value

    def __init__(
        self, df=None, args=None, indicators=None, pre_rendered=None, **kwargs
    ):
        super().__init__(**kwargs)
        self.df = df
        self.args = args
        self.indicators = indicators or []
        self.pre_rendered = pre_rendered

    def on_mount(self):
        if self.frozen:
            return
        # Only start a periodic refresh for live views when enabled
        if self.auto_refresh_enabled and not self.is_backtest:
            self._refresh_timer = self.set_interval(0.5, self.refresh)

    async def on_resize(self, event):
        """Handle resize events.

        For back-test graphs the render can be expensive, so rebuild the
        graph off the UI thread when the widget is resized.  Live graphs are
        lightweight, so they simply trigger a normal refresh.
        """
        if self.frozen:
            # Do not rebuild or refresh when frozen
            return
        if self.is_backtest:
            # Keep the previous render until the updated one is ready to avoid
            # blocking the interface.
            self.pre_rendered = await asyncio.to_thread(self.build_graph)
            self.refresh()
        else:
            self.pre_rendered = None
            self.refresh()  # Force redraw when size changes

    def watch_df(self, old, new):
        if not self.frozen:
            self.pre_rendered = None
            self.refresh()

    def watch_symbol(self, old, new):
        if not self.frozen:
            self.pre_rendered = None
            self.refresh()

    def watch_quote(self, old, new):
        if not self.frozen:
            self.pre_rendered = None
            self.refresh()

    def watch_is_backtest(self, old, new):
        if not self.frozen:
            self.pre_rendered = None
            self.refresh()
        # Stop periodic refresh when entering backtest mode
        if new and self._refresh_timer is not None:
            try:
                self._refresh_timer.stop()
            except Exception:
                pass
            self._refresh_timer = None

    def watch_crop_to_width(self, old, new):
        if not self.frozen:
            self.pre_rendered = None
            self.refresh()

    async def on_unmount(self) -> None:
        # Ensure any periodic timer is stopped when the widget is removed
        if self._refresh_timer is not None:
            try:
                self._refresh_timer.stop()
            except Exception:
                pass
            self._refresh_timer = None

    def load_df(self, df, args, indicators=None):
        """Store the DataFrame and redraw on next refresh."""
        if self.frozen:
            # Ignore updates when frozen to preserve the rendered snapshot
            return
        self.df = df
        self.args = args
        if indicators is not None:
            self.indicators = indicators
        self.pre_rendered = None
        self.refresh()

    def render(self):
        if self.pre_rendered is not None:
            return self.pre_rendered
        if self.frozen:
            # Build once and keep
            self.pre_rendered = self.build_graph()
            return self.pre_rendered
        return self.build_graph()

    def build_graph(self):
        if self.df is None or self.df.empty:
            return "Waiting for chart data..."

        max_points = max(int(self.size.width * self.args.scale), 10)

        if self.crop_to_width and len(self.df) > max_points:
            # Only show the tail that reasonably fits the terminal width
            df = self.df.tail(max_points)
        else:
            # Show the entire range (used by backtest results)
            df = self.df.copy()

        # Extract time labels robustly (handle naive and tz-aware indices)
        idx = df.index
        if not isinstance(idx, pd.DatetimeIndex):
            try:
                idx = pd.to_datetime(idx, errors="coerce")
            except Exception:
                return "Invalid time index"
        try:
            if idx.tz is not None:
                idx = idx.tz_convert("UTC")
        except Exception:
            # If conversion fails, keep as-is
            pass
        dates = idx.strftime("%Y-%m-%d %H:%M:%S")
        # ohlc_data = list(zip(df['open'], df['high'], df['low'], df['close']))

        # Rename the 'open' column to 'Open'
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

        # Clear and configure plotext
        plt.clf()
        plt.canvas_color("default")
        plt.axes_color("default")
        plt.ticks_color("default")
        plt.grid(False)
        # Include date on backtest charts to disambiguate multi-day ranges
        if self.is_backtest:
            plt.date_form(input_form="Y-m-d H:M:S", output_form="m/d/Y H:M")
        else:
            plt.date_form(input_form="Y-m-d H:M:S", output_form="H:M:S")

        inds = {spec.name.lower() for spec in self.indicators}
        # In backtest results we want a clean price view only
        if self.is_backtest:
            inds = set()

        # Plot Bollinger Bands
        if "bollingerbands" in inds:
            if "bb_upper" in df.columns and not df["bb_upper"].isna().all():
                plt.plot(
                    dates,
                    df["bb_upper"],
                    color="red",
                    label="BB Upper",
                    yside="right",
                    marker="dot",
                )
            if "bb_mid" in df.columns and not df["bb_mid"].isna().all():
                plt.plot(
                    dates,
                    df["bb_mid"],
                    color="blue",
                    label="BB Mid",
                    yside="right",
                    marker="-",
                )
            if "bb_lower" in df.columns and not df["bb_lower"].isna().all():
                plt.plot(
                    dates,
                    df["bb_lower"],
                    color="green",
                    label="BB Lower",
                    yside="right",
                    marker="dot",
                )

        if "vwap" in inds and "VWAP" in df.columns:
            plt.plot(
                dates,
                df["VWAP"],
                yside="right",
                marker="hd",
                color="orange",
                label="VWAP",
            )

        if "sma" in inds:
            for spec in self.indicators:
                if spec.name.lower() != "sma":
                    continue
                col_type = spec.params.get("type")
                if col_type:
                    col = f"ma_{col_type}"
                else:
                    window = spec.params.get("window", 20)
                    col = f"sma_{window}"
                if col in df.columns:
                    plt.plot(
                        dates, df[col], yside="right", label=col.upper(), marker="dot"
                    )

        # Prefer candles when requested and OHLC columns exist; otherwise fall back to a close line
        ohlc_cols = ["Open", "Close", "High", "Low"]
        if self.args.candles and all(col in df.columns for col in ohlc_cols):
            plt.candlestick(dates, df[ohlc_cols], yside="right")
        else:
            if "Close" in df.columns:
                plt.plot(dates, df["Close"], yside="right", marker="hd", color="green")
            else:
                # Nothing to plot; return a friendly message
                return "No plottable price series available."

        # -------- BUY / SELL MARKERS ---------
        last_buy_y = last_buy_x = None
        last_sell_y = last_sell_x = None
        if "buy_signals" in df.columns:
            buy_mask = df["buy_signals"].astype(bool)

            # Plot green ▲ for buys
            if buy_mask.any():
                buy_x = np.array(dates)[buy_mask]
                buy_y = df.loc[buy_mask, "Close"]
                plt.scatter(
                    buy_x, buy_y, marker="O", color="green", label="Buy", yside="right"
                )
                last_buy_x, last_buy_y = buy_x[-1], float(buy_y.iloc[-1])

        if "sell_signals" in df.columns:
            sell_mask = df["sell_signals"].astype(bool)

            # Plot red ▼ for sells
            if sell_mask.any():
                sell_x = np.array(dates)[sell_mask]
                sell_y = df.loc[sell_mask, "Close"]
                plt.scatter(
                    sell_x, sell_y, marker="X", color="red", label="Sell", yside="right"
                )
                # remember the LAST sell to label on the right
                last_sell_x, last_sell_y = sell_x[-1], float(sell_y.iloc[-1])

        # -------- PRICE LABELS ON THE RIGHT EDGE -------------------------

        if last_buy_y is not None:
            plt.text(
                f"${last_buy_y:.2f}",
                last_buy_x,
                last_buy_y,
                color="green",
                yside="right",
            )

        if last_sell_y is not None:
            plt.text(
                f"${last_sell_y:.2f}",
                last_sell_x,
                last_sell_y,
                color="red",
                yside="right",
            )

        last_x = dates[-1]
        current_price = df["Close"].iloc[-1]
        price_label = f"${current_price:.2f}"

        if not self.is_backtest:
            plt.text(
                price_label,
                last_x,
                current_price + 0.5,
                color="green",
                style="#price_label",
                yside="right",
                alignment="right",
            )
            plt.title(f"{self.symbol} - {price_label}")
        else:
            plt.title(self.symbol)

        # Compute y-range based on visible data with ±5% padding
        y_series = []
        # Base price data (candles or close line)
        if self.args.candles and all(col in df.columns for col in ["High", "Low"]):
            y_series.append(df["High"])  # highs
            y_series.append(df["Low"])   # lows
        elif "Close" in df.columns:
            y_series.append(df["Close"])  # line mode

        # Overlays that are plotted on the right axis
        if "bollingerbands" in inds:
            for col in ("bb_upper", "bb_mid", "bb_lower"):
                if col in df.columns and not df[col].isna().all():
                    y_series.append(df[col])
        if "vwap" in inds and "VWAP" in df.columns:
            y_series.append(df["VWAP"])
        if "sma" in inds:
            for spec in self.indicators:
                if spec.name.lower() != "sma":
                    continue
                col_type = spec.params.get("type")
                if col_type:
                    col = f"ma_{col_type}"
                else:
                    window = spec.params.get("window", 20)
                    col = f"sma_{window}"
                if col in df.columns:
                    y_series.append(df[col])

        # Flatten and filter numeric values
        vals = []
        for s in y_series:
            try:
                arr = np.asarray(s.dropna(), dtype=float)
                if arr.size:
                    vals.extend(arr.tolist())
            except Exception:
                pass

        if vals:
            y_min_raw = min(vals)
            y_max_raw = max(vals)
        else:
            # Fallback to current price if no series collected
            y_min_raw = float(current_price)
            y_max_raw = float(current_price)

        if y_min_raw == y_max_raw:
            pad = abs(y_min_raw) * 0.02 or 1.0
            y_min = y_min_raw - pad
            y_max = y_max_raw + pad
        else:
            diff = y_max_raw - y_min_raw
            y_min = y_min_raw - (diff * 0.1)
            y_max = y_max_raw + (diff * 0.1)

        plt.ylim(y_min, y_max)

        # Show the current price on the y-axis and ensure it isn't truncated
        ticks = np.linspace(y_min, y_max, 5).tolist()
        labels = [f"{t:.2f}" for t in ticks]
        if current_price not in ticks:
            ticks.append(current_price)
            labels.append(price_label)
            ticks, labels = zip(*sorted(zip(ticks, labels)))
        plt.yticks(ticks, labels, yside="right")

        # Size the plot to the widget's allocated size.
        # Keep a small margin to avoid clipping borders.
        width = max(int(self.size.width), 20)
        height = max(int(self.size.height), 10)
        plt.plotsize(max(width - 2, 10), max(height - 1, 8))

        return Text.from_ansi(plt.build())
