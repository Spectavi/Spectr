from textual.widgets import Input, Label, Button
from textual.containers import Vertical
from textual.screen import ModalScreen

class MultiTickerInputDialog(ModalScreen):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def compose(self):
        yield Vertical(
            Label("Enter symbols (comma-separated):"),
            Input(placeholder="e.g. AAPL,TSLA,NVDA", id="multi-input"),
            Button("Submit", id="submit-button"),
            id="multi-ticker-dialog"
        )

    async def on_mount(self):
        self.query_one("#multi-input").focus()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "submit-button":
            self._submit()

    def on_input_submitted(self, event: Input.Submitted):
        self._submit()

    def _submit(self):
        input_widget = self.query_one("#multi-input", Input)
        raw = input_widget.value.strip()
        if raw:
            symbols = [s.strip().upper() for s in raw.split(",") if s.strip()]
            self.dismiss()
            self.callback(symbols)
