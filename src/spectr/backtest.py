import logging

import backtrader as bt
import pandas as pd

log = logging.getLogger(__name__)


class CommInfoFractional(bt.CommissionInfo):
    """Allow fractional share sizing."""

    def getsize(self, price, cash):
        return self.p.leverage * (cash / price)


def run_backtest(
    df: pd.DataFrame, symbol: str, config, strategy_class, starting_cash: float = 1000.0
):
    """Execute a backtest using ``backtrader``.

    Parameters
    ----------
    df : pd.DataFrame
        Historical price data with indicators already computed.
    symbol : str
        Ticker symbol for the strategy.
    config : object
        Configuration object with ``bb_period``, ``bb_dev`` and ``macd_thresh`` attributes.
    strategy_class : type
        Strategy class compatible with ``backtrader``.
    starting_cash : float, optional
        Initial account value, by default ``1000.0``.
    """

    cerebro = bt.Cerebro()
    # Dynamically map ``config`` attributes onto the strategy parameters.  This
    # allows running backtests with different strategy classes that may not
    # accept the same keywords (e.g. ``MACDOscillator`` doesn't use Bollinger
    # Band settings).  Only parameters defined on the strategy are forwarded.
    params = {"symbol": symbol}

    if hasattr(strategy_class, "params"):
        try:
            keys = list(strategy_class.params._getkeys())
        except Exception:  # pragma: no cover - very unlikely
            keys = []
    else:  # pragma: no cover - fallback for unusual classes
        keys = []

    for key in keys:
        if key == "symbol":
            continue
        if hasattr(config, key):
            params[key] = getattr(config, key)

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
