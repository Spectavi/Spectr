import logging

from textual.screen import Screen
from textual.widgets import Static, DataTable, Header, Footer
from textual.containers import Vertical
from textual.reactive import reactive
from textual import events

log = logging.getLogger(__name__)

class PortfolioScreen(Screen):
    """Modal screen that shows cash, invested value, and current holdings."""

    BINDINGS = [
        ("p",      "app.pop_screen", "Back"),   # allow P to close, too
        ("escape", "app.pop_screen", "Back"),
    ]

    REFRESH_SECS = 10  # how often to poll pending orders

    # reactive so the table can be refreshed later if you want
    positions = reactive(list)
    cash      = reactive(0.0)
    buying_power = reactive(0.0)
    portfolio_value = reactive(0.0)
    is_paper  = reactive(True)

    def __init__(self, cash: float, buying_power: float, portfolio_value: float, positions: list, pending_orders_callback, real_trades: bool) -> None:
        super().__init__()
        self.cash = cash
        self.buying_power = buying_power
        self.portfolio_value = portfolio_value
        self.positions = positions
        self.real_trades = real_trades
        self.top_title = Static(id="portfolio-title") # gets filled in on_mount
        # Holdings Table
        self.holdings_table = DataTable(zebra_stripes=True, id="holdings-table")
        self.holdings_table.add_columns("Symbol", "Qty", "Value")

        # Pending Orders Table
        self.order_table = DataTable(zebra_stripes=True, id="pending-orders-table")
        self.order_table.add_columns("Symbol", "Side", "Qty", "Type", "Status")
        self.pending_orders_callback = pending_orders_callback
        self._refresh_job = None  # handle for cancel



    def compose(self):
        yield Vertical(
            self.top_title,
            Static("Portfolio assets:", id="assets-title"),
            self.holdings_table,
            Static("Pending orders:", id="orders-title"),
            self.order_table,
            id="portfolio-screen",
        )

    async def on_mount(self, event: events.Mount) -> None:
        # title
        acct = "PAPER" if self.is_paper else "LIVE"

        top_title_widget = self.query_one("#portfolio-title", Static)
        top_title_widget.update(
            f"[b]{acct} ACCOUNT[/b] — "
            f"Cash: [green]${self.cash:,.2f}[/]\n"
            f"Buying Power: [cyan]${self.buying_power:,.2f}[/]\n"
            f"Portfolio Value: [cyan]${self.portfolio_value:,.2f}[/]",
        )

        # table
        self.holdings_table.clear()
        for pos in self.positions:
            log.debug(f"position: {pos}")
            self.holdings_table.add_row(
                pos.symbol,
                pos.qty,
                pos.market_value,
            )           # one-time load
        self.holdings_table.scroll_home()

        # schedule auto-refresh of the quote
        self._refresh_job = self.set_interval(
            self.REFRESH_SECS, self._refresh_pending_orders(), pause=False
        )

    async def on_unmount(self, event: events.Unmount) -> None:
        # cancel the refresher when the dialog closes
        self._refresh_job.stop()
        self._refresh_job = None

    def _refresh_pending_orders(self):
        if not self.is_mounted:
            return

        pending_orders = self.pending_orders_callback(self.real_trades)
        log.debug(f"Pending orders: {pending_orders}")
        if pending_orders:
            table = self.query_one("#pending-orders-table", DataTable)
            table.clear()
            for order in pending_orders:
                table.add_row(
                    order.symbol,
                    order.side,
                    order.qty,
                    order.type,
                    order.status,
                )
            table.scroll_home()
