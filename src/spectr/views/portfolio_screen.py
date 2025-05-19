from textual.screen import Screen
from textual.widgets import Static, DataTable, Header, Footer
from textual.containers import Vertical
from textual.reactive import reactive
from textual import events


class PortfolioScreen(Screen):
    """Modal screen that shows cash, invested value, and current holdings."""

    BINDINGS = [
        ("p",      "app.pop_screen", "Back"),   # allow P to close, too
        ("escape", "app.pop_screen", "Back"),
    ]

    # reactive so the table can be refreshed later if you want
    positions = reactive(list)
    cash      = reactive(0.0)
    buying_power = reactive(0.0)
    portfolio_value = reactive(0.0)
    is_paper  = reactive(True)

    def __init__(self, cash: float, buying_power: float, portfolio_value: float, positions: list, real_trades: bool) -> None:
        super().__init__()
        self.cash = cash
        self.buying_power = buying_power
        self.portfolio_value = portfolio_value
        self.positions = positions
        self.real_trades = real_trades
        self.top_title = Static(id="portfolio_title") # gets filled in on_mount
        self.table = DataTable(zebra_stripes=True)
        self.table.add_columns("Symbol", "Qty", "Value")

    def compose(self):
        yield Static()
        yield self.top_title
        yield Static()
        yield Vertical(self.table, id="port_table_container")
        #yield Footer()

    async def on_mount(self, event: events.Mount) -> None:
        # title
        acct = "PAPER" if self.is_paper else "LIVE"

        top_title_widget = self.query_one("#portfolio_title", Static)
        top_title_widget.update(
            f"[b]{acct} ACCOUNT[/b] — "
            f"Cash: [green]${self.cash:,.2f}[/] • "
            f"Buying Power: [cyan]${self.buying_power:,.2f}[/] • "
            f"Portfolio Value: [cyan]${self.portfolio_value:,.2f}[/]",
        )

        # table
        self.table.clear()
        for pos in self.positions:
            self.table.add_row(
                pos["symbol"],
                str(pos["qty"]),
                f"${pos['value']:,.2f}",
            )           # one-time load
        self.table.scroll_home()

