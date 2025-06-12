from textual.screen import Screen
from textual.widgets import DataTable, Header, Footer
from textual.reactive import reactive

class StrategyScreen(Screen):
    """Modal screen listing live strategy signals."""
    BINDINGS = [
        ("s", "app.pop_screen", "Back"),
        ("escape", "app.pop_screen", "Back"),
    ]

    signals: reactive[list] = reactive([])

    def __init__(self, signals: list[dict]):
        super().__init__()
        self.signals = signals

    def compose(self):
        table = DataTable(zebra_stripes=True)
        table.add_columns("Date/Time", "Symbol", "Side", "Price", "Reason")
        for sig in sorted(self.signals, key=lambda r: r["time"]):
            dt = sig["time"].strftime("%Y-%m-%d %H:%M") if sig.get("time") else ""
            price = sig.get("price")
            table.add_row(
                dt,
                sig.get("symbol", ""),
                sig.get("side", "").upper(),
                f"{price:.2f}" if price is not None else "",
                sig.get("reason", ""),
            )
        yield Header(show_clock=False)
        yield table
        yield Footer()
