import pandas as pd

from spectr.utils import simulate_portfolio_end_value


def test_end_value_single_buy_open_position():
    # Starting cash 10,000; buy at 100, final close 120 → value 12,000
    starting_cash = 10000.0
    trades = [
        {"type": "buy", "time": pd.Timestamp("2024-01-01 10:00"), "price": 100.0, "quantity": 100.0},
    ]
    df = pd.DataFrame(
        {
            "open": [100, 110, 115, 118, 120],
            "high": [110, 112, 116, 119, 122],
            "low": [95, 108, 112, 117, 119],
            "close": [105, 111, 115, 118, 120],
            "volume": [1, 1, 1, 1, 1],
        },
        index=pd.date_range("2024-01-01 10:00", periods=5, freq="T"),
    )
    end_value = simulate_portfolio_end_value(trades, df, starting_cash)
    assert end_value == 12000.0


def test_end_value_round_trip_profit():
    # Starting cash 10,000; buy at 100, sell at 120 → end value 12,000
    starting_cash = 10000.0
    trades = [
        {"type": "buy", "time": pd.Timestamp("2024-01-01 10:00"), "price": 100.0, "quantity": 100.0},
        {"type": "sell", "time": pd.Timestamp("2024-01-01 11:00"), "price": 120.0, "quantity": 100.0},
    ]
    df = pd.DataFrame(
        {
            "open": [100, 110, 115, 118, 120],
            "high": [110, 112, 116, 119, 122],
            "low": [95, 108, 112, 117, 119],
            "close": [105, 111, 115, 118, 120],
            "volume": [1, 1, 1, 1, 1],
        },
        index=pd.date_range("2024-01-01 10:00", periods=5, freq="T"),
    )
    end_value = simulate_portfolio_end_value(trades, df, starting_cash)
    assert end_value == 12000.0

