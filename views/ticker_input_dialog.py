from textual.widgets import Input, Label, Button
from textual.containers import Vertical
from textual.screen import ModalScreen

class TickerInputDialog(ModalScreen):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def compose(self):
        yield Vertical(
            Label("Enter new ticker symbol list (up to 10):"),
            Input(placeholder="e.g. AAPL,AMZN,META,MSFT,NVDA,TSLA,GOOG,VTI,GLD", id="ticker-input"),
            Button("Submit", id="submit-button")
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "submit-button":
            self._submit()

    def on_input_submitted(self, event: Input.Submitted):
        self._submit()

    def _submit(self):
        input_widget = self.query_one("#ticker-input", Input)
        symbol = input_widget.value.strip().upper()
        if symbol:
            self.dismiss()
            self.callback(symbol)
