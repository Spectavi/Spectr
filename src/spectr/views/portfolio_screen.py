import logging

from typing import Optional

from textual.screen import Screen
from textual.widgets import Static, DataTable, Switch, Input, Button
from textual.containers import Vertical, Container, Horizontal
from textual.reactive import reactive
from textual import events
from textual.widgets._data_table import CellDoesNotExist

from ..fetch.broker_interface import OrderSide
import asyncio

from .equity_curve_view import EquityCurveView
from .setup_confirm_dialog import SetupConfirmDialog
from .setup_app import SetupApp

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
    trade_amount = reactive(0.0)

    def __init__(
        self,
        cash: Optional[float],
        buying_power: Optional[float],
        portfolio_value: Optional[float],
        positions: Optional[list],
        orders: Optional[list],
        orders_callback,
        cancel_order_callback,
        real_trades: bool,
        set_real_trades_cb=None,
        disable_live_switch: bool = False,
        hide_live_switch: bool = False,
        auto_trading: bool = False,
        set_auto_trading_cb=None,
        balance_callback=None,
        positions_callback=None,
        equity_data: Optional[list] = None,
        trade_amount: float = 0.0,
        set_trade_amount_cb=None,
    ) -> None:
        super().__init__()
        self.cash = cash or 0.0
        self.buying_power = buying_power or 0.0
        self.portfolio_value = portfolio_value or 0.0
        self.positions = positions or []
        self.cached_orders = orders or []
        if self.cached_orders:
            self.cached_orders.sort(key=self._order_date, reverse=True)
        self.real_trades = real_trades
        self.disable_live_switch = disable_live_switch
        self.hide_live_switch = hide_live_switch
        self._has_cached_balance = cash is not None
        self._has_cached_positions = positions is not None
        self._has_cached_orders = orders is not None
        self._set_real_trades_cb = set_real_trades_cb
        self.auto_trading_enabled = auto_trading
        self._set_auto_trading_cb = set_auto_trading_cb
        self._cancel_order_cb = cancel_order_callback
        self.trade_amount = trade_amount
        self._set_trade_amount_cb = set_trade_amount_cb
        self.top_title = Static(id="portfolio-title") # gets filled in on_mount

        # Equity curve graph
        self.equity_view = EquityCurveView(id="equity-curve")

        # Holdings Table
        self.holdings_table = DataTable(zebra_stripes=True, id="holdings-table")
        self.holdings_table_columns = self.holdings_table.add_columns("Symbol", "Qty", "Value", "Avg Cost", "Profit")
        self.holdings_table.cursor_type = "row"
        self.holdings_table.show_cursor = True

        #Orders Table
        self.order_table = DataTable(zebra_stripes=True, id="orders-table")
        self.order_table_columns = self.order_table.add_columns("Date/Time", "Symbol", "Side", "Qty", "Value", "Type", "Status", "Cancel?", "Order ID")
        self._cancel_col = self.order_table_columns[-2]
        self._order_id_col = self.order_table_columns[-1]
        self.order_table.cursor_type = "cell"
        self.order_table.show_cursor = True

        self.mode_switch = Switch(value=self.real_trades, id="trade-mode-switch")
        self.mode_switch.disabled = self.disable_live_switch
        self.auto_switch = Switch(value=self.auto_trading_enabled, id="auto-trade-switch")
        self.orders_callback = orders_callback
        self.balance_callback = balance_callback
        self.positions_callback = positions_callback
        self._refresh_job = None  # handle for cancel
        self._balance_job = None  # periodic balance refresher

        if equity_data:
            self.equity_view.data = list(equity_data)

        # Initial placeholder content
        acct = "LIVE" if self.real_trades else "PAPER"
        if self._has_cached_balance:
            self.top_title.update(
                f"** [b]{acct} ACCOUNT[/b] **\n"
                f"Cash: [green]${self.cash:,.2f}[/]\n"
                f"Buying Power: [cyan]${self.buying_power:,.2f}[/]\n"
                f"Portfolio Value: [cyan]${self.portfolio_value:,.2f}[/]",
            )
            self.equity_view.add_point(self.cash, self.portfolio_value)
        else:
            self.top_title.update(
                f"** [b]{acct} ACCOUNT[/b] **\n"
                "Cash: Loading...\n"
                "Buying Power: Loading...\n"
                "Portfolio Value: Loading...",
            )

        if self._has_cached_positions:
            for pos in self.positions:
                cost = getattr(pos, "cost_basis", None)
                if cost is None:
                    try:
                        cost = float(pos.qty) * float(pos.avg_entry_price)
                    except Exception:
                        cost = 0.0
                profit = float(pos.market_value) - float(cost) if cost else 0.0
                self.holdings_table.add_row(
                    pos.symbol,
                    pos.qty,
                    pos.market_value,
                    cost,
                    profit,
                )
        else:
            self.holdings_table.add_row("Loading...", "", "", "", "")

        if self._has_cached_orders:
            self.cached_orders.sort(key=self._order_date, reverse=True)
            for order in self.cached_orders:
                price = (
                    getattr(order, "filled_avg_price", None)
                    or getattr(order, "limit_price", None)
                    or getattr(order, "price", None)
                    or 0.0
                )
                try:
                    value = float(order.qty) * float(price)
                except Exception:
                    value = 0.0

                dt = (
                        getattr(order, "submitted_at", None)
                        or getattr(order, "created_at", None)
                        or getattr(order, "filled_at", None)
                )
                if hasattr(dt, "strftime"):
                    dt_str = dt.strftime("%Y-%m-%d %H:%M")
                else:
                    dt_str = str(dt) if dt else ""

                self.order_table.add_row(
                    dt_str,
                    order.symbol,
                    order.side,
                    order.qty,
                    value,
                    order.order_type,
                    order.status,
                    "Cancel" if self._is_cancelable(order.status.name) else "",
                    key=getattr(order, "id", None),
                )
        else:
            self.order_table.add_row("Loading...", "", "", "", "", "", "", "")



    def compose(self):
        yield Vertical(
            self.top_title,
            Horizontal(
                *(
                    []
                    if self.hide_live_switch
                    else [
                        Container(
                            Static("Live Trading"),
                            self.mode_switch,
                            id="mode-switch-container",
                        )
                    ]
                ),
                Container(
                    Static("Auto Trades"),
                    self.auto_switch,
                    id="trade-switch-container"),
                id="trade-mode-container",
            ),
            Horizontal(
                Static("Trade Amount $"),
                id="trade-amount-row",
            ),
            Input(id="trade-amount-input", placeholder="0.00"),
            Static("Equity Curve:", id="equity-curve-title"),
            self.equity_view,

            Static("Holdings:", id="holdings-title"),
            self.holdings_table,
            Static("Order History:", id="orders-title"),
            self.order_table,
            Horizontal(
                Button("Close", id="close-button", variant="error"),
                Button("Setup", id="setup-button"),
                id="portfolio_buttons_row",
            ),
            id="portfolio-screen",
        )

    async def on_mount(self, event: events.Mount) -> None:
        # Fetch account data in the background so the dialog appears immediately
        asyncio.create_task(self._reload_account_data())
        asyncio.create_task(self._refresh_orders())

        self.query_one("#trade-amount-input", Input).value = (
            f"{self.trade_amount}" if self.trade_amount else ""
        )

        # schedule auto-refresh of the orders
        self._refresh_job = self.set_interval(
            self.REFRESH_SECS, self._refresh_orders, pause=False
        )
        # periodic balance updates for equity graph
        self._balance_job = self.set_interval(
            self.REFRESH_SECS, self._reload_account_data, pause=False
        )

    async def on_unmount(self, event: events.Unmount) -> None:
        # cancel the refresher when the dialog closes
        if self._refresh_job:
            self._refresh_job.stop()
            self._refresh_job = None
        if self._balance_job:
            self._balance_job.stop()
            self._balance_job = None

    async def _reload_account_data(self):
        """Refresh balance metrics and positions using callbacks."""
        if callable(self.balance_callback):
            info = await asyncio.to_thread(self.balance_callback)
            if info:
                self.cash = info.get("cash", 0.0)
                self.buying_power = info.get("buying_power", 0.0)
                self.portfolio_value = info.get("portfolio_value", 0.0)
                self.app._portfolio_balance_cache = info
                self._has_cached_balance = True

        if callable(self.positions_callback):
            try:
                self.positions = await asyncio.to_thread(self.positions_callback) or []
                self.app._portfolio_positions_cache = self.positions
                self._has_cached_positions = True
            except Exception:
                log.warning("Failed to fetch positions")
                self.positions = []

        # update title
        top_title_widget = self.query_one("#portfolio-title", Static)
        acct = "LIVE" if self.real_trades else "PAPER"
        top_title_widget.update(
            f"** [b]{acct} ACCOUNT[/b] **\n"
            f"Cash: [green]${self.cash:,.2f}[/]\n"
            f"Buying Power: [cyan]${self.buying_power:,.2f}[/]\n"
            f"Portfolio Value: [cyan]${self.portfolio_value:,.2f}[/]",
        )
        self.equity_view.add_point(self.cash, self.portfolio_value)

        # refresh holdings table
        self.holdings_table.clear()
        for pos in self.positions:
            cost = getattr(pos, "cost_basis", None)
            if cost is None:
                try:
                    cost = float(pos.qty) * float(pos.avg_entry_price)
                except Exception:
                    cost = 0.0
            profit = float(pos.market_value) - float(cost) if cost else 0.0
            self.holdings_table.add_row(
                pos.symbol,
                pos.qty,
                pos.market_value,
                cost,
                profit,
            )
        self.holdings_table.scroll_home()

    async def _refresh_orders(self):
        log.debug("Refreshing orders")

        orders = None
        try:
            log.debug("Fetching orders...")
            orders = await asyncio.to_thread(self.orders_callback, self.real_trades)
        except Exception:
            log.warning("Account orders fetch failed! get_all_orders()")
            top_title_widget = self.query_one("#portfolio-title", Static)
            top_title_widget.update(
                "[b]ACCOUNT ACCESS FAILED![/b]"
            )

        if orders:
            log.debug(f"Order History fetched.")
            orders.sort(key=self._order_date, reverse=True)
            table = self.query_one("#orders-table", DataTable)
            table.clear()
            for order in orders:
                print(f"Order: {order}")
                price = (
                        getattr(order, "filled_avg_price", None)
                        or getattr(order, "limit_price", None)
                        or getattr(order, "price", None)
                        or 0.0
                )
                try:
                    value = float(order.qty) * float(price)
                except Exception:
                    value = 0.0

                # Determine a readable timestamp
                dt = (
                        getattr(order, "submitted_at", None)
                        or getattr(order, "created_at", None)
                        or getattr(order, "filled_at", None)
                )
                if hasattr(dt, "strftime"):
                    dt_str = dt.strftime("%Y-%m-%d %H:%M")
                else:
                    dt_str = str(dt) if dt else ""

                table.add_row(
                        dt_str,
                    order.symbol,
                    order.side,
                    order.qty,
                    value,
                    order.order_type,
                    order.status,
                    "Cancel" if self._is_cancelable(order.status.name) else "",
                    order.id,
                )
            table.scroll_home()
            self.app._portfolio_orders_cache = orders
            self._has_cached_orders = True

    async def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "trade-mode-switch":
            self.real_trades = event.value
            if callable(self._set_real_trades_cb):
                self._set_real_trades_cb(event.value)
            # Switching accounts should start a fresh equity curve
            self.equity_view.reset()
            await self._reload_account_data()
            await self._refresh_orders()
        elif event.switch.id == "auto-trade-switch":
            self.auto_trading_enabled = event.value
            if callable(self._set_auto_trading_cb):
                self._set_auto_trading_cb(event.value)

    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "trade-amount-input":
            try:
                self.trade_amount = float(event.value)
            except ValueError:
                self.trade_amount = 0.0
            if callable(self._set_trade_amount_cb):
                self._set_trade_amount_cb(self.trade_amount)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "trade-amount-input":
            event.input.blur()

    async def on_data_table_row_selected(
            self,
            event: DataTable.RowSelected,
    ) -> None:
        """Open an order dialog to sell when a holdings row is clicked."""
        table_id = event.data_table.id
        log.debug(f"Row selected in table {table_id}: {event.row_key}")
        if event.data_table.id not in ["holdings-table"]:
            return

        symbol = None
        try:
            if table_id == "holdings-table":
                symbol = str(event.data_table.get_cell(event.row_key, self.holdings_table_columns[0])).strip().upper()
        except CellDoesNotExist:
            log.debug("Selected row no longer exists")
            return
        if not symbol or symbol.upper() == "LOADING...":
            log.debug("No valid symbol selected, ignoring...")
            return

        self.app.open_order_dialog(OrderSide.SELL, 100.0, symbol, None)

    async def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        """Handle cancel button clicks in the orders table."""
        if event.data_table.id != "orders-table":
            return
        if event.cell_key.column_key != self._cancel_col:
            return

        order_id = str(event.data_table.get_cell(event.cell_key.row_key, self._order_id_col))
        cell_val = event.value
        if str(cell_val).lower() != "cancel" or not order_id:
            return

        if callable(self._cancel_order_cb):
            await asyncio.to_thread(self._cancel_order_cb, order_id)
            await self._refresh_orders()

    @staticmethod
    def _order_date(order):
        """Return the best available timestamp for sorting orders."""
        return (
            getattr(order, "created_at", None)
            or getattr(order, "submitted_at", None)
            or getattr(order, "updated_at", None)
            or getattr(order, "filled_at", None)
            or getattr(order, "canceled_at", None)
        )

    @staticmethod
    def _is_cancelable(status: str) -> bool:
        """Return True if an order with this status can be cancelled."""
        status = str(status).lower()
        not_cancelable = {
            "filled",
            "canceled",
            "replaced",
            "expired",
            "rejected",
            "done_for_day",
        }
        return status not in not_cancelable

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "setup-button":
            result = await self.app.push_screen(SetupConfirmDialog(), wait_for_dismiss=True)
            if result:
                setup = SetupApp()
                setup.run()
        elif event.button.id == "close-button":
            self.app.pop_screen()
