import logging
from textual.screen import ModalScreen
from textual.widgets import Static, DataTable
from textual.containers import Vertical

from .graph_view import GraphView


log = logging.getLogger(__name__)


class BacktestResultScreen(ModalScreen):
    """Screen displaying the back‑test graph and summary metrics."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
    ]

    def __init__(
        self,
        graph: GraphView,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
        start_value: float,
        end_value: float,
        num_buys: int,
        num_sells: int,
        trades: list[dict],
    ) -> None:
        super().__init__()
        self._graph = graph
        self._graph.is_backtest = True
        self.report = Static(id="backtest-report")
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.start_value = start_value
        self.end_value = end_value
        self.num_buys = num_buys
        self.num_sells = num_sells
        self.trades = trades

    def compose(self):
        log.debug("BacktestResultScreen.compose")
        self.report.update(self._make_report())
        table = DataTable(id="backtest-trades", zebra_stripes=True)
        table.styles.height = 10
        table.add_columns("Signal", "Price", "Quantity", "Value", "Reason")
        for trade in self.trades:
            table.add_row(
                trade["type"].upper(),
                f"${trade['price']:.2f}",
                f"{trade.get('quantity', 0):.4f}",
                f"${trade['value']:.2f}" if trade.get("value") is not None else "—",
                trade.get("reason", ""),
            )
        yield Vertical(
            self._graph,
            self.report,
            table,
            id="backtest-result-container",
        )

    async def on_mount(self) -> None:
        log.debug("BacktestResultScreen mounted")

    async def on_unmount(self) -> None:
        log.debug("BacktestResultScreen unmounted")

    def _make_report(self) -> str:
        return (
            f"Symbol: {self.symbol}\n"
            f"From: {self.start_date}\n"
            f"To: {self.end_date}\n"
            f"Start Value: ${self.start_value:,.2f}\n"
            f"End Value: ${self.end_value:,.2f}\n"
            f"Buys: {self.num_buys}\n"
            f"Sells: {self.num_sells}"
        )
