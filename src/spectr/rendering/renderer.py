from __future__ import annotations

from rich.text import Text
import plotext as plt

from ..plot_lock import PLOT_LOCK
from .models import ChartViewModel


class PlotRenderer:
    """Render plotext charts from view models."""

    def render(self, model: ChartViewModel, *, width: int, height: int) -> Text:
        with PLOT_LOCK:
            plt.clf()
            plt.canvas_color(model.canvas_color)
            plt.axes_color(model.axes_color)
            plt.ticks_color(model.ticks_color)
            plt.grid(model.grid)
            if model.date_form is not None:
                plt.date_form(
                    input_form=model.date_form.input_form,
                    output_form=model.date_form.output_form,
                )

            if model.hide_xticks:
                plt.xticks([], [])
            elif model.x_ticks is not None:
                plt.xticks(model.x_ticks.positions, model.x_ticks.labels)

            if model.y_ticks is not None:
                plt.yticks(
                    model.y_ticks.positions,
                    model.y_ticks.labels,
                    yside=model.y_ticks.yside,
                )

            if model.candles is not None:
                plt.candlestick(model.candles.x, model.candles.ohlc, yside=model.candles.yside)

            for series in model.series:
                if series.kind == "bar":
                    plt.bar(
                        series.x,
                        series.y,
                        label=series.label,
                        color=list(series.colors) if series.colors is not None else series.color,
                        yside=series.yside,
                        marker=series.marker,
                        width=series.width,
                    )
                elif series.kind == "scatter":
                    plt.scatter(
                        series.x,
                        series.y,
                        label=series.label,
                        color=series.color,
                        yside=series.yside,
                        marker=series.marker,
                    )
                else:
                    plt.plot(
                        series.x,
                        series.y,
                        label=series.label,
                        color=series.color,
                        yside=series.yside,
                        marker=series.marker,
                    )

            for text in model.texts:
                plt.text(
                    text.text,
                    text.x,
                    text.y,
                    color=text.color,
                    yside=text.yside,
                    alignment=text.alignment,
                    style=text.style,
                )

            if model.y_limits is not None:
                plt.ylim(model.y_limits[0], model.y_limits[1])

            if model.title:
                plt.title(model.title)

            plt.plotsize(max(width, 10), max(height, 8))

            return Text.from_ansi(plt.build())
