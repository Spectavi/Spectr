from textual.screen import ModalScreen
from textual.widgets import Static, Button
from textual.containers import Vertical, Horizontal
from textual.app import ComposeResult
from textual.message import Message

class SetupConfirmDialog(ModalScreen):
    """Simple yes/no confirmation dialog for setup."""

    class Result(Message):
        def __init__(self, sender: "SetupConfirmDialog", value: bool) -> None:
            super().__init__()
            self.value = value

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("Reconfigure API keys?"),
            Horizontal(
                Button("Yes", id="yes", variant="success"),
                Button("No", id="no", variant="error"),
                id="setup_confirm_row",
            ),
            id="setup_confirm_body",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

