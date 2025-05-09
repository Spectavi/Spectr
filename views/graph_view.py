import logging

import plotext as plt
from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

log = logging.getLogger(__name__)

class GraphView(Static):
    symbol: reactive[str] = reactive("")

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

    def render(self):
        log.debug("Rendering graph")
        return self.build_graph()

    def build_graph(self):
        if self.df is None or self.df.empty:
            return "Waiting for data..."

        # Limit the number of bars to fit in terminal width
        max_points = max(int(self.size.width * self.args.scale), 10)
        df = self.df.tail(max_points)

        # Extract time labels and prices
        dates = df.index.strftime('%Y-%m-%d %H:%M:%S')
        #ohlc_data = list(zip(df['open'], df['high'], df['low'], df['close']))

        # Rename the 'open' column to 'Open'
        df = df.rename(columns={'low': 'Low', 'high': 'High', 'open': 'Open', 'close': 'Close'})

        # Clear and configure plotext
        plt.clf()
        plt.canvas_color('default')
        plt.axes_color('default')
        plt.ticks_color('default')
        plt.grid(False)
        plt.date_form(input_form="Y-m-d H:M:S", output_form="H:M:S")  # for times like 13:45:12

        # Plot Bollinger Bands
        plt.plot(dates, df['bb_upper'], color="red", label="BB Upper", yside="right", marker='dot')
        plt.plot(dates, df['bb_mid'], color="blue", label="BB Mid", yside="right", marker='-')
        plt.plot(dates, df['bb_lower'], color="lime", label="BB Lower", yside="right", marker='dot')

        # Add candlesticks
        # plt.candlestick(dates, df[['Open', 'Close', 'High', 'Low']], yside='right')
        plt.plot(dates, df['Close'], yside='right', marker='hd', color='green')

        last_x = dates[-2]
        last_y = df['Close'].iloc[-1]
        price = f"${last_y:.2f}"

        plt.text(price, last_x, last_y + 0.5, color="green", style='#price_label', yside='right')
        plt.title(f"{self.symbol} - {price}")

        # Align the latest price in a center vertically
        highs = self.df['bb_upper']
        lows = self.df['bb_lower']
        current_price = df['Close'].iloc[-1]
        price_range = highs.max() * 1.05 - lows.min() * 1.05
        margin = price_range * 4 if price_range else 1
        plt.ylim(current_price - margin, current_price + margin)

        width = max(self.size.width, 20)  # leave some margin
        height = max(self.size.height, 10)  # reasonable min height
        plt.plotsize(width, height)

        return Text.from_ansi(plt.build())
