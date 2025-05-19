import logging

from textual import events
from textual.widgets import Input, Label, Button, DataTable
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen

log = logging.getLogger(__name__)

class TickerInputDialog(ModalScreen):
    BINDINGS = [
        ("enter", "submit", "Submit"),
        ("escape", "app.pop_screen", "Cancel"),
    ]

    def __init__(self, callback, top_movers_cb):
        super().__init__()
        self.callback = callback
        self.top_movers_cb = top_movers_cb  # one quick client
        self.movers: list[dict] = []

    def compose(self):
        yield Vertical(
            Label("Enter new ticker symbol list (up to 10):"),
            Input(
                placeholder="e.g. AAPL,AMZN,META,MSFT,NVDA,TSLA,GOOG,VTI,GLD",
                id="ticker-input",
            ),
            Button("Submit", id="submit-button", variant="success"),
            Label("Top 10 gainers today:", id="movers-title"),
            Horizontal(Button("Select", id="select-button", variant="primary"),Button("Refresh", id="refresh-button")),
            DataTable(id="movers-table"),
        )

    async def on_mount(self, event: events.Mount) -> None:
        table = self.query_one("#movers-table", DataTable)
        table.add_columns("Symbol", "% Δ", "Price")
        self.refresh_top_movers()

    def on_button_pressed(self, event: Button.Pressed):
        match event.button.id:
            case "submit-button":
                self._submit()
            case "select-button":
                self._select_movers()
            case "refresh-button":
                self.refresh_top_movers()

    def on_input_submitted(self, event: Input.Submitted):
        self._submit()

    def _submit(self):
        input_widget = self.query_one("#ticker-input", Input)
        symbols = input_widget.value.strip().upper()
        if symbols:
            self.dismiss()
            self.callback(symbols)

    def _select_movers(self):
        if not self.movers:
            return
        top10 = ",".join(row["symbol"] for row in self.movers)
        self.query_one("#ticker-input", Input).value = top10

    def refresh_top_movers(self):
        self.movers = self.top_movers_cb(limit=10)
        log.debug(f"Top 10 gainers today: {self.movers}")
        table = self.query_one("#movers-table", DataTable)
        table.clear()
        for row in self.movers:
            table.add_row(
                row["symbol"],
                row["changesPercentage"],
                f"${row['price']:.2f}",
            )
        table.scroll_home()
