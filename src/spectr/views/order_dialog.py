from __future__ import annotations

from fetch.broker_interface import OrderType, OrderSide

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
        pos_pct: float,
        get_pos_cb: Callable,
        get_price_cb: Callable,
    ) -> None:
        super().__init__()
        self.side         = side
        self.symbol       = symbol.upper()
        self.pos_pct      = pos_pct
        self._get_pos      = get_pos_cb
        self._get_price   = get_price_cb
        self._refresh_job = None

        self.pos_qty   = None
        self.pos_value = None

    # ------------------------------------------------------------------
    def compose(self):
        yield Vertical(
            Static(f"[b]{self.side.name.upper()} {self.symbol}[/b]", id="dlg_title"),
            Static(),
            Static(self._price_fmt(),  id="dlg_price"),
            Static(self._pos_fmt(),    id="dlg_pos"),
            Static(),
            Horizontal(
                Label("Type:", id="dlg_ot_lbl"),
                Select(
                    id="dlg_ot_sel",
                    prompt="Select",
                    value=self.order_type,
                    options=[(ot.name.replace("_", " "), ot.name) for ot in OrderType],
                ),
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
            ),
            id="dlg_body",
        )

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
            return f"Market Order total: [yellow]${self.qty * self.price:,.2f}[/]"
        elif self.order_type == OrderType.LIMIT.name:
            return f"Limit Order total: [yellow]${self.qty * self.limit_price:,.2f}[/]"
        return f"Order total: [yellow]${self.total:,.2f}[/]"

    # ------------------------------------------------------------------
    async def on_mount(self, event: events.Mount):
        qty_in = self.query_one("#dlg_qty_in", Input)
        qty_in.focus()

        # hide limit row initially
        self.query_one("#lim_row").display = False

        # Start disabled until position updates with a position to sell.
        # TODO: Add check for funds and disable BUY button if insufficient funds.
        if self.side == OrderSide.SELL:
            self.query_one("#dlg_ok", Button).disabled = True

        # start quote refresher
        self._refresh_job = self.set_interval(self.REFRESH_SECS, self._refresh_data)

    async def on_unmount(self, event: events.Unmount):
        if self._refresh_job:
            self._refresh_job.stop()
            self._refresh_job = None

    # ---------------- event handlers ----------------------------------
    async def _refresh_data(self):
        pos = self._get_pos(self.symbol)
        if pos:
            log.debug(f"Position for {self.symbol}: {pos}")
            self.pos_qty   = float(pos.qty)
            self.pos_value = float(pos.market_value)
            if self.side.name.upper() == "SELL":
                self.qty = self.pos_qty * self.pos_pct
                self.query_one("#dlg_qty_in", Input).value = str(self.qty)
        else:
            self.query_one("#dlg_ok", Button).disabled = True
        self.query_one("#dlg_pos", Static).update(self._pos_fmt())

        new_price = self._get_price(self.symbol).get("price", 0)
        if new_price:
            self.price = new_price
            self.query_one("#dlg_price", Static).update(self._price_fmt())
            if self.order_type == OrderType.MARKET.name:
                # Update total if it's a market order
                self.total = self.qty * self.price
                self.query_one("#dlg_total", Static).update(self._total_fmt())
            elif self.order_type == OrderType.LIMIT.name:
                # Update total if it's a limit order
                self.total = self.qty * self.limit_price
                self.query_one("#dlg_total", Static).update(self._total_fmt())
            self.query_one("#dlg_total", Static).update(self._total_fmt())

    async def on_select_changed(self, event: Select.Changed):
        if event.select.id == "dlg_ot_sel":
            self.order_type = event.value
            limit_row = self.query_one("#lim_row")
            limit_row.display = self.order_type != OrderType.MARKET.name
        self.query_one("#dlg_total", Static).update(self._total_fmt())

    async def on_input_changed(self, event: Input.Changed):
        if event.input.id == "dlg_qty_in":
            try:
                self.qty = float(event.value)
            except ValueError:
                self.qty = 0
            self.total = self.qty * self.price
        elif event.input.id == "dlg_lim_in":
            try:
                self.limit_price = float(event.value)
            except ValueError:
                self.limit_price = 0.0
        self.query_one("#dlg_total", Static).update(self._total_fmt())

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "dlg_ok":
            self.action_submit()
        else:
            self.app.pop_screen()

    def action_submit(self):
        self.post_message(
            self.Submit(
                self,
                symbol=self.symbol,
                side=self.side,
                price=self.price,
                qty=self.qty,
                total=self.total,
                order_type=self.order_type,
                limit_price=self.limit_price if self.order_type == OrderType.LIMIT.name else None,
            )
        )
        self.app.pop_screen()
