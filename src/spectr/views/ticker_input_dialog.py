import json
import logging
import pathlib
import time

from textual import events
from textual.widgets import Input, Label, Button, DataTable
from textual.containers import Vertical, Horizontal, Container
from textual.screen import ModalScreen
import playsound

log = logging.getLogger(__name__)

NO_RESULT_ROW = ("No results found.", "", "", "")    # 4 cols = table layout
SCAN_SOUND_PATH = 'src/spectr/res/buy.mp3'

from concurrent.futures import ThreadPoolExecutor, as_completed

class TickerInputDialog(ModalScreen):
    BINDINGS = [
        ("enter", "submit", "Submit"),
        ("escape", "app.pop_screen", "Cancel"),
    ]

    REFRESH_SECS = 60

    _CACHE_FILE = pathlib.Path.home() / ".spectr_scanner_cache.json"

    def _save_scanner_cache(self, rows: list[dict]) -> None:
        """Write filtered rows + timestamp to JSON."""
        try:
            self._CACHE_FILE.write_text(
                json.dumps({"t": time.time(), "rows": rows}, indent=0)
            )
        except Exception as exc:
            log.debug(f"cache write failed: {exc}")

    def _load_scanner_cache(self) -> list[dict]:
        """Return cached rows or [] if file missing / unreadable / stale."""

        try:
            blob = json.loads(self._CACHE_FILE.read_text())
            # optional: expire after 15 min

            if time.time() - blob.get("t", 0) > 900:
                return []

            return blob.get("rows", [])
        except Exception:
            return []



    def __init__(self, callback, top_movers_cb, quote_cb, has_recent_positive_news_cb):
        super().__init__()
        self.callback = callback
        self.top_gainers_cb = top_movers_cb  # one quick client
        self.gainers_list: list[dict] = []
        self.gainers_table_columns = None
        self.scanner_list: list[dict] = []
        self.scanner_table_columns = None
        self.quote_cb = quote_cb
        self.has_recent_positive_news_cb = has_recent_positive_news_cb
        self._refresh_job = None  # handle for cancel
        self._scan_pool = ThreadPoolExecutor(max_workers=50, thread_name_prefix="scan")

    def compose(self):
        yield Vertical(
            Label("Enter new ticker symbol list (up to 20):"),
            Input(
                placeholder="e.g. AAPL,AMZN,META,MSFT,NVDA,TSLA,GOOG,VTI,GLD",
                id="ticker-input",
            ),
            Button("Submit", id="submit-button", variant="success"),
            Label("Top 20 gainers today:", id="gainers-title"),
            Container(
                DataTable(id="gainers-table"),
                id="gainers-container",
            ),
            Label("Scanner results:", id="scanner-title"),
            Container(
            DataTable(id="scanner-table"),
                id="scanner-container",
            ),
            id="ticker_input_dlg_body",
        )

    async def on_mount(self, event: events.Mount) -> None:
        self.query_one("#ticker-input", Input).focus()
        table = self.query_one("#gainers-table", DataTable)
        self.gainers_table_columns = table.add_columns("Symbol", "% Δ", "Curr Price", "Open Price", "% Avg Vol", "Avg Vol", "Float")
        table.cursor_type = "row"
        table.show_cursor = True

        scanner_table = self.query_one("#scanner-table", DataTable)
        self.scanner_table_columns = scanner_table.add_columns("Symbol", "% Δ", "Curr Price", "Open Price", "% Avg Vol", "Avg Vol", "Float")
        scanner_table.cursor_type = "row"
        scanner_table.show_cursor = True
        self.refresh_top_movers()

        cached = self._load_scanner_cache()
        if cached:
            self._populate_scanner_table(cached)
        else:
            scanner_table.add_row("Scanning...", "", "", "")

        # schedule auto-refresh of the scanner
        self._refresh_job = self.set_interval(
            self.REFRESH_SECS, self.refresh_scanner, pause=False
        )



    async def on_unmount(self, event: events.Unmount) -> None:
        # cancel the refresher when the dialog closes
        self._refresh_job.stop()
        self._refresh_job = None
        if self._scan_pool:
            self._scan_pool.shutdown(wait=False, cancel_futures=True)
            self._scan_pool = None

    def on_data_table_row_selected(
            self,
            event: DataTable.RowSelected,
    ) -> None:
        log.debug(f"row selected: {event.row_key}")
        log.debug(f"data table: {event.data_table.name}")

        columns = self.gainers_table_columns if event.data_table.name == "gainers-table" else self.scanner_table_columns
        symbol = str(event.data_table.get_cell(event.row_key, columns[0])).strip().upper()  # row_key is the first column
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
            case "scanner-select-button":
                self._select_scanners()

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

    def refresh_top_movers(self):
        self.gainers_list = self.top_gainers_cb(limit=20)
        log.debug(f"Top 20 gainers today: {self.gainers_list}")
        table = self.query_one("#gainers-table", DataTable)
        table.clear()
        for row in self.gainers_list:
            open_price = row["price"] - row["change"]
            table.add_row(
                row["symbol"],
                row["changesPercentage"],
                f"${row['price']:.2f}",
                f"${open_price:.2f}",
                key=row["symbol"],
            )
        table.scroll_home()

    # Add MACD is positive and open.
    def _check_symbol(self, row):
        sym = row["symbol"]
        quote = self.quote_cb(sym)
        if not quote:
            return None

        # +5 % since yesterday’s close
        prev = quote.get("previousClose") or 0
        if prev == 0 or (quote["price"] - prev) / prev < 0.05:
            log.debug(f"symbol {sym} doesn't exceed price increase threshold")
            return None

        # ≥ 3× average volume
        avg_vol = quote.get("avgVolume") or 0
        if avg_vol == 0 or quote["volume"] < 3 * avg_vol:
            log.debug(f"symbol {sym} doesn't exceed volume threshold: {avg_vol}")
            return None

        # bullish news in last 12 h
        if not self.has_recent_positive_news_cb(sym, hours=48):
            log.debug(f"symbol {sym} doesn't have recent news update in 48 hours")
            return None

        return {**row, "open_price": quote["price"] - quote["change"]}

    def refresh_scanner(self):
        # ------------------------------------------------------------
        gainers = self.top_gainers_cb(limit=50)
        futures = [self._scan_pool.submit(self._check_symbol, row) for row in gainers]
        filtered = [f.result() for f in as_completed(futures) if f.result()]

        log.debug(f"Scanner results: {filtered}")
        self._populate_scanner_table(filtered)
        self._save_scanner_cache(filtered)


    def _populate_scanner_table(self, rows: list[dict]) -> None:
        # -------- update UI (main thread) -------------------------------
        table = self.query_one("#scanner-table", DataTable)
        table.clear()

        if not rows:
            table.add_row("No results found.", "", "", "")
        else:
            for row in rows:
                table.add_row(
                    row["symbol"],
                    row["changesPercentage"],
                    f"${row['price']:.2f}",
                    f"${row['open_price']:.2f}",
                )
            try:
                playsound.playsound(SCAN_SOUND_PATH, block=False)
            except Exception as exc:
                log.debug(f"scan-sound failed: {exc}")

        table.scroll_home()