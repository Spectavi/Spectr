import logging
import asyncio

from textual import events
from textual.widgets import Input, Label, Button, DataTable, Select
from textual.containers import Vertical, Horizontal, Container
from textual.screen import ModalScreen
from .. import utils

log = logging.getLogger(__name__)

NO_RESULT_ROW = ("No results found.", "", "", "", "", "", "")    # table layout


class TickerInputDialog(ModalScreen):
    BINDINGS = [
        ("enter", "submit", "Submit"),
        ("escape", "app.pop_screen", "Cancel"),
    ]


    def __init__(
            self,
            callback,
            top_movers_cb,
            quote_cb=None,
            profile_cb=None,
            scanner_results=None,
            scanner_results_cb=None,
            gainers_results=None,
            gainers_results_cb=None,
            scanner_names=None,
            current_scanner=None,
            set_scanner_cb=None,
    ):
        super().__init__()
        self.callback = callback
        self.top_gainers_cb = top_movers_cb  # one quick client
        self.quote_cb = quote_cb
        self.profile_cb = profile_cb
        self.gainers_list: list[dict] = gainers_results or []
        self.gainers_table_columns = None
        self.scanner_list: list[dict] = scanner_results or []
        self.scanner_table_columns = None
        self.scanner_results_cb = scanner_results_cb
        self._scanner_refresh_job = None
        self.gainers_results_cb = gainers_results_cb
        self._gainers_refresh_job = None
        self.scanner_names: list[str] = scanner_names or []
        self.current_scanner = current_scanner or (self.scanner_names[0] if self.scanner_names else "")
        self.set_scanner_cb = set_scanner_cb

    def compose(self):
        yield Vertical(
            Label("Enter new ticker symbol list (up to 20):"),
            Horizontal(
                Input(
                    placeholder="e.g. AAPL,AMZN,META,MSFT,NVDA,TSLA,GOOG,VTI,GLD",
                    id="ticker-input",
                ),
                Button("Submit", id="submit-button", variant="success"),
                id="ticker_input_row",
            ),
            Horizontal(
                Label("Scanner:", id="scanner-label"),
                Select(
                    id="scanner-select",
                    prompt="",
                    value=self.current_scanner,
                    options=[(name, name) for name in self.scanner_names],
                ),
            ),
            Label("Scanner results:", id="scanner-title"),
            Container(
                DataTable(id="scanner-table"),
                id="scanner-container",
            ),
            Label("Top 50 gainers today:", id="gainers-title"),
            Container(
                DataTable(id="gainers-table"),
                id="gainers-container",
            ),
            id="ticker_input_dlg_body",
        )

    async def on_mount(self, event: events.Mount) -> None:
        input_widget = self.query_one("#ticker-input", Input)
        if hasattr(self.app, "ticker_symbols"):
            input_widget.value = ",".join(self.app.ticker_symbols)
        input_widget.focus()
        table = self.query_one("#gainers-table", DataTable)
        self.gainers_table_columns = table.add_columns(
            "Symbol", "% Δ", "Curr Price", "Open Price", "% Avg Vol", "Avg Vol", "Float"
        )
        table.cursor_type = "row"
        table.show_cursor = True
        table.add_row("Loading...", "", "", "", "", "", "")

        scanner_table = self.query_one("#scanner-table", DataTable)
        self.scanner_table_columns = scanner_table.add_columns(
            "Symbol", "% Δ", "Curr Price", "Open Price", "% Avg Vol", "Avg Vol", "Float"
        )
        scanner_table.cursor_type = "row"
        scanner_table.show_cursor = True
        if self.scanner_names:
            self.query_one("#scanner-select", Select).value = self.current_scanner

        if self.gainers_list:
            asyncio.create_task(self.refresh_top_movers(rows=self.gainers_list))
        else:
            asyncio.create_task(self.refresh_top_movers())

        if self.scanner_list:
            self._populate_scanner_table(self.scanner_list)
        else:
            scanner_table.add_row("Scanning...", "", "", "", "", "", "")

        if self.scanner_results_cb:
            self._scanner_refresh_job = self.set_interval(
                10.0, self._check_scanner_results
            )
        if self.gainers_results_cb:
            self._gainers_refresh_job = self.set_interval(
                10.0, self._check_gainers_results
            )



    async def on_unmount(self, event: events.Unmount) -> None:
        if self._scanner_refresh_job:
            self._scanner_refresh_job.stop()
            self._scanner_refresh_job = None
        if self._gainers_refresh_job:
            self._gainers_refresh_job.stop()
            self._gainers_refresh_job = None

    def on_data_table_row_selected(
            self,
            event: DataTable.RowSelected,
    ) -> None:
        log.debug(f"row selected: {event.row_key}")
        log.debug(f"data table id: {event.data_table.id}")

        columns = (
            self.gainers_table_columns
            if event.data_table.id == "gainers-table"
            else self.scanner_table_columns
        )
        symbol = str(event.data_table.get_cell(event.row_key, columns[0])).strip().upper()  # row_key is the first column
        if not symbol:
            return

        # Ignore placeholder rows used during scanning or when no results were
        # found. These rows don't represent a valid ticker symbol and should
        # not be added to the input field when selected.
        if symbol.upper() in {"SCANNING...", NO_RESULT_ROW[0].upper()}:
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
                asyncio.create_task(self.refresh_top_movers())
            case "scanner-select-button":
                self._select_scanners()

    async def on_select_changed(self, event: Select.Changed):
        if event.select.id == "scanner-select":
            self.current_scanner = event.value
            if callable(self.set_scanner_cb):
                self.set_scanner_cb(event.value)

    def on_input_submitted(self, event: Input.Submitted):
        self._submit()

    def _submit(self):
        input_widget = self.query_one("#ticker-input", Input)
        symbols = input_widget.value.strip().upper()
        if symbols:
            self.dismiss()
            self.callback(symbols)

    def _select_gainers(self):
        if not self.gainers_list:
            return
        top10 = ",".join(row["symbol"] for row in self.gainers_list)
        self.query_one("#ticker-input", Input).value = top10

    def _select_scanners(self):
        if not self.scanner_list:
            return
        top10 = ",".join(row["symbol"] for row in self.scanner_list)
        self.query_one("#ticker-input", Input).value = top10

    async def refresh_top_movers(self, rows=None):
        if rows is None:
            rows = self.top_gainers_cb(limit=50)

        self.gainers_list = rows
        table = self.query_one("#gainers-table", DataTable)
        table.clear()
        for row in self.gainers_list:
            table.add_row(
                row["symbol"],
                row["changesPercentage"],
                f"${row['price']:.2f}",
                f"${row['open_price']:.2f}",
                row.get('volume_pct'),
                utils.human_format(row["avg_volume"]),
                utils.human_format(row["float"]),
                key=row["symbol"],
            )
        table.scroll_home()

    def _populate_scanner_table(self, rows: list[dict]) -> None:
        # -------- update UI (main thread) -------------------------------
        table = self.query_one("#scanner-table", DataTable)
        table.clear()

        if not rows:
            table.add_row(*NO_RESULT_ROW)
        else:
            for row in rows:
                pct = f"{row.get('volume_pct', 0):.0f}%" if row.get('avg_volume') else ""
                table.add_row(
                    row["symbol"],
                    str(row.get("changesPercentage", ""))[:7],
                    f"${row['price']:.2f}",
                    f"${row['open_price']:.2f}",
                    pct,
                    utils.human_format(row.get("avg_volume", 0)),
                    utils.human_format(row.get("float", 0)),
                )

        table.scroll_home()

    async def _check_scanner_results(self):
        if not self.scanner_results_cb:
            return
        results = self.scanner_results_cb()
        if results and results != self.scanner_list:
            self.scanner_list = results
            self._populate_scanner_table(results)

    async def _check_gainers_results(self):
        if not self.gainers_results_cb:
            return
        results = self.gainers_results_cb()
        if results and results != self.gainers_list:
            self.gainers_list = results
            await self.refresh_top_movers(rows=results)
