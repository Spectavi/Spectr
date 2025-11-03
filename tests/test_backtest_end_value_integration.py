import pandas as pd

from types import SimpleNamespace

from spectr.backtest import run_backtest
from spectr.utils import simulate_portfolio_end_value
from spectr.strategies.trading_strategy import TradingStrategy


class BuyAndHoldOnce(TradingStrategy):
    """Buys once on the first bar and holds to the end (no sells)."""

    params = (("symbol", ""),)

    def __init__(self):
        # Ensure signal containers exist for run_backtest outputs
        self.buy_signals = []
        self.sell_signals = []

    @classmethod
    def get_indicators(cls):
        return []

    def get_lookback(self) -> int:
        return 1

    @staticmethod
    def detect_signals(df: pd.DataFrame, symbol: str, position=None, orders=None, **kwargs):
        # If not in a position, signal a single buy; otherwise, do nothing
        qty = getattr(position, "qty", getattr(position, "size", 0)) if position is not None else 0
        if qty == 0:
            price = float(df.iloc[-1]["close"]) if not df.empty else 0.0
            return {"signal": "buy", "price": price, "symbol": symbol, "reason": "entry"}
        return None

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
                {
                    "type": "buy",
                    "time": self.datas[0].datetime.datetime(0),
                    "price": price,
                    "quantity": size,
                    "reason": signal.get("reason"),
                }
            )


def test_backtest_end_value_matches_broker_buy_and_hold():
    # Price rises from 100 → 120; starting cash 10,000; buy ~100 shares; end value ≈ 12,000
    df = pd.DataFrame(
        {
            "open": [100, 110, 115, 118, 120],
            "high": [110, 112, 116, 119, 122],
            "low": [95, 108, 112, 117, 119],
            "close": [100, 111, 115, 118, 120],
            "volume": [1, 1, 1, 1, 1],
        },
        index=pd.date_range("2024-01-01 10:00", periods=5, freq="min"),
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

    starting_cash = 10_000.0
    res = run_backtest(df, "TEST", cfg, BuyAndHoldOnce, starting_cash)

    # Merge trades for simulation
    trades = list(res.get("buy_signals", [])) + list(res.get("sell_signals", []))
    price_df = res["price_data"]

    sim_end = simulate_portfolio_end_value(trades, price_df, starting_cash)

    # Compare to broker's final value
    assert abs(sim_end - float(res["final_value"])) < 1e-6
