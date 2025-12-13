from textual.screen import Screen
from textual.widgets import Static, Button
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal


class BacktestErrorScreen(Screen):
    """Full-screen error dialog shown when a backtest fails."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("enter", "dismiss", "Close"),
    ]

    def __init__(self, message: str, *, id: str | None = None):
        super().__init__(id=id)
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="backtest-error-container"):
            yield Static(self._message, id="backtest-error-label")
            with Horizontal(id="backtest-error-buttons"):
                yield Button("Close", id="backtest-error-close-btn", variant="warning")

    def action_dismiss(self) -> None:
        try:
            self.app.pop_screen()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "backtest-error-close-btn":
            self.action_dismiss()
