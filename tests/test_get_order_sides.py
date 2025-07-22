from types import SimpleNamespace
from enum import Enum
import pandas as pd
from spectr.strategies.trading_strategy import get_order_sides


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
