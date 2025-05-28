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

    def update_symbol(self, value: str):
        self.symbol = value

    def __init__(self, df=None, args=None, **kwargs):
        super().__init__(**kwargs)
        self.df = df
        self.args = args

    def on_mount(self):
        self.set_interval(0.5, self.refresh)  # Force refresh loop, optional

    def on_resize(self, event):
        self.refresh()  # Force redraw when size changes

    def watch_df(self, old, new):
        self.refresh()

    def watch_symbol(self, old, new):
        self.refresh()

    def watch_quote(self, old, new):
        self.refresh()

    def watch_is_backtest(self, old, new):
        self.refresh()

    def load_df(self, df, args):
        """Store the DataFrame and redraw on next refresh."""
        self.df = df
        self.args = args
        self.refresh()

    def render(self):
        log.debug("Rendering graph")
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

        dates = df.index.strftime("%Y-%m-%d %H:%M:%S")
        #ohlc_data = list(zip(df['open'], df['high'], df['low'], df['close']))

        # Rename the 'open' column to 'Open'
        df = df.rename(columns={'low': 'Low', 'high': 'High', 'open': 'Open', 'close': 'Close', 'volume': 'Volume', 'vwap': 'VWAP'})

        # Clear and configure plotext
        plt.clf()
        plt.canvas_color('default')
        plt.axes_color('default')
        plt.ticks_color('default')
        plt.grid(False)
        plt.date_form(input_form="Y-m-d H:M:S", output_form="H:M:S")  # for times like 13:45:12

        # Plot Bollinger Bands
        if "bb_upper" in df.columns and not df["bb_upper"].isna().all():
            plt.plot(dates, df['bb_upper'], color="red", label="BB Upper", yside="right", marker='dot')
        if "bb_mid" in df.columns and not df["bb_mid"].isna().all():
            plt.plot(dates, df['bb_mid'], color="blue", label="BB Mid", yside="right", marker='-')
        if "bb_lower" in df.columns and not df["bb_lower"].isna().all():
            plt.plot(dates, df['bb_lower'], color="green", label="BB Lower", yside="right", marker='dot')

        if "VWAP" in df.columns:
            plt.plot(dates, df['VWAP'], yside='right', marker='hd', color="orange", label="VWAP")

        if self.args.candles:
            # Add candlesticks
            plt.candlestick(dates, df[['Open', 'Close', 'High', 'Low']], yside='right')
        else:
            plt.plot(dates, df['Close'], yside='right', marker='hd', color='green')

        # -------- BUY / SELL MARKERS ---------
        last_buy_y = last_buy_x = None
        last_sell_y = last_sell_x = None
        if 'buy_signals' in df.columns:
            log.debug(f"buy_signals column detected: {df.columns}")
            buy_mask = df['buy_signals'].astype(bool)
            log.debug(f"buy_mask: {buy_mask}")

            # Plot green ▲ for buys
            if buy_mask.any():
                buy_x = np.array(dates)[buy_mask]
                buy_y = df.loc[buy_mask, 'Close']
                plt.scatter(buy_x, buy_y,
                            marker='dot', color='green',
                            label = 'Buy', yside = 'right')
                last_buy_x, last_buy_y = buy_x[-1], float(buy_y.iloc[-1])

        if 'sell_signals' in df.columns:
            log.debug(f"sell_signals column detected: {df.columns}")
            sell_mask = df['sell_signals'].astype(bool)
            log.debug(f"sell_mask: {sell_mask}")

            # Plot red ▼ for sells
            if sell_mask.any():
                sell_x = np.array(dates)[sell_mask]
                sell_y = df.loc[sell_mask, 'Close']
                plt.scatter(sell_x, sell_y,
                             marker = 'dot', color = 'red',
                             label = 'Sell', yside = 'right')
                # remember the LAST sell to label on the right
                last_sell_x, last_sell_y = sell_x[-1], float(sell_y.iloc[-1])

        # -------- PRICE LABELS ON THE RIGHT EDGE -------------------------

        if last_buy_y is not None:
            plt.text(f"${last_buy_y:.2f}",
                                  last_buy_x,
                                  last_buy_y,
                                  color = "green",
            yside = "right")

        if last_sell_y is not None:
            plt.text(f"${last_sell_y:.2f}",
                                last_sell_x,
                                last_sell_y,
                                color = "red",
            yside = "right")

        last_x = dates[-2]
        last_y = df['Close'].iloc[-1]
        price_label = f"${last_y:.2f}"

        plt.text(price_label, last_x, last_y + 0.5, color="green", style='#price_label', yside='right')
        plt.title(f"{self.symbol} - {price_label}")

        # Align the latest price_label in a center vertically
        current_price = df['Close'].iloc[-1]
        plt.ylim(current_price * 0.90, current_price * 1.1)

        width = max(self.size.width, 20)  # leave some margin
        height = max(self.size.height, 10)  # reasonable min height
        plt.plotsize(width-3, height)

        return Text.from_ansi(plt.build())
