from textual.screen import Screen
from textual.widgets import Static
from textual.containers import Vertical

from .graph_view import GraphView


class BacktestResultScreen(Screen):
    """Screen displaying the back‑test graph and summary metrics."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
    ]

    def __init__(
        self,
        df,
        args,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
        start_value: float,
        end_value: float,
        num_buys: int,
        num_sells: int,
    ) -> None:
        super().__init__()
        self._graph = GraphView(df=df, args=args, id="backtest-graph")
        self._graph.is_backtest = True
        self.report = Static(id="backtest-report")
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.start_value = start_value
        self.end_value = end_value
        self.num_buys = num_buys
        self.num_sells = num_sells

    def compose(self):
        self.report.update(self._make_report())
        yield Vertical(
            self._graph,
            self.report,
            id="backtest-result-container",
        )

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

