import pytest
from spectr.fetch.alpaca import _format_symbol


@pytest.mark.parametrize(
    "given,expected",
    [
        ("BTCUSD", "BTC/USD"),
        ("ETHUSDT", "ETH/USDT"),
        ("DOGEUSDC", "DOGE/USDC"),
        ("AAPL", "AAPL"),
        ("BTC/USD", "BTC/USD"),
    ],
)
def test_format_symbol(given, expected):
    assert _format_symbol(given) == expected
