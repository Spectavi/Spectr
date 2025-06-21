from __future__ import annotations

from ..fetch.broker_interface import OrderType, OrderSide

"""OrderDialog with dynamic Limit‑Price field.
Shows a limit‑price input only when the user picks OrderType.LIMIT.
"""

import logging
from typing import Callable, Any

from textual.screen import ModalScreen
from textual.widgets import Static, Input, Button, Label, Select
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual import events

log = logging.getLogger(__name__)

class OrderDialog(ModalScreen):
    """Interactive order ticket.

    * Dynamically shows a *Limit Price* input when the user picks **LIMIT**.
    * Emits a ``Submit`` message with all parameters (including `limit_price`).
    * Auto‑refreshes the quote every ``REFRESH_SECS`` seconds.
    """

    BINDINGS = [
        ("enter", "submit", "SUBMIT"),
        ("escape", "app.pop_screen", "Cancel"),
    ]

    REFRESH_SECS = 10

    # ---------------- message -----------------------------------------
    class Submit(Message):
        def __init__(
            self,
            sender: "OrderDialog",
            *,
            symbol: str,
            side: OrderSide,
            price: float,
            qty: float,
            total: float,
            order_type: OrderType,
            limit_price: float | None,
        ) -> None:
            super().__init__()
            self.symbol = symbol
            self.side = side
            self.price = price
            self.qty = qty
            self.total = total
            self.order_type = order_type
            self.limit_price = limit_price

    # ---------------- reactive fields --------------------------------
    qty          = reactive(0.0)
    price        = reactive(0.0)
    total        = reactive(0.0)
    order_type   = reactive(OrderType.MARKET.name)
    limit_price  = reactive(0.0)

    # ------------------------------------------------------------------
    def __init__(
        self,
        *,
        side: OrderSide,
        symbol: str,
        pos_pct: float = 100.0,
        get_pos_cb: Callable,
        get_price_cb: Callable,
        trade_amount: float = 0.0,
        reason: str | None = None,
        default_order_type: OrderType = OrderType.MARKET,
        default_limit_price: float | None = None,
    ) -> None:
        super().__init__()
        self.side         = side
        self.symbol       = symbol.upper()
        self.pos_pct      = pos_pct
        self._get_pos      = get_pos_cb
        self._get_price   = get_price_cb
        self.trade_amount = trade_amount
        self.reason       = reason
        self._refresh_job = None

        self.order_type  = default_order_type.name
        self.limit_price = default_limit_price or 0.0

        self.pos_qty   = None
        self.pos_value = None

        # Tracks if the user has manually changed the qty so we don't
        # overwrite their choice on subsequent refreshes.
        self._qty_modified = False

    # ------------------------------------------------------------------
    def compose(self):
        components = [
            Static(f"[b]{self.side.name.upper()} {self.symbol}[/b]", id="dlg_title")
        ]
        if self.reason:
            components.append(Static(self.reason, id="dlg_reason"))
        components += [
            Static(),
            Static(self._price_fmt(), id="dlg_price"),
            Static(self._pos_fmt(), id="dlg_pos"),
            Static(),
            Horizontal(
                Label("Type:", id="dlg_ot_lbl"),
                Select(
                    id="dlg_ot_sel",
                    prompt="Select",
                    value=self.order_type,
                    options=[(ot.name.replace("_", " "), ot.name) for ot in OrderType],
                ),
                id="dlg_ot_row",
            ),
            Horizontal(
                Label("Qty:", id="dlg_qty_lbl"),
                Input(placeholder="0", id="dlg_qty_in"),
            ),
            # Limit price row (hidden by default)
            Horizontal(
                Label("Limit $:", id="dlg_lim_lbl"),
                Input(placeholder="0.00", id="dlg_lim_in"),
                id="lim_row",
            ),
            Static(self._total_fmt(), id="dlg_total"),
            Horizontal(
                Button(self.side.name.upper(), id="dlg_ok", variant="success"),
                Button("Cancel", id="dlg_cancel", variant="error"),
                id="dlg_buttons_row",
            ),
        ]

        yield Vertical(*components, id="dlg_body")

    # ---------------- private helpers ---------------------------------
    def _price_fmt(self) -> str:
        return (
            f"Price: [green]${self.price:,.2f}[/]  (auto-updates every {self.REFRESH_SECS} secs)"
            if self.price > 0
            else "Price: [red]N/A[/] (fetching)"
        )

    def _pos_fmt(self) -> str:
        if self.pos_qty is None or self.pos_value is None:
            return "Current position: [red]N/A[/] (fetching)"
        return (
            f"Current position: [cyan]{self.pos_qty}[/] @ [cyan]${self.pos_value}[/]"
            if self.pos_qty > 0
            else "Current position: [yellow]NO POSITION![/]"
        )

    def _total_fmt(self) -> str:
        if self.order_type == OrderType.MARKET.name:
            return f"Market Order total: [yellow]${self.total:,.2f}[/]"
        elif self.order_type == OrderType.LIMIT.name:
            return f"Limit Order total: [yellow]${self.total:,.2f}[/]"

    def _update_total(self) -> None:
        """Recalculate and update the total based on the current order type."""
        if self.order_type == OrderType.MARKET.name:
            self.total = self.qty * self.price
        else:
            self.total = self.qty * self.limit_price
        self.query_one("#dlg_total", Static).update(self._total_fmt())

    # ------------------------------------------------------------------
    async def on_mount(self, event: events.Mount):
        qty_in = self.query_one("#dlg_qty_in", Input)
        qty_in.focus()

        # show or hide limit price row based on default order type
        limit_row = self.query_one("#lim_row")
        limit_row.display = self.order_type != OrderType.MARKET.name
        if self.order_type != OrderType.MARKET.name and self.limit_price:
            self.query_one("#dlg_lim_in", Input).value = str(self.limit_price)

        # Start disabled until position updates with a position to sell.
        # TODO: Add check for funds and disable BUY button if insufficient funds.
        if self.side == OrderSide.SELL:
            self.query_one("#dlg_ok", Button).disabled = True

        # start quote refresher
        await self._refresh_data(is_initial_load=True)
        self._refresh_job = self.set_interval(self.REFRESH_SECS, self._refresh_data)

    async def on_unmount(self, event: events.Unmount):
        if self._refresh_job:
            self._refresh_job.stop()
            self._refresh_job = None

    # ---------------- event handlers ----------------------------------
    async def _refresh_data(self, is_initial_load: bool = False):
        # Check position first to see if it's changed. Only update qty input field if it's the initial load.
        pos = self._get_pos(self.symbol)
        if pos:
            log.debug(f"Position for {self.symbol}: {pos}")
            self.query_one("#dlg_ok", Button).disabled = False
            self.pos_qty   = float(pos.qty)
            self.pos_value = float(pos.market_value)
            if self.side == OrderSide.SELL and self.pos_pct > 0:
                self.qty = self.pos_qty * (self.pos_pct / 100.0)
                qty_input = self.query_one("#dlg_qty_in", Input)
                if is_initial_load:
                    qty_input.value = str(self.qty)
        else:
            # When there's no position on the symbol, keep the BUY button
            # active and show "NO POSITION" instead of "N/A".
            if self.side == OrderSide.SELL:
                self.query_one("#dlg_ok", Button).disabled = True
            else:
                self.query_one("#dlg_ok", Button).disabled = False
            self.pos_qty = 0
            self.pos_value = 0.0
        self.query_one("#dlg_pos", Static).update(self._pos_fmt())

        new_price = self._get_price(self.symbol)
        if new_price:
            new_price = new_price.get("price", 0)
            self.price = new_price
            self.query_one("#dlg_price", Static).update(self._price_fmt())
            if (
                    self.side == OrderSide.BUY
                    and self.trade_amount > 0
                    and self.price > 0
                    and not self._qty_modified
            ):
                self.qty = self.trade_amount / self.price
                self.query_one("#dlg_qty_in", Input).value = str(self.qty)
            self._update_total()

    async def on_select_changed(self, event: Select.Changed):
        if event.select.id == "dlg_ot_sel":
            self.order_type = event.value
            limit_row = self.query_one("#lim_row")
            limit_row.display = self.order_type != OrderType.MARKET.name
        self._update_total()

    async def on_input_changed(self, event: Input.Changed):
        if event.input.id == "dlg_qty_in":
            try:
                self.qty = float(event.value)
            except ValueError:
                self.qty = 0
            else:
                self._qty_modified = True
        elif event.input.id == "dlg_lim_in":
            try:
                self.limit_price = float(event.value)
            except ValueError:
                self.limit_price = 0.0
        self._update_total()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "dlg_ok":
            self.action_submit()
        else:
            self.app.pop_screen()

    def action_submit(self):
        """Emit a :class:`Submit` message with the proper ``OrderType`` enum."""

        order_type_enum = OrderType[self.order_type]

        self.post_message(
            self.Submit(
                self,
                symbol=self.symbol,
                side=self.side,
                price=self.price,
                qty=self.qty,
                total=self.total,
                order_type=order_type_enum,
                limit_price=self.limit_price if order_type_enum == OrderType.LIMIT else None,
            )
        )
        self.app.pop_screen()
