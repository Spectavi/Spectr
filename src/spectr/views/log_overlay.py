import logging
from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static
from textual.screen import ModalScreen


class ErrorLogOverlay(ModalScreen):
    """Modal overlay showing recent ERROR log lines."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]

    def __init__(self, *, id: str | None = None):
        super().__init__(id=id)
        self._buffer: list[str] = []

    def compose(self) -> ComposeResult:
        yield Vertical(Static("", id="log-overlay-content"), id="log-overlay-container")

    def on_mount(self) -> None:
        handler = _OverlayLogHandler(self)
        handler.setLevel(logging.ERROR)
        logging.getLogger().addHandler(handler)
        self._handler = handler
        self._update_display()

    def add_line(self, line: str) -> None:
        self._buffer.append(line)
        self._buffer = self._buffer[-200:]
        self._update_display()

    def _update_display(self) -> None:
        try:
            widget = self.query_one("#log-overlay-content", Static)
            widget.update("\n".join(self._buffer) or "No error messages logged yet")
        except Exception:
            pass

    async def on_key(self, event: events.Key) -> None:
        key = getattr(event, "key", "")
        char = getattr(event, "character", None)
        if key in {"`", "~"} or char in {"`", "~"}:
            try:
                event.stop()
            except Exception:
                pass
            self.action_dismiss()

    def action_dismiss(self) -> None:
        try:
            self.dismiss(None)
        except Exception:
            pass

    def on_unmount(self) -> None:
        handler = getattr(self, "_handler", None)
        if handler:
            try:
                logging.getLogger().removeHandler(handler)
            except Exception:
                pass
            self._handler = None


class _OverlayLogHandler(logging.Handler):
    """Simple handler to forward ERROR messages into the overlay."""

    def __init__(self, overlay: ErrorLogOverlay):
        super().__init__()
        self.overlay = overlay

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            if self.overlay:
                self.overlay.add_line(msg)
        except Exception:
            pass
