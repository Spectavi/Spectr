import logging
from datetime import datetime

import plotext as plt
from rich.text import Text
from textual.widgets import Static

log = logging.getLogger(__name__)


class EquityCurveView(Static):
    """Simple line chart for portfolio cash and total value."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data: list[tuple[datetime, float, float]] = []

    def add_point(self, cash: float, total: float) -> None:
        """Append a new data point and trigger a refresh."""
        self.data.append((datetime.now(), cash, total))
        if len(self.data) > 1000:
            self.data = self.data[-1000:]
        self.refresh()

    def render(self) -> str:
        if not self.data:
            return "No equity data…"

        times = [d[0].strftime("%Y-%m-%d %H:%M:%S") for d in self.data]
        cash_vals = [d[1] for d in self.data]
        total_vals = [d[2] for d in self.data]

        plt.clear_data()
        plt.clear_figure()
        plt.canvas_color("default")
        plt.axes_color("default")
        plt.ticks_color("default")

        plt.date_form(input_form="Y-m-d H:M:S", output_form="H:M:S")

        plt.plot(times, cash_vals, color="blue", marker="hd", label="Cash", yside="right")
        plt.plot(times, total_vals, color="red", marker="hd", label="Total", yside="right")

        ymin = min(min(cash_vals), min(total_vals)) * 0.95
        ymax = max(max(cash_vals), max(total_vals)) * 1.05
        plt.ylim(ymin, ymax, yside="right")

        width = max(self.size.width - 3, 20)
        height = max(self.size.height, 10)
        plt.plotsize(width, height)
        plt.title("Equity Curve")

        return Text.from_ansi(plt.build())
