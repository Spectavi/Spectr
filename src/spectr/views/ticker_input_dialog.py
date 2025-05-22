import logging

from textual import events
from textual.widgets import Input, Label, Button, DataTable
from textual.containers import Vertical, Horizontal, Container
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
        self.top_gainers_cb = top_movers_cb  # one quick client
        self.gainers: list[dict] = []
        self.gainers_table_columns = None

    def compose(self):
        yield Vertical(
            Label("Enter new ticker symbol list (up to 20):"),
            Input(
                placeholder="e.g. AAPL,AMZN,META,MSFT,NVDA,TSLA,GOOG,VTI,GLD",
                id="ticker-input",
            ),
            Button("Submit", id="submit-button", variant="success"),
            Horizontal(
                Label("Top 20 gainers today:", id="gainers-title"),
                Label("Strategy scanner results:", id="scanner-results"),
                id="title-row"),
            Horizontal(
                Button("Select", id="gainers-select-button", variant="primary"),
                    Button("Refresh", id="gainers-refresh-button"),
                    Button("Select", id="scanner-select-button", variant="primary"),
                    Button("Refresh", id="scanner-refresh-button"),
                id="table-buttons-row",
            ),
            Horizontal(
            Container(
                DataTable(id="gainers-table"),
                    id="gainers-container",
                ),
                Container(
                DataTable(id="scanner-table"),
                    id="scanner-container",
                ),
                id="data-table-row",
            ),
            id="ticker_input_dlg_body",
        )

    async def on_mount(self, event: events.Mount) -> None:
        table = self.query_one("#gainers-table", DataTable)
        self.gainers_table_columns = table.add_columns("Symbol", "% Δ", "Curr Price", "Open Price")
        table.cursor_type = "row"  # ← NEW: enables row selection by mouse
        table.show_cursor = True
        table.focus()
        table = self.query_one("#scanner-table", DataTable)
        table.add_columns("Symbol", "% Δ", "Curr Price", "Open Price")
        table.cursor_type = "row"  # ← NEW: enables row selection by mouse
        table.show_cursor = True
        self.refresh_top_movers()

    def on_data_table_row_selected(
            self,
            event: DataTable.RowSelected,
    ) -> None:
        log.debug(f"row selected: {event.row_key}")

        symbol = str(event.data_table.get_cell(event.row_key, self.gainers_table_columns[0])).strip().upper()  # row_key is the first column
        if not symbol:
            return

        input_widget = self.query_one("#ticker-input", Input)
        current = [s for s in input_widget.value.upper().split(",") if s]

        if symbol not in current:
            current.append(symbol)
            input_widget.value = ",".join(current)

    def on_button_pressed(self, event: Button.Pressed):
        match event.button.id:
            case "submit-button":
                self._submit()
            case "gainers-select-button":
                self._select_gainers()
            case "gainers-refresh-button":
                self.refresh_top_movers()

    def on_input_submitted(self, event: Input.Submitted):
        self._submit()

    def _submit(self):
        input_widget = self.query_one("#ticker-input", Input)
        symbols = input_widget.value.strip().upper()
        if symbols:
            self.dismiss()
            self.callback(symbols)

    def _select_gainers(self):
        if not self.gainers:
            return
        top10 = ",".join(row["symbol"] for row in self.gainers)
        self.query_one("#ticker-input", Input).value = top10

    def refresh_top_movers(self):
        self.gainers = self.top_gainers_cb(limit=20)
        log.debug(f"Top 20 gainers today: {self.gainers}")
        table = self.query_one("#gainers-table", DataTable)
        table.clear()
        for row in self.gainers:
            open_price = row["price"] - row["change"]
            table.add_row(
                row["symbol"],
                row["changesPercentage"],
                f"${row['price']:.2f}",
                f"${open_price:.2f}",
                key=row["symbol"],
            )
        table.scroll_home()

    # TODO: finish implementing this properly. Just shows gainers for now.
    def refresh_scanner(self):
        self.gainers = self.top_gainers_cb(limit=20)
        log.debug(f"Strategy scanner results: {self.gainers}")
        table = self.query_one("#scanner-table", DataTable)
        table.clear()
        for row in self.gainers:
            open_price = row["price"] - row["change"]
            table.add_row(
                row["symbol"],
                row["changesPercentage"],
                f"${row['price']:.2f}",
                f"${open_price:.2f}",
            )
        table.scroll_home()