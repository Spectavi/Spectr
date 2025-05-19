import logging

import pandas as pd
import plotext as plt
from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

log = logging.getLogger(__name__)

class MACDView(Static):
    is_backtest: reactive[bool] = reactive(False)

    def __init__(self, df=None, args=None, **kwargs):
        super().__init__(**kwargs)
        self.df = df
        self.args = args

    def on_mount(self):
        self.set_interval(0.5, self.refresh)  # Force refresh loop, optional

    def on_resize(self, event):
        self.refresh()  # Force redraw when size changes

    def update_df(self, df: pd.DataFrame):
        """Set a new DataFrame and trigger redraw"""
        if 'macd' in df.columns and 'macd_signal' in df.columns:
            self.df = df.copy()

    def watch_df(self, old, new):
        self.refresh()

    def watch_is_backtest(self, old, new):
        self.refresh()

    def render(self):
        log.debug("Rendering macd")
        return self.build_graph()

    def build_graph(self) -> str:
        if self.df is None or self.df.empty or "macd" not in self.df.columns:
            return "Waiting for MACD data..."
        self.df = self.df.dropna(subset=["macd", "macd_signal"])

        max_points = max(int(self.size.width * self.args.scale), 10)
        if not self.is_backtest and len(self.df) > max_points:
            # Live view: only show the tail that fits the terminal width
            df = self.df.tail(max_points)
        else:
            # Back-test or small frame: show everything
            df = self.df.copy()

        if len(df) < 2:
            return "Not enough data."

        # Force datetime index safely
        if not isinstance(df.index, pd.DatetimeIndex):
            try:
                df.index = pd.to_datetime(df.index, errors="coerce")
            except Exception as e:
                return f"Invalid index: {e}"

        times = df.index.strftime('%Y-%m-%d %H:%M:%S')

        plt.clf()
        plt.canvas_color("default")
        plt.axes_color("default")
        plt.ticks_color("grey")
        plt.xticks([], [])  # No xticks for indicators, cleans up UI.
        plt.grid(False)
        plt.date_form("Y-m-d H:M:S")

        baseline_x = [times[0], times[-1]]
        plt.plot(baseline_x, [0, 0], marker="-", color="gray", yside="right", label="")
        plt.plot(times, df["macd"], color="white", label="MACD", marker="hd", yside="right")
        plt.plot(times, df["macd_signal"], color="orange", label="Signal", marker="hd", yside="right")

        # Y range adjustment
        macd_range = max(df["macd"]) - min(df["macd_signal"])
        center = df["macd"][-1]
        margin = macd_range * 1.2 if macd_range else 1
        plt.ylim(center - margin, center + margin)

        plt.plotsize(self.size.width, self.size.height)

        return Text.from_ansi(plt.build())
