import shutil
import subprocess
import webbrowser

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

    def on_markdown_link_clicked(self, event: Markdown.LinkClicked) -> None:
        event.prevent_default()
        url = event.href
        if not url:
            return
        if not self._open_url(url):
            try:
                self.app.notify(
                    f"Open this link in a browser: {url}",
                    severity="warning",
                )
            except Exception:
                pass

    def action_dismiss(self) -> None:
        try:
            self.dismiss(None)
        except Exception:
            pass

    def _open_url(self, url: str) -> bool:
        commands: list[list[str]] = []
        if shutil.which("kioclient5"):
            commands.append(["kioclient5", "exec", url])
        if shutil.which("kde-open5"):
            commands.append(["kde-open5", url])
        if shutil.which("xdg-open"):
            commands.append(["xdg-open", url])
        for cmd in commands:
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception:
                continue
        try:
            return webbrowser.open(url, new=2)
        except Exception:
            return False
