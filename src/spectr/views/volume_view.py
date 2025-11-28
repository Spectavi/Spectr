# volume_view.py
import plotext as plt
import numpy as np
from rich.text import Text
from textual.widgets import Static
import logging
from ..plot_lock import PLOT_LOCK

log = logging.getLogger(__name__)


class VolumeView(Static):
    """Terminal chart that shows traded volume for the active symbol."""

    def __init__(self, *, id: str = "volume"):
        super().__init__(id=id)
        self.df = None  # DataFrame injected by SpectrApp
        self.args = None  # same args object GraphView uses

    def load_df(self, df, args):
        """Store the DataFrame and redraw on next refresh."""
        self.df = df
        self.args = args
        self.refresh()

    def render(self):
        if self.df is None or self.df.empty:
            return "No volume data yet…"

        return self.build_graph()

    def build_graph(self):
        with PLOT_LOCK:
            plt.clear_data()
            plt.clear_figure()

        df = self.df.copy()

        # Decide how many points fit in the widget’s width
        max_points = max(int(self.size.width * self.args.scale), 10)
        if len(df) > max_points:
            df = df.tail(max_points)

        # X-axis: use the same timestamp formatting convention as GraphView
        times = df.index.strftime("%Y-%m-%d %H:%M")

        # Plot volume as vertical bars on the RIGHT y-axis
        # Choose a colour per bar: green if close ≥ open, else red
        prev_close = df["close"].shift(1).fillna(df["close"])
        colors = np.where(df["close"] >= prev_close, "green", "red")

        # Plot volume bars on the RIGHT y-axis with per-bar colors
        with PLOT_LOCK:
            plt.bar(
                times,
                df["volume"].to_numpy(dtype=float),
                label="Volume",
                color=colors.tolist(),
                yside="right",
                marker="hd",
                width=0.4,
            )

            # Cosmetics – keep the same theme as other views
            # plt.title(f"Volume — {self.args.symbols[self.args.active_index]")
            plt.xticks([], [])  # No xticks for indicators, cleans up UI.
            plt.canvas_color("default")
            plt.axes_color("default")
            plt.ticks_color("default")

            max_vol = float(df["volume"].astype(float).max())
            top = int(np.ceil(max_vol * 1.1)) if max_vol > 0 else 1
            plt.ylim(0, top, yside="right")

            tick_step = max(1, top // 4)
            ticks = np.arange(0, top + tick_step, tick_step)
            plt.yticks(ticks.tolist(), [str(t) for t in ticks], yside="right")

            width = max(self.size.width, 20)
            height = max(self.size.height, 10)
            plt.plotsize(width, height)

            # plt.xticks(auto=True, rotation=90)
            # plt.frame(True)

            return Text.from_ansi(plt.build())
