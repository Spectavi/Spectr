import logging
from datetime import datetime, timedelta

import plotext as plt
from rich.text import Text
from textual.widgets import Static

log = logging.getLogger(__name__)


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
            return "No equity data…"

        # Plotext's date handling can raise errors on some platforms when
        # timestamps are converted to dates (e.g. Windows pre‑1970 support).
        # To avoid this we plot using numeric X values and manually label
        # a subset of ticks with formatted times.

        raw_times = [d[0] for d in self.data]
        cash_vals = [d[1] for d in self.data]
        total_vals = [d[2] for d in self.data]

        x_vals = list(range(len(raw_times)))

        plt.clear_data()
        plt.clear_figure()
        plt.canvas_color("default")
        plt.axes_color("default")
        plt.ticks_color("default")

        plt.plot(x_vals, cash_vals, color="blue", marker="hd", label="Cash", yside="right")
        plt.plot(x_vals, total_vals, color="red", marker="hd", label="Total", yside="right")

        # Label a handful of ticks to avoid clutter
        step = max(1, len(x_vals) // 10)
        tick_positions = x_vals[::step]
        tick_labels = [raw_times[i].strftime("%H:%M:%S") for i in tick_positions]
        plt.xticks(tick_positions, tick_labels)

        ymin = min(min(cash_vals), min(total_vals)) * 0.95
        ymax = max(max(cash_vals), max(total_vals)) * 1.05
        plt.ylim(ymin, ymax, yside="right")

        width = max(self.size.width - 3, 20)
        height = max(self.size.height, 10)
        plt.plotsize(width, height)

        return Text.from_ansi(plt.build())
