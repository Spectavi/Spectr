import logging
from datetime import datetime, timedelta

from textual.widgets import Static

from ..rendering import PlotRenderer, build_equity_model

log = logging.getLogger(__name__)
_RENDERER = PlotRenderer()


class EquityCurveView(Static):
    """Simple line chart for portfolio cash and total value."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data: list[tuple[datetime, float, float]] = []

        # Limit history to the last 4 hours
        self.history_window = timedelta(hours=4)

    def reset(self) -> None:
        """Clear all recorded data points and refresh the view."""
        self.data.clear()
        self.refresh()

    def add_point(self, cash: float, total: float) -> None:
        """Append a new data point and trigger a refresh."""
        now = datetime.now()
        self.data.append((now, cash, total))
        cutoff = now - self.history_window
        self.data = [d for d in self.data if d[0] >= cutoff]
        if len(self.data) > 1000:
            self.data = self.data[-1000:]
        self.refresh()

    def render(self) -> str:
        if not self.data:
            return "No equity data..."

        model = build_equity_model(self.data)
        if model is None:
            return "No equity data..."

        width = max(int(self.size.width) - 3, 20)
        height = max(int(self.size.height), 10)
        return _RENDERER.render(model, width=width, height=height)
