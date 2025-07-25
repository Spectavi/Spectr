import logging

import backtrader as bt
import pandas as pd

from . import utils
from .strategies import metrics

log = logging.getLogger(__name__)


class CommInfoFractional(bt.CommissionInfo):
    """Allow fractional share sizing."""

    def getsize(self, price, cash):
        return self.p.leverage * (cash / price)


def run_backtest(
    df: pd.DataFrame | None,
    symbol: str,
    config,
    strategy_class,
    starting_cash: float = 1000.0,
    *,
    data_api=None,
    from_date: str | None = None,
    to_date: str | None = None,
):
    """Execute a backtest using ``backtrader``.

    Parameters
    ----------
    df : pd.DataFrame | None
        Historical price data. If ``None``, ``data_api`` along with
        ``from_date`` and ``to_date`` must be provided and the data will be
        fetched using :func:`spectr.utils.get_historical_data`.
    symbol : str
        Ticker symbol for the strategy.
    config : object
        Configuration object with ``bb_period``, ``bb_dev`` and ``macd_thresh`` attributes.
    strategy_class : type
        Strategy class compatible with ``backtrader``.
    starting_cash : float, optional
        Initial account value, by default ``1000.0``.
    data_api : DataInterface, optional
        Data provider used to fetch historical bars when ``df`` is ``None``.
    from_date, to_date : str, optional
        Inclusive date range for the backtest when data must be fetched.
    """

    if df is None:
        if not all([data_api, from_date, to_date]):
            raise ValueError(
                "df is None but data_api/from_date/to_date were not provided"
            )
        df, _ = utils.get_historical_data(
            data_api,
            config.bb_period,
            config.bb_dev,
            config.macd_thresh,
            symbol,
            from_date=from_date,
            to_date=to_date,
        )

    # Ensure indicators are present
    df = metrics.analyze_indicators(
        df,
        strategy_class.get_indicators(),
    )

    cerebro = bt.Cerebro()
    # Dynamically map ``config`` attributes onto the strategy parameters.  This
    # allows running backtests with different strategy classes that may not
    # accept the same keywords (e.g. ``MACDOscillator`` doesn't use Bollinger
    # Band settings).  Only parameters defined on the strategy are forwarded.
    params = {"symbol": symbol}

    keys = []
    params_obj = getattr(strategy_class, "params", None)
    if params_obj is not None:
        if hasattr(params_obj, "_getkeys"):
            try:
                keys = list(params_obj._getkeys())
            except Exception:  # pragma: no cover - very unlikely
                keys = []
        elif isinstance(params_obj, dict):  # pragma: no cover - alternative form
            keys = list(params_obj.keys())

    for key in keys:
        if key == "symbol":
            continue
        if hasattr(config, key):
            params[key] = getattr(config, key)

    if "is_backtest" in keys:
        params["is_backtest"] = True

    cerebro.addstrategy(strategy_class, **params)

    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)
    cerebro.broker.setcash(starting_cash)
    cerebro.broker.addcommissioninfo(CommInfoFractional())
    cerebro.broker.setcommission(commission=0.0)
    cerebro.addsizer(bt.sizers.AllInSizer, percents=100)

    log.debug("Starting Portfolio Value: %.2f", cerebro.broker.getvalue())
    results = cerebro.run()
    log.debug("Final Portfolio Value: %.2f", cerebro.broker.getvalue())

    strat = results[0]

    portfolio_values = [strat.broker.get_value()]
    timestamps = df.index.tolist()
    equity_curve = list(zip(timestamps, portfolio_values))

    return {
        "final_value": cerebro.broker.getvalue(),
        "equity_curve": equity_curve,
        "price_data": df[["close"]].copy(),
        "timestamps": timestamps,
        "buy_signals": strat.buy_signals,
        "sell_signals": strat.sell_signals,
    }
