from datetime import date, timedelta

from textual.screen import ModalScreen
from textual.widgets import Input, Button, Label, Static
from textual.app import ComposeResult
import asyncio
import inspect

class BacktestInputDialog(ModalScreen):
    """Modal form: symbol, from/to dates, and starting balance."""
    CSS = """
    BacktestInputDialog {
        align: center middle;
        width: 40%;
    }
    """

    def __init__(self, callback, default_symbol: str = ""):
        self._callback = callback
        self._default_symbol = default_symbol

        # --- Figure out last week’s Monday-Friday ---
        today = date.today()  # uses local timezone
        weekday = today.weekday()  # Monday=0 … Sunday=6
        start_this_week = today - timedelta(days=weekday)
        last_monday = start_this_week - timedelta(days=7)
        last_friday = last_monday + timedelta(days=4)
        self._default_from = last_monday.isoformat()
        self._default_to = last_friday.isoformat()

        super().__init__()

    def compose(self) -> ComposeResult:
        yield Static("Back-test Parameters", classes="title")
        yield Input(
            value=self._default_symbol,  # pre-populated
            placeholder="Symbol (e.g. NVDA)",
            id="symbol",
        )
        yield Input(
            value=self._default_from,
            placeholder="From date YYYY-MM-DD",
            id="from",
        )
        yield Input(
            value=self._default_to,
            placeholder="To date YYYY-MM-DD",
            id="to",
        )
        yield Input(value="10000", placeholder="Starting balance $", id="cash")
        yield Button("Run", id="run", variant="success")
        yield Button("Cancel", id="cancel", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run":
            vals = {
                "symbol": self.query_one("#symbol", Input).value.strip().upper(),
                "from": self.query_one("#from", Input).value.strip(),
                "to": self.query_one("#to", Input).value.strip(),
                "cash": self.query_one("#cash", Input).value.strip(),
            }
            self.dismiss()

            # Await callback if needed.
            result = self._callback(vals)
            if inspect.isawaitable(result):
                asyncio.create_task(result)
        else:
            self.dismiss()
