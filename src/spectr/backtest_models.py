from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import pandas as pd


@dataclass(frozen=True)
class BacktestInput:
    df: pd.DataFrame
    symbol: str
    config: object
    strategy_class: type
    starting_cash: float
    start_date: str
    end_date: str


@dataclass(frozen=True)
class BacktestReport:
    symbol: str
    start_date: str
    end_date: str
    starting_cash: float
    final_value: float
    end_value: float
    equity_curve: Sequence[float]
    timestamps: Sequence[object]
    price_data: pd.DataFrame
    buy_signals: list[dict]
    sell_signals: list[dict]
    trades: list[dict]
