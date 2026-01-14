import logging

import pandas as pd
from textual.reactive import reactive
from textual.widgets import Static

from ..rendering import PlotRenderer, build_macd_model

log = logging.getLogger(__name__)
_RENDERER = PlotRenderer()


class MACDView(Static):
    is_backtest: reactive[bool] = reactive(False)

    def __init__(self, df=None, args=None, **kwargs):
        super().__init__(**kwargs)
        self.df = df
        self.args = args
        self._refresh_timer = None

    def on_mount(self):
        # Keep a handle so we can reliably stop it on unmount
        self._refresh_timer = self.set_interval(0.5, self.refresh)

    def on_resize(self, event):
        self.refresh()  # Force redraw when size changes

    def update_df(self, df: pd.DataFrame):
        """Set a new DataFrame and trigger redraw"""
        if "macd" in df.columns and "macd_signal" in df.columns:
            self.df = df.copy()

    def watch_df(self, old, new):
        self.refresh()

    def watch_is_backtest(self, old, new):
        self.refresh()

    async def on_unmount(self) -> None:
        # Ensure the periodic timer is stopped when removed from the DOM
        if self._refresh_timer is not None:
            try:
                self._refresh_timer.stop()
            except Exception:
                pass
            self._refresh_timer = None

    def render(self):
        return self.build_graph()

    def load_df(self, df, args):
        """Store the DataFrame and redraw on next refresh."""
        self.df = df
        self.args = args
        self.refresh()

    def build_graph(self) -> str:
        if self.df is None or self.df.empty or "macd" not in self.df.columns:
            return "Waiting for MACD data..."

        model = build_macd_model(
            self.df,
            args=self.args,
            is_backtest=self.is_backtest,
            width=max(int(self.size.width), 20),
        )
        if model is None:
            return "Not enough data."

        width = max(int(self.size.width) - 5, 10)
        height = max(int(self.size.height), 8)
        return _RENDERER.render(model, width=width, height=height)
