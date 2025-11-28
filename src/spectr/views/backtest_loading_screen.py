import itertools
from textual.screen import Screen
from textual.widgets import Static, Button
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal


class BacktestLoadingScreen(Screen):
    """Full-screen loading screen shown while a backtest runs."""

    BINDINGS = [
        # No-op escape so users can't accidentally close while running
        ("escape", "noop", ""),
    ]

    def __init__(self, message: str = "Running backtest...", *, id: str | None = None):
        super().__init__(id=id)
        self._message = message
        self._label: Static | None = None
        self._timer = None
        self._spinner = itertools.cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])  # braille spinner

    def compose(self) -> ComposeResult:
        self._label = Static(self._format_text(), id="backtest-loading-label")
        with Vertical(id="backtest-loading-container"):
            yield self._label
            with Horizontal(id="backtest-loading-buttons"):
                yield Button("Cancel", id="backtest-cancel-btn", variant="error")

    def _format_text(self) -> str:
        frame = next(self._spinner)
        return f"{frame} {self._message}"

    def set_message(self, msg: str) -> None:
        self._message = msg
        if self._label:
            self._label.update(self._format_text())

    def on_mount(self) -> None:
        # Update spinner at a steady clip
        self._timer = self.set_interval(0.1, self._tick)

    def _tick(self) -> None:
        if self._label:
            self._label.update(self._format_text())

    async def on_unmount(self) -> None:
        if self._timer:
            try:
                self._timer.stop()
            except Exception:
                pass
            self._timer = None

    def action_noop(self) -> None:
        # Explicitly do nothing
        return

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "backtest-cancel-btn":
            try:
                if hasattr(self.app, "cancel_backtest"):
                    self.app.cancel_backtest()
                else:
                    # Fallback: just close the screen
                    self.app.pop_screen()
            except Exception:
                pass
