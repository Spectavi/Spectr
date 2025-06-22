from textual.screen import ModalScreen
from textual.widgets import Static, Input, Button, Label, Select
from textual.app import ComposeResult
from textual.message import Message

class OnboardingDialog(ModalScreen):
    """Ask the user for broker and data provider configuration."""

    BINDINGS = [
        ("enter", "save", "Save"),
        ("escape", "app.pop_screen", "Cancel"),
    ]

    class Submit(Message):
        def __init__(self, sender: "OnboardingDialog", *, broker: str, data: str, broker_key: str, data_key: str) -> None:
            super().__init__()
            self.broker = broker
            self.data = data
            self.broker_key = broker_key
            self.data_key = data_key

    def __init__(self, callback) -> None:
        super().__init__()
        self._callback = callback

    def compose(self) -> ComposeResult:
        yield Static("Initial Setup", classes="title")
        yield Label("Broker:")
        yield Select(id="broker-select", options=[("Alpaca", "alpaca"), ("Robinhood", "robinhood")])
        yield Input(placeholder="Broker API Key", id="broker-key")
        yield Label("Data Provider:")
        yield Select(id="data-select", options=[("Alpaca", "alpaca"), ("Robinhood", "robinhood"), ("FMP", "fmp")])
        yield Input(placeholder="Data API Key", id="data-key")
        yield Button("Save", id="save", variant="success")
        yield Button("Cancel", id="cancel", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            broker = self.query_one("#broker-select", Select).value
            data = self.query_one("#data-select", Select).value
            broker_key = self.query_one("#broker-key", Input).value
            data_key = self.query_one("#data-key", Input).value
            self.dismiss()
            if self._callback:
                self._callback(broker, data, broker_key, data_key)
        else:
            self.dismiss()
