from __future__ import annotations

import pandas as pd

from .. import utils
from ..backtest import run_backtest
from ..backtest_models import BacktestInput, BacktestReport


class BacktestService:
    def run(self, inputs: BacktestInput) -> BacktestReport:
        result = run_backtest(
            inputs.df,
            inputs.symbol,
            inputs.config,
            inputs.strategy_class,
            inputs.starting_cash,
        )

        equity_curve = result.get("equity_curve", [])
        timestamps = result.get("timestamps", [])

        if isinstance(equity_curve, pd.Series):
            timestamps = list(equity_curve.index)
            equity_curve = equity_curve.tolist()
        elif isinstance(equity_curve, pd.DataFrame):
            timestamps = list(equity_curve.index)
            equity_curve = [float(v) for v in equity_curve.iloc[:, -1].tolist()]

        buy_signals = list(result.get("buy_signals", []))
        sell_signals = list(result.get("sell_signals", []))

        equity_lookup = {}
        if timestamps and equity_curve:
            equity_lookup = dict(zip(timestamps, equity_curve))

        trades: list[dict] = []
        for rec in buy_signals + sell_signals:
            rec_time = rec.get("time")
            trades.append(
                {
                    **rec,
                    "value": equity_lookup.get(rec_time),
                }
            )
        trades.sort(key=lambda r: r.get("time"))

        price_data = result.get("price_data")
        if isinstance(price_data, pd.DataFrame):
            price_data = price_data.copy(deep=True)
        else:
            price_data = pd.DataFrame()

        try:
            end_value = utils.simulate_portfolio_end_value(
                trades, price_data, inputs.starting_cash
            )
        except Exception:
            end_value = float(result.get("final_value", 0.0))

        return BacktestReport(
            symbol=inputs.symbol,
            start_date=inputs.start_date,
            end_date=inputs.end_date,
            starting_cash=inputs.starting_cash,
            final_value=float(result.get("final_value", 0.0)),
            end_value=end_value,
            equity_curve=equity_curve,
            timestamps=timestamps,
            price_data=price_data,
            buy_signals=buy_signals,
            sell_signals=sell_signals,
            trades=trades,
        )
