from datetime import date, timedelta

from textual.screen import ModalScreen
from textual.widgets import Input, Button, Label, Static, Select
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
import asyncio
import inspect


class BacktestInputDialog(ModalScreen):
    """Modal form for selecting symbol, strategy and date range."""

    CSS = """
    BacktestInputDialog {
        align: center middle;
    }

    #backtest-input-body {
        width: 66%;
        border: solid green;
        padding: 1 2;
        content-align-horizontal: center;
        background: #1a1a1a;
    }

    #backtest-input-body Input,
    #backtest-input-body Select {
        background: #262626;
        color: #00ff55;
    }
    """

    def __init__(
        self,
        callback,
        default_symbol: str = "",
        strategies=None,
        current_strategy: str | None = None,
    ):
        self._callback = callback
        self._default_symbol = default_symbol
        self._strategies = strategies or []
        self._current_strategy = current_strategy or (
            self._strategies[0] if self._strategies else ""
        )

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
        yield Vertical(
            Static("Back-test Parameters", classes="title"),
            Input(
                value=self._default_symbol,  # pre-populated
                placeholder="Symbol (e.g. NVDA)",
                id="symbol",
            ),
            Select(
                id="strategy-select",
                prompt="",
                value=self._current_strategy,
                options=[(s, s) for s in self._strategies],
            ),
            Input(
                value=self._default_from,
                placeholder="From date YYYY-MM-DD",
                id="from",
            ),
            Input(
                value=self._default_to,
                placeholder="To date YYYY-MM-DD",
                id="to",
            ),
            Input(value="10000", placeholder="Starting balance $", id="cash"),
            Horizontal(
                Button("Run", id="run", variant="success"),
                Button("Cancel", id="cancel", variant="error"),
                id="backtest-buttons-row",
            ),
            id="backtest-input-body",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run":
            vals = {
                "symbol": self.query_one("#symbol", Input).value.strip().upper(),
                "strategy": self.query_one("#strategy-select", Select).value,
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
