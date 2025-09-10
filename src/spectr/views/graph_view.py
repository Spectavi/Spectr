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
        if not self.is_backtest:
            self.set_interval(0.5, self.refresh)  # Force refresh loop, optional

    async def on_resize(self, event):
        """Handle resize events.

        For back-test graphs the render can be expensive, so rebuild the
        graph off the UI thread when the widget is resized.  Live graphs are
        lightweight, so they simply trigger a normal refresh.
        """
        if self.is_backtest:
            # Keep the previous render until the updated one is ready to avoid
            # blocking the interface.
            self.pre_rendered = await asyncio.to_thread(self.build_graph)
            self.refresh()
        else:
            self.pre_rendered = None
            self.refresh()  # Force redraw when size changes

    def watch_df(self, old, new):
        self.pre_rendered = None
        self.refresh()

    def watch_symbol(self, old, new):
        self.pre_rendered = None
        self.refresh()

    def watch_quote(self, old, new):
        self.pre_rendered = None
        self.refresh()

    def watch_is_backtest(self, old, new):
        self.pre_rendered = None
        self.refresh()

    def load_df(self, df, args, indicators=None):
        """Store the DataFrame and redraw on next refresh."""
        self.df = df
        self.args = args
        if indicators is not None:
            self.indicators = indicators
        self.pre_rendered = None
        self.refresh()

    def render(self):
        if self.pre_rendered is not None:
            return self.pre_rendered
        return self.build_graph()

    def build_graph(self):
        if self.df is None or self.df.empty:
            return "Waiting for chart data..."

        max_points = max(int(self.size.width * self.args.scale), 10)

        if not self.is_backtest and len(self.df) > max_points:
            # Live view: only show the tail that fits the terminal width
            df = self.df.tail(max_points)
        elif self.is_backtest:
            # Back-test or small frame: show everything
            df = self.df.copy()
        else:
            df = self.df.copy()

        # Extract time labels and prices

        dates = df.index.tz_convert("UTC").strftime("%Y-%m-%d %H:%M:%S")
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
        plt.date_form(
            input_form="Y-m-d H:M:S", output_form="H:M:S"
        )  # for times like 13:45:12

        inds = {spec.name.lower() for spec in self.indicators}

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

        if self.args.candles:
            # Add candlesticks
            plt.candlestick(dates, df[["Open", "Close", "High", "Low"]], yside="right")
        else:
            plt.plot(dates, df["Close"], yside="right", marker="hd", color="green")

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

        # Align the latest price_label in a center vertically
        y_min = current_price * 0.90
        y_max = current_price * 1.1
        # Apply limits to the right-hand axis where the price data is plotted
        plt.ylim(y_min, y_max, yside="right")

        # Show the current price on the y-axis and ensure it isn't truncated
        ticks = np.linspace(y_min, y_max, 5).tolist()
        labels = [f"{t:.2f}" for t in ticks]
        if current_price not in ticks:
            ticks.append(current_price)
            labels.append(price_label)
            ticks, labels = zip(*sorted(zip(ticks, labels)))
        plt.yticks(ticks, labels, yside="right")

        width = max(self.size.width, 20)  # leave some margin
        height = max(self.size.height, 10)  # reasonable min height
        plt.plotsize(width - 3, height)

        return Text.from_ansi(plt.build())
