import pathlib

from spectr.strategies import get_strategy_code


def test_get_strategy_code_reads_file():
    code = get_strategy_code("CustomStrategy")
    path = pathlib.Path("src/spectr/strategies/custom_strategy.py")
    assert code == path.read_text(encoding="utf-8")
