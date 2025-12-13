import pandas as pd
from types import SimpleNamespace

from spectr.backtest import split_backtest_frames, run_backtest
from spectr.utils import simulate_portfolio_end_value
from spectr.strategies.trading_strategy import TradingStrategy


class _SingleRoundTrip(TradingStrategy):
    params = (("symbol", ""),)

    def __init__(self):
        self.buy_signals = []
        self.sell_signals = []

    @classmethod
    def get_indicators(cls):
        return []

    def get_lookback(self) -> int:
        return 1

    @staticmethod
    def detect_signals(df: pd.DataFrame, symbol: str, position=None, orders=None, **kwargs):
        qty = getattr(position, "qty", getattr(position, "size", 0)) if position is not None else 0
        if qty == 0:
            price = float(df.iloc[-1]["close"])
            return {"signal": "buy", "price": price, "symbol": symbol, "reason": "entry"}
        return {"signal": "sell", "price": float(df.iloc[-1]["close"]), "symbol": symbol, "reason": "exit"}

    def handle_signal(self, signal):
        if not signal:
            return
        current_position = self.getposition(self.datas[0])
        qty = getattr(current_position, "qty", getattr(current_position, "size", 0))
        if signal.get("signal") == "buy" and not qty:
            price = self.datas[0].close[0]
            cash = self.broker.getcash()
            size = cash / price if price else 0.0
            self.buy(size=size)
            self.buy_signals.append(
                {"type": "buy", "time": self.datas[0].datetime.datetime(0), "price": price, "quantity": size}
            )
        elif signal.get("signal") == "sell" and qty:
            price = self.datas[0].close[0]
            self.sell(size=qty)
            self.sell_signals.append(
                {"type": "sell", "time": self.datas[0].datetime.datetime(0), "price": price, "quantity": qty}
            )


def test_backtest_calc_uses_full_df_even_if_graph_cropped():
    dates = pd.date_range("2024-01-01", periods=6, freq="D")
    df = pd.DataFrame(
        {
            "open": [100, 101, 102, 103, 104, 105],
            "high": [101, 102, 103, 104, 105, 106],
            "low": [99, 100, 101, 102, 103, 104],
            "close": [100, 102, 104, 106, 108, 110],
            "volume": [1, 1, 1, 1, 1, 1],
        },
        index=dates,
    )

    cfg = SimpleNamespace(
        bb_period=20,
        bb_dev=2.0,
        macd_thresh=0.005,
        stop_loss_pct=0.01,
        take_profit_pct=0.05,
        fast_period=12,
        slow_period=26,
    )

    starting_cash = 1_000.0
    result = run_backtest(df, "TEST", cfg, _SingleRoundTrip, starting_cash)

    calc_df, graph_df = split_backtest_frames(result, graph_tail=2)
    trades = list(result.get("buy_signals", []))  # leave position open to rely on final close

    graph_df.loc[:, "close"] = 1.0  # simulate a heavily cropped/altered graph view

    end_value_full = simulate_portfolio_end_value(trades, calc_df, starting_cash)
    end_value_graph = simulate_portfolio_end_value(trades, graph_df, starting_cash)

    assert len(calc_df) == len(df)
    assert len(graph_df) == 2
    assert end_value_full != end_value_graph  # calc uses full history, not mutated graph view
