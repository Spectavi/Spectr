import logging

from textual.widgets import Static

from ..rendering import PlotRenderer, build_volume_model

log = logging.getLogger(__name__)
_RENDERER = PlotRenderer()


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
            return "No volume data yet..."

        return self.build_graph()

    def build_graph(self):
        model = build_volume_model(
            self.df,
            args=self.args,
            width=max(int(self.size.width), 20),
        )
        if model is None:
            return "No volume data yet..."

        width = max(int(self.size.width), 20)
        height = max(int(self.size.height), 10)
        return _RENDERER.render(model, width=width, height=height)
