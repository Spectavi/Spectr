from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown, Static


class MarkdownModal(ModalScreen):
    """Modal that shows markdown content in a scrollable view."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]

    def __init__(self, markdown: str, *, title: str | None = None, id: str | None = None):
        super().__init__(id=id)
        self._markdown = markdown or "No content provided."
        self._title = title

    def compose(self) -> ComposeResult:
        with Vertical(id="markdown-modal-container"):
            if self._title:
                yield Static(self._title, id="markdown-modal-title")
            with VerticalScroll(id="markdown-modal-scroll"):
                yield Markdown(self._markdown, id="markdown-modal-content")
            with Horizontal(id="markdown-modal-actions"):
                yield Button("Close", id="markdown-modal-close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "markdown-modal-close":
            self.dismiss(None)

    def action_dismiss(self) -> None:
        try:
            self.dismiss(None)
        except Exception:
            pass
