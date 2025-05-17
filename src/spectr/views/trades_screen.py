# ── NEW: simple modal that shows a DataTable of trades ────────────────────
from textual.screen import Screen
from textual.widgets import DataTable, Header, Footer
from textual.reactive import reactive

class TradesScreen(Screen):
    """Modal screen that lists every buy / sell from the last back-test."""
    BINDINGS = [("tab", "app.pop_screen", "Back"),  # Tab closes the modal
                ("escape", "app.pop_screen", "Back")]

    trades: reactive[list] = reactive([])

    def __init__(self, trades: list[dict]):        # ➊ list comes from SpectrApp
        super().__init__()
        self.trades = trades

    def compose(self):
        table = DataTable(zebra_stripes=True, header_style="bold")
        table.add_columns("#", "Type", "Time", "Price", "Value")

        for i, trade in enumerate(self.trades, 1):
            table.add_row(
                str(i),
                trade["type"].upper(),
                trade["time"].strftime("%Y-%m-%d %H:%M"),
                f"${trade['price']:.2f}",
                f"${trade['value']:.2f}" if trade.get("value") else "—",
            )

        yield Header(show_clock=False)
        yield table
        yield Footer()
