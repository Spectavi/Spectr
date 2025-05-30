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
    real_trades  = reactive(False)

    def __init__(self, cash: float, buying_power: float, portfolio_value: float, positions: list, orders_callback, real_trades: bool) -> None:
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

        #Orders Table
        self.order_table = DataTable(zebra_stripes=True, id="orders-table")
        self.order_table.add_columns("Symbol", "Side", "Qty", "Type", "Status")
        self.orders_callback = orders_callback
        self._refresh_job = None  # handle for cancel




    def compose(self):
        yield Vertical(
            self.top_title,
            Static("Portfolio assets:", id="assets-title"),
            self.holdings_table,
            Static("Order History:", id="orders-title"),
            self.order_table,
            id="portfolio-screen",
        )

    async def on_mount(self, event: events.Mount) -> None:
        # title
        acct = "LIVE" if self.real_trades else "PAPER"

        top_title_widget = self.query_one("#portfolio-title", Static)
        top_title_widget.update(
            f"** [b]{acct} ACCOUNT[/b] **\n"
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
            self.REFRESH_SECS, self._refresh_orders(), pause=False
        )

    async def on_unmount(self, event: events.Unmount) -> None:
        # cancel the refresher when the dialog closes
        self._refresh_job.stop()
        self._refresh_job = None

    def _refresh_orders(self):
        log.debug("Refreshing orders")

        orders = None
        try:
            log.debug("Fetching orders...")
            orders = self.orders_callback(self.real_trades)
            log.debug(f"Account orders: {orders}")
        except Exception:
            log.warning(f"Account orders fetch failed! get_all_orders()")
            top_title_widget = self.query_one("#portfolio-title", Static)
            top_title_widget.update(
                f"[b]ACCOUNT ACCESS FAILED![/b]"
            )

        if orders:
            log.debug(f"Order History: {orders}")
            table = self.query_one("#orders-table", DataTable)
            table.clear()
            for order in orders:
                print(f"Order: {order}")
                table.add_row(
                    order.symbol,
                    order.side,
                    order.qty,
                    order.order_type,
                    order.status,
                )
            table.scroll_home()
