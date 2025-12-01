from datetime import date, timedelta

from textual.screen import Screen, ModalScreen
from textual.widgets import Input, Button, Label, Static, Select
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
import asyncio
import inspect


class BacktestInputDialog(ModalScreen):
    """Full-screen form for selecting symbol, strategy and date range."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Cancel"),
    ]

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
        # Track whether user clicked Run so the app stays in backtest mode
        # when this screen is dismissed.
        self._proceed_to_results = False

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
            Static("Back-test Parameters", id="backtest-title", classes="title"),
            Label("Strategy:"),
            Select(
                id="strategy-select",
                prompt="",
                value=self._current_strategy,
                options=[(s, s) for s in self._strategies],
            ),
            Label("Symbol:"),
            Input(
                value=self._default_symbol,
                placeholder="Symbol (e.g. NVDA)",
                id="symbol-input",
            ),
            Label("From:"),
            Input(
                value=self._default_from,
                placeholder="From date YYYY-MM-DD",
                id="from",
            ),
            Label("To:"),
            Input(
                value=self._default_to,
                placeholder="To date YYYY-MM-DD",
                id="to",
            ),
            Label("Starting Cash:"),
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
            self._proceed_to_results = True
            vals = {
                "symbol": self.query_one("#symbol", Input).value.strip().upper(),
                "strategy": self.query_one("#strategy-select", Select).value,
                "from": self.query_one("#from", Input).value.strip(),
                "to": self.query_one("#to", Input).value.strip(),
                "cash": self.query_one("#cash", Input).value.strip(),
            }
            # Run the callback without blocking the UI thread.
            if inspect.iscoroutinefunction(self._callback):
                asyncio.create_task(self._callback(vals))
            else:
                asyncio.create_task(asyncio.to_thread(self._callback, vals))
        else:
            self.dismiss()

    async def on_unmount(self) -> None:
        # If the user cancelled (didn't press Run), leave backtest mode and
        # allow the app to restore the symbol view and resume polling.
        if not self._proceed_to_results:
            try:
                if hasattr(self.app, "_exit_backtest"):
                    self.app._exit_backtest()
                else:
                    self.app.is_backtest = False
            except Exception:
                pass
