from typing import Optional
from types import SimpleNamespace

from textual.screen import ModalScreen
from textual.widgets import Static, Button, Switch, Input, DataTable
from textual.containers import Vertical, Horizontal, Container
from textual import events
from textual.reactive import reactive

import asyncio
import logging
import pandas as pd

from ..fetch.broker_interface import OrderSide
from .equity_curve_view import EquityCurveView
from .. import cache

log = logging.getLogger(__name__)


class PortfolioPanel(Vertical):
    """Panel that shows cash, invested value, and current holdings."""

    REFRESH_SECS = 10

    positions = reactive(list)
    cash = reactive(0.0)
    buying_power = reactive(0.0)
    portfolio_value = reactive(0.0)
    real_trades = reactive(False)
    trade_amount = reactive(0.0)
    afterhours_enabled = reactive(True)

    def __init__(
        self,
        cash: Optional[float] = None,
        buying_power: Optional[float] = None,
        portfolio_value: Optional[float] = None,
        positions: Optional[list] = None,
        orders: Optional[list] = None,
        orders_callback=None,
        cancel_order_callback=None,
        real_trades: bool = False,
        set_real_trades_cb=None,
        disable_live_switch: bool = False,
        hide_live_switch: bool = False,
        auto_trading: bool = False,
        set_auto_trading_cb=None,
        afterhours_enabled: bool = True,
        set_afterhours_cb=None,
        balance_callback=None,
        positions_callback=None,
        equity_data: Optional[list] = None,
        trade_amount: float = 0.0,
        set_trade_amount_cb=None,
    ):
        super().__init__()
        self.cash = cash or 0.0
        self.buying_power = buying_power or 0.0
        self.portfolio_value = portfolio_value or 0.0
        self.positions = positions or []
        self.cached_orders = orders or []
        if isinstance(self.cached_orders, pd.DataFrame):
            if not self.cached_orders.empty:
                self.cached_orders = [
                    SimpleNamespace(**rec)
                    for rec in self.cached_orders.to_dict(orient="records")
                ]
            else:
                self.cached_orders = []
        if self.cached_orders:
            self.cached_orders.sort(key=self._order_date, reverse=True)
        self.real_trades = real_trades
        self.disable_live_switch = disable_live_switch
        self.hide_live_switch = hide_live_switch
        self._has_cached_balance = cash is not None
        self._has_cached_positions = positions is not None
        self._has_cached_orders = bool(self.cached_orders)
        self._set_real_trades_cb = set_real_trades_cb
        self.auto_trading_enabled = auto_trading
        self._set_auto_trading_cb = set_auto_trading_cb
        self.afterhours_enabled = afterhours_enabled
        self._set_afterhours_cb = set_afterhours_cb
        self._cancel_order_cb = cancel_order_callback
        self.trade_amount = trade_amount
        self._set_trade_amount_cb = set_trade_amount_cb
        self.top_title = Static(id="portfolio-title")
        self.equity_view = EquityCurveView(id="equity-curve")
        self.holdings_table = DataTable(zebra_stripes=True, id="holdings-table")
        self.holdings_table_columns = self.holdings_table.add_columns(
            "Symbol",
            "Qty",
            "Value",
            "Ask Value",
            "Bid Value",
            "Avg Cost",
            "Profit",
        )
        self.holdings_table.cursor_type = "row"
        self.holdings_table.show_cursor = True
        self.order_table = DataTable(zebra_stripes=True, id="orders-table")
        self.order_table_columns = self.order_table.add_columns(
            "Date/Time",
            "Symbol",
            "Side",
            "Qty",
            "Value",
            "Type",
            "Reason",
            "Status",
            "Cancel?",
            "Order ID",
        )
        self._cancel_col = self.order_table_columns[-2]
        self._order_id_col = self.order_table_columns[-1]
        self.order_table.cursor_type = "cell"
        self.order_table.show_cursor = True
        self.mode_switch = Switch(value=self.real_trades, id="trade-mode-switch")
        self.mode_switch.disabled = self.disable_live_switch
        self.auto_switch = Switch(
            value=self.auto_trading_enabled, id="auto-trade-switch"
        )
        self.afterhours_switch = Switch(
            value=self.afterhours_enabled, id="afterhours-switch"
        )
        self.orders_callback = orders_callback
        self.balance_callback = balance_callback
        self.positions_callback = positions_callback
        self._refresh_job = None
        self._balance_job = None

        if equity_data:
            self.equity_view.data = list(equity_data)

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
                    0.0,
                    0.0,
                    cost,
                    profit,
                    key=pos.symbol,
                )
        else:
            self.holdings_table.add_row("Loading...", "", "", "", "", "", "")

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

                order_id = getattr(order, "id", None)
                short_id = f"{str(order_id)[:4]}..." if order_id else ""
                reason = self._get_order_reason(order_id)
                self.order_table.add_row(
                    dt_str,
                    order.symbol,
                    order.side,
                    order.qty,
                    value,
                    order.order_type,
                    reason,
                    order.status,
                    (
                        "Cancel"
                        if self._is_cancelable(
                            getattr(order.status, "name", order.status)
                        )
                        else ""
                    ),
                    short_id,
                    key=order_id,
                )
        else:
            self.order_table.add_row("Loading...", "", "", "", "", "", "", "", "", "")

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
                    Static("Auto Trades"), self.auto_switch, id="trade-switch-container"
                ),
                Container(
                    Static("Afterhours"),
                    self.afterhours_switch,
                    id="afterhours-switch-container",
                ),
                id="trade-mode-container",
            ),
            Horizontal(Static("Trade Amount $"), id="trade-amount-row"),
            Input(id="trade-amount-input", placeholder="0.00"),
            Static("Holdings:", id="holdings-title"),
            self.holdings_table,
            Static("Order History:", id="orders-title"),
            self.order_table,
            Horizontal(
                Button("Setup", id="setup-button"),
                id="portfolio_buttons_row",
            ),
            id="portfolio-panel",
        )

    async def on_mount(self, event: events.Mount) -> None:
        if hasattr(self.app, "update_status_bar"):
            self.app.update_status_bar()
        asyncio.create_task(self._reload_account_data())
        asyncio.create_task(self._refresh_orders())

        self.query_one("#trade-amount-input", Input).value = (
            f"{self.trade_amount}" if self.trade_amount else ""
        )

        self._refresh_job = self.set_interval(
            self.REFRESH_SECS, self._refresh_orders, pause=False
        )
        self._balance_job = self.set_interval(
            self.REFRESH_SECS, self._reload_account_data, pause=False
        )

    async def on_unmount(self, event: events.Unmount) -> None:
        if self._refresh_job:
            self._refresh_job.stop()
            self._refresh_job = None
        if self._balance_job:
            self._balance_job.stop()
            self._balance_job = None

    async def _reload_account_data(self):
        if callable(self.balance_callback):
            info = await asyncio.to_thread(self.balance_callback)
            if info:
                self.cash = info.get("cash", 0.0)
                self.buying_power = info.get("buying_power", 0.0)
                self.portfolio_value = info.get("portfolio_value", 0.0)
                self.app._portfolio_balance_cache = info
                if hasattr(self.app, "_sync_store_portfolio"):
                    self.app._sync_store_portfolio()
                self._has_cached_balance = True

        if callable(self.positions_callback):
            try:
                self.positions = await asyncio.to_thread(self.positions_callback) or []
                self.app._portfolio_positions_cache = self.positions
                if hasattr(self.app, "_sync_store_portfolio"):
                    self.app._sync_store_portfolio()
                self._has_cached_positions = True
            except Exception:
                log.warning("Failed to fetch positions")
                self.positions = []

        top_title_widget = self.query_one("#portfolio-title", Static)
        acct = "LIVE" if self.real_trades else "PAPER"
        top_title_widget.update(
            f"** [b]{acct} ACCOUNT[/b] **\n"
            f"Cash: [green]${self.cash:,.2f}[/]\n"
            f"Buying Power: [cyan]${self.buying_power:,.2f}[/]\n"
            f"Portfolio Value: [cyan]${self.portfolio_value:,.2f}[/]",
        )
        self.equity_view.add_point(self.cash, self.portfolio_value)

        table = self.holdings_table
        broker = getattr(self.app, "broker_api", None)

        current_keys = {pos.symbol for pos in self.positions}
        existing_keys = set(table.rows.keys())

        for row_key in existing_keys - current_keys:
            table.remove_row(row_key)

        for pos in self.positions:
            cost = getattr(pos, "cost_basis", None)
            if cost is None:
                try:
                    cost = float(pos.qty) * float(pos.avg_entry_price)
                except Exception:
                    cost = 0.0
            profit = float(pos.market_value) - float(cost) if cost else 0.0
            quote = {}
            if broker is not None:
                quote = await asyncio.to_thread(broker.fetch_quote, pos.symbol)
            ask_price = (
                quote.get("ask")
                or quote.get("ask_price")
                or quote.get("askPrice")
                or quote.get("price")
                or 0.0
            )
            bid_price = (
                quote.get("bid")
                or quote.get("bid_price")
                or quote.get("bidPrice")
                or quote.get("price")
                or 0.0
            )
            ask_value = float(pos.qty) * float(ask_price) if ask_price else 0.0
            bid_value = float(pos.qty) * float(bid_price) if bid_price else 0.0

            if pos.symbol not in existing_keys:
                table.add_row(
                    pos.symbol,
                    pos.qty,
                    pos.market_value,
                    ask_value,
                    bid_value,
                    cost,
                    profit,
                    key=pos.symbol,
                )
            else:
                table.update_cell(pos.symbol, self.holdings_table_columns[1], pos.qty)
                table.update_cell(
                    pos.symbol, self.holdings_table_columns[2], pos.market_value
                )
                table.update_cell(pos.symbol, self.holdings_table_columns[3], ask_value)
                table.update_cell(pos.symbol, self.holdings_table_columns[4], bid_value)
                table.update_cell(pos.symbol, self.holdings_table_columns[5], cost)
                table.update_cell(pos.symbol, self.holdings_table_columns[6], profit)
                row_index = table.get_row_index(pos.symbol)
                table.refresh_row(row_index)
        table.scroll_home()

    async def _refresh_orders(self):
        log.debug("Refreshing orders")

        orders = None
        try:
            log.debug("Fetching orders...")
            orders = await asyncio.to_thread(self.orders_callback, self.real_trades)
        except Exception:
            log.warning("Account orders fetch failed! get_all_orders()")
            top_title_widget = self.query_one("#portfolio-title", Static)
            top_title_widget.update("[b]ACCOUNT ACCESS FAILED![/b]")
        if isinstance(orders, pd.DataFrame):
            if not orders.empty:
                orders = [
                    SimpleNamespace(**rec) for rec in orders.to_dict(orient="records")
                ]
            else:
                orders = []

        if orders:
            log.debug(f"Order History fetched.")
            orders.sort(key=self._order_date, reverse=True)
            cache.update_order_statuses(self.app.strategy_signals, orders)
            table = self.query_one("#orders-table", DataTable)
            table.clear()
            for order in orders:
                log.debug(f"Order: {order}")
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

                order_id = getattr(order, "id", None)
                short_id = f"{str(order_id)[:4]}..." if order_id else ""
                reason = self._get_order_reason(order_id)
                table.add_row(
                    dt_str,
                    order.symbol,
                    order.side,
                    order.qty,
                    value,
                    order.order_type,
                    reason,
                    order.status,
                    (
                        "Cancel"
                        if self._is_cancelable(
                            getattr(order.status, "name", order.status)
                        )
                        else ""
                    ),
                    short_id,
                    key=order_id,
                )
            table.scroll_home()
            self.app._portfolio_orders_cache = orders
            if hasattr(self.app, "_sync_store_portfolio"):
                self.app._sync_store_portfolio()
            self._has_cached_orders = True

    async def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "trade-mode-switch":
            self.real_trades = event.value
            if callable(self._set_real_trades_cb):
                self._set_real_trades_cb(event.value)
            self.equity_view.reset()
            await self._reload_account_data()
            await self._refresh_orders()
            if self.auto_trading_enabled:
                self.auto_trading_enabled = False
                self.auto_switch.value = False
                if callable(self._set_auto_trading_cb):
                    self._set_auto_trading_cb(False)
        elif event.switch.id == "auto-trade-switch":
            self.auto_trading_enabled = event.value
            if callable(self._set_auto_trading_cb):
                self._set_auto_trading_cb(event.value)
        elif event.switch.id == "afterhours-switch":
            self.afterhours_enabled = event.value
            if callable(self._set_afterhours_cb):
                self._set_afterhours_cb(event.value)

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

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "setup-button":
            self.app.pop_screen()

    def _get_order_reason(self, order_id):
        if not order_id:
            return ""
        app = getattr(self, "app", None)
        if app is None or not hasattr(app, "strategy_signals"):
            return ""
        for rec in reversed(app.strategy_signals):
            rec_id = rec.get("order_id")
            if rec_id is not None and str(rec_id) == str(order_id):
                return str(rec.get("reason", ""))
        return ""

    @staticmethod
    def _order_date(order):
        return (
            getattr(order, "created_at", None)
            or getattr(order, "submitted_at", None)
            or getattr(order, "updated_at", None)
            or getattr(order, "filled_at", None)
            or getattr(order, "canceled_at", None)
        )

    @staticmethod
    def _is_cancelable(status: str) -> bool:
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


