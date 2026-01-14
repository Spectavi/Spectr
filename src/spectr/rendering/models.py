from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence


@dataclass(frozen=True)
class ChartText:
    text: str
    x: object
    y: float
    color: str | None = None
    yside: Literal["left", "right"] = "right"
    alignment: str | None = None
    style: str | None = None


@dataclass(frozen=True)
class ChartTicks:
    positions: Sequence[object]
    labels: Sequence[str]
    yside: Literal["left", "right"] = "right"


@dataclass(frozen=True)
class ChartCandles:
    x: Sequence[object]
    ohlc: object
    yside: Literal["left", "right"] = "right"


@dataclass(frozen=True)
class ChartSeries:
    x: Sequence[object]
    y: Sequence[float]
    label: str | None = None
    color: str | None = None
    marker: str | None = None
    yside: Literal["left", "right"] = "right"
    kind: Literal["line", "scatter", "bar"] = "line"
    width: float | None = None
    colors: Sequence[str] | None = None


@dataclass(frozen=True)
class DateForm:
    input_form: str
    output_form: str


@dataclass(frozen=True)
class ChartViewModel:
    series: Sequence[ChartSeries]
    candles: ChartCandles | None = None
    title: str | None = None
    texts: Sequence[ChartText] = ()
    x_ticks: ChartTicks | None = None
    y_ticks: ChartTicks | None = None
    y_limits: tuple[float, float] | None = None
    date_form: DateForm | None = None
    canvas_color: str = "default"
    axes_color: str = "default"
    ticks_color: str = "default"
    grid: bool = False
    hide_xticks: bool = False
