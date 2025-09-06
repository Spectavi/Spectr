from textual.screen import ModalScreen
from textual.widgets import Static, Input, Button, Label, Select
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.app import ComposeResult
from textual.message import Message
from textual import events


class SetupDialog(ModalScreen):
    """Ask the user for broker and data provider configuration."""

    BINDINGS = [
        ("enter", "save", "Save"),
        ("escape", "cancel", "Cancel"),
    ]

    class Submit(Message):
        def __init__(
            self,
            sender: "SetupDialog",
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

    def __init__(
        self, callback, defaults: dict | None = None, *, exit_on_cancel: bool = True
    ) -> None:
        super().__init__()
        self._callback = callback
        self._defaults = defaults or {}
        self._exit_on_cancel = exit_on_cancel

    def compose(self) -> ComposeResult:
        yield VerticalScroll(
            Static("Setup", id="setup-title"),
            Label("Broker:"),
            Select(
                id="broker-select",
                options=[("Alpaca", "alpaca")],
            ),
            Input(placeholder="Broker API Key", id="broker-key"),
            Input(placeholder="Broker Secret Key", id="broker-secret"),
            Label("Paper Trading:"),
            Select(id="paper-select", options=[("Alpaca", "alpaca")]),
            Input(placeholder="Paper API Key", id="paper-key"),
            Input(placeholder="Paper Secret Key", id="paper-secret"),
            Label("Data Provider:"),
            Select(
                id="data-select",
                options=[
                    ("Alpaca", "alpaca"),
                    ("FMP", "fmp"),
                ],
            ),
            Input(placeholder="Data API Key", id="data-key"),
            Input(placeholder="Data Secret Key", id="data-secret"),
            Label("OpenAI API Key:"),
            Input(placeholder="OpenAI API Key", id="openai-key"),
            Horizontal(
                Button("Save", id="save", variant="success"),
                Button("Cancel", id="cancel", variant="error"),
                id="setup_buttons_row",
            ),
            id="setup_body",
        )

    async def on_mount(self, event: events.Mount) -> None:
        if self._defaults:
            broker = self._defaults.get("broker", "alpaca")
            if broker not in {"alpaca"}:
                broker = "alpaca"
            self.query_one("#broker-select", Select).value = broker
            paper = self._defaults.get("paper", "alpaca")
            if paper not in {"alpaca"}:
                paper = "alpaca"
            self.query_one("#paper-select", Select).value = paper
            data = self._defaults.get("data_api", "alpaca")
            if data not in {"alpaca", "fmp"}:
                data = "alpaca"
            self.query_one("#data-select", Select).value = data

        self._update_broker_fields()
        self._update_paper_fields()
        self._update_data_fields()

        if self._defaults:
            self.query_one("#broker-key", Input).value = self._defaults.get(
                "broker_key", ""
            )
            self.query_one("#broker-secret", Input).value = self._defaults.get(
                "broker_secret", ""
            )
            self.query_one("#paper-key", Input).value = self._defaults.get(
                "paper_key", ""
            )
            self.query_one("#paper-secret", Input).value = self._defaults.get(
                "paper_secret", ""
            )
            self.query_one("#data-key", Input).value = self._defaults.get(
                "data_key", ""
            )
            self.query_one("#data-secret", Input).value = self._defaults.get(
                "data_secret", ""
            )
            self.query_one("#openai-key", Input).value = self._defaults.get(
                "openai_key", ""
            )

        # Focus the first input field so the user can start typing immediately
        self.query_one("#broker-key", Input).focus()

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

    def action_cancel(self) -> None:
        """Dismiss or exit when the dialog is cancelled."""
        if self._exit_on_cancel:
            self.app.exit()
        else:
            self.dismiss()

    def action_save(self) -> None:
        """Collect field values and exit with the result."""
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

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self.action_save()
        else:
            self.action_cancel()
