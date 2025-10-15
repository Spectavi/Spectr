from types import SimpleNamespace
from enum import Enum
import pandas as pd
from spectr.strategies.trading_strategy import get_order_sides
import backtrader as bt


class DummySide(Enum):
    BUY = "buy"
    SELL = "sell"


def test_get_order_sides_enum_objects():
    orders = [SimpleNamespace(side=DummySide.BUY), {"side": DummySide.SELL}]
    sides = get_order_sides(orders)
    assert sides == {"buy", "sell"}


def test_get_order_sides_enum_dataframe():
    df = pd.DataFrame({"side": [DummySide.BUY, DummySide.SELL]})
    sides = get_order_sides(df)
    assert sides == {"buy", "sell"}


def test_get_order_sides_backtrader_like_pending_and_completed():
    class DummyBtBuy:
        def __init__(self, status):
            self.status = status

        def isbuy(self):
            return True

        def issell(self):
            return False

    class DummyBtSell:
        def __init__(self, status):
            self.status = status

        def isbuy(self):
            return False

        def issell(self):
            return True

    # Pending buy should be detected
    pending_buy = DummyBtBuy(bt.Order.Submitted)
    # Completed sell should be ignored (terminal)
    completed_sell = DummyBtSell(bt.Order.Completed)
    sides = get_order_sides([pending_buy, completed_sell])
    assert sides == {"buy"}
