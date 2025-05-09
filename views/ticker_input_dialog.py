from textual.widgets import Input, Label, Button
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.message import Message

class TickerSubmitted(Message):
    def __init__(self, sender, symbol: str):
        super().__init__()
        self.sender = sender
        self.symbol = symbol

class TickerInputDialog(ModalScreen):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def compose(self):
        yield Vertical(
            Label("Enter new ticker symbol:"),
            Input(placeholder="e.g. AAPL", id="ticker-input"),
            Button("Submit", id="submit-button")
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "submit-button":
            input_widget = self.query_one("#ticker-input", Input)
            symbol = input_widget.value.strip().upper()
            if symbol:
                self.dismiss()
                self.callback(symbol)
