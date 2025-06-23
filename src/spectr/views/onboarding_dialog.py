from textual.screen import ModalScreen
from textual.widgets import Static, Input, Button, Label, Select
from textual.app import ComposeResult
from textual.message import Message
from textual import events

class OnboardingDialog(ModalScreen):
    """Ask the user for broker and data provider configuration."""

    BINDINGS = [
        ("enter", "save", "Save"),
        ("escape", "app.pop_screen", "Cancel"),
    ]

    class Submit(Message):
        def __init__(
            self,
            sender: "OnboardingDialog",
            *,
            broker: str,
            paper: str,
            data: str,
            broker_key: str,
            broker_secret: str,
            paper_key: str,
            paper_secret: str,
            data_key: str,
            data_secret: str,
            openai_key: str,
        ) -> None:
            super().__init__()
            self.broker = broker
            self.paper = paper
            self.data = data
            self.broker_key = broker_key
            self.broker_secret = broker_secret
            self.paper_key = paper_key
            self.paper_secret = paper_secret
            self.data_key = data_key
            self.data_secret = data_secret
            self.openai_key = openai_key

    def __init__(self, callback) -> None:
        super().__init__()
        self._callback = callback

    def compose(self) -> ComposeResult:
        yield Static("Initial Setup", classes="title")

        yield Label("Broker:")
        yield Select(id="broker-select", options=[("Alpaca", "alpaca"), ("Robinhood", "robinhood")])
        yield Input(placeholder="Broker API Key", id="broker-key")
        yield Input(placeholder="Broker Secret Key", id="broker-secret")

        yield Label("Paper Trading:")
        yield Select(id="paper-select", options=[("Alpaca", "alpaca")])
        yield Input(placeholder="Paper API Key", id="paper-key")
        yield Input(placeholder="Paper Secret Key", id="paper-secret")

        yield Label("Data Provider:")
        yield Select(id="data-select", options=[("Alpaca", "alpaca"), ("Robinhood", "robinhood"), ("FMP", "fmp")])
        yield Input(placeholder="Data API Key", id="data-key")
        yield Input(placeholder="Data Secret Key", id="data-secret")

        yield Label("OpenAI API Key:")
        yield Input(placeholder="OpenAI API Key", id="openai-key")

        yield Button("Save", id="save", variant="success")
        yield Button("Cancel", id="cancel", variant="error")

    async def on_mount(self, event: events.Mount) -> None:
        self._update_broker_fields()
        self._update_paper_fields()
        self._update_data_fields()

    async def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "broker-select":
            self._update_broker_fields()
        elif event.select.id == "paper-select":
            self._update_paper_fields()
        elif event.select.id == "data-select":
            self._update_data_fields()

    def _update_broker_fields(self) -> None:
        broker = self.query_one("#broker-select", Select).value
        key_input = self.query_one("#broker-key", Input)
        secret_input = self.query_one("#broker-secret", Input)
        if broker == "alpaca":
            key_input.placeholder = "Broker API Key"
            secret_input.placeholder = "Broker Secret Key"
            secret_input.display = True
        else:  # robinhood
            key_input.placeholder = "Broker Username"
            secret_input.placeholder = "Broker Password"
            secret_input.display = True
    def _update_paper_fields(self) -> None:
        paper = self.query_one("#paper-select", Select).value
        key_input = self.query_one("#paper-key", Input)
        secret_input = self.query_one("#paper-secret", Input)
        if paper == "alpaca":
            key_input.placeholder = "Paper API Key"
            secret_input.placeholder = "Paper Secret Key"
            secret_input.display = True
        else:
            secret_input.display = True

    def _update_data_fields(self) -> None:
        data = self.query_one("#data-select", Select).value
        key_input = self.query_one("#data-key", Input)
        secret_input = self.query_one("#data-secret", Input)
        if data == "fmp":
            key_input.placeholder = "Data API Key"
            secret_input.display = False
        elif data == "alpaca":
            key_input.placeholder = "Data API Key"
            secret_input.placeholder = "Data Secret Key"
            secret_input.display = True
        else:  # robinhood
            key_input.placeholder = "Data Username"
            secret_input.placeholder = "Data Password"
            secret_input.display = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            broker = self.query_one("#broker-select", Select).value
            paper = self.query_one("#paper-select", Select).value
            data = self.query_one("#data-select", Select).value
            broker_key = self.query_one("#broker-key", Input).value
            broker_secret = self.query_one("#broker-secret", Input).value
            paper_key = self.query_one("#paper-key", Input).value
            paper_secret = self.query_one("#paper-secret", Input).value
            data_key = self.query_one("#data-key", Input).value
            data_secret = self.query_one("#data-secret", Input).value
            openai_key = self.query_one("#openai-key", Input).value
            self.dismiss()
            if self._callback:
                self._callback(
                    broker,
                    paper,
                    data,
                    broker_key,
                    broker_secret,
                    paper_key,
                    paper_secret,
                    data_key,
                    data_secret,
                    openai_key,
                )
        else:
            self.dismiss()