class SettingsDialog(ModalScreen):
    """Modal dialog with sidebar navigation for Portfolio and Settings."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
    ]

    def __init__(
        self,
        cash: Optional[float] = None,
        buying_power: Optional[float] = None,
        portfolio_value: Optional[float] = None,
        positions: Optional[list] = None,
        orders: Optional[list] = None,
        orders_callback=None,
        cancel_order_callback=None,
        real_trades: bool = False,
        set_real_trades_cb=None,
        disable_live_switch: bool = False,
        hide_live_switch: bool = False,
        auto_trading: bool = False,
        set_auto_trading_cb=None,
        afterhours_enabled: bool = True,
        set_afterhours_cb=None,
        balance_callback=None,
        positions_callback=None,
        equity_data: Optional[list] = None,
        trade_amount: float = 0.0,
        set_trade_amount_cb=None,
    ):
        super().__init__()
        self.portfolio_kwargs = {
            "cash": cash,
            "buying_power": buying_power,
            "portfolio_value": portfolio_value,
            "positions": positions,
            "orders": orders,
            "orders_callback": orders_callback,
            "cancel_order_callback": cancel_order_callback,
            "real_trades": real_trades,
            "set_real_trades_cb": set_real_trades_cb,
            "disable_live_switch": disable_live_switch,
            "hide_live_switch": hide_live_switch,
            "auto_trading": auto_trading,
            "set_auto_trading_cb": set_auto_trading_cb,
            "afterhours_enabled": afterhours_enabled,
            "set_afterhours_cb": set_afterhours_cb,
            "balance_callback": balance_callback,
            "positions_callback": positions_callback,
            "equity_data": equity_data,
            "trade_amount": trade_amount,
            "set_trade_amount_cb": set_trade_amount_cb,
        }
        
        # Create portfolio panel once and reuse it
        self._portfolio_panel = PortfolioPanel(**self.portfolio_kwargs)

    def compose(self):
        yield Horizontal(
            Vertical(
                Button("Portfolio", id="sidebar-portfolio", variant="primary"),
                id="settings-sidebar",
            ),
            Container(id="settings-content"),
            Button("×", id="close-button"),
            id="settings-dialog",
        )

    def on_mount(self) -> None:
        close_btn = self.query_one("#close-button")
        close_btn.styles.margin = ("12px", "0px", "0px", "auto")
        close_btn.styles.padding = (0, 8)
        close_btn.styles.width = 3
        close_btn.background = "#da3633"
        close_btn.color = "#ffffff"
        self.show_portfolio()

    def show_portfolio(self):
        content = self.query_one("#settings-content", Container)
        content.remove_children()
        # Mount the existing portfolio panel instead of creating new one
        content.mount(self._portfolio_panel)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-button":
            self.app.pop_screen()
