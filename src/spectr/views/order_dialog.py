# order_dialog.py  (replace the previous version)

from __future__ import annotations

import logging

from textual.screen import ModalScreen
from textual.widgets import Static, Input, Button, Label
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual import events


log = logging.getLogger(__name__)

class OrderDialog(ModalScreen):
    """Pop-up order ticket that displays live price and current position."""

    BINDINGS = [
        ("enter", "submit", "SELL"),
        ("enter", "submit", "BUY"),
        ("escape", "app.pop_screen",  "Cancel"),
    ]

    REFRESH_SECS = 10          # how often to poll the quote

    class Submit(Message):
        def __init__(self, sender, *, symbol: str, side: str,
                     price: float, qty: float, total: float) -> None:
            super().__init__()
            self.symbol = symbol
            self.side   = side
            self.price  = price
            self.qty    = qty
            self.total  = total

    # live-reactive fields (UI updates automatically on change)
    qty    = reactive(0)
    price  = reactive(0.0)
    total  = reactive(0.0)


    def __init__(
        self,
        side: str,
        symbol:   str,
        pos_pct: float,
        get_pos_cb,
        get_price_cb,                     # async () -> float
    ) -> None:
        """
        `get_price_cb` must be an **async** callable that returns the latest
        quote price for `symbol` (e.g. `self.get_live_quote` from SpectrApp).
        """
        super().__init__()

        self.side         = side  # "BUY" / "SELL"
        self.symbol       = symbol.upper()
        self.pos_pct      = pos_pct
        self.get_pos      = get_pos_cb
        self.pos_qty      = 0.00
        self.pos_value    = 0.00
        self._get_price   = get_price_cb
        self._refresh_job = None                  # handle for cancel


    def compose(self):
        yield Vertical(
            Static(f"[b]{self.side} {self.symbol}[/b]", id="dlg_title"),
            Static(),
            Static(self._price_fmt(),               id="dlg_price"),
            Static(self._pos_fmt(),                 id="dlg_pos"),
            Horizontal(Label("", id="empty_line_lbl"), id="empty_line"),
            Horizontal(
                Label("Qty:", id="dlg_qty_lbl"),
                Input(placeholder="0", id="dlg_qty_in"),
            ),
            Static(self._total_fmt(), id="dlg_total"),
            Horizontal(
                Button(self.side, id="dlg_ok", variant="success"),
                Button("Cancel", id="dlg_cancel", variant="error"),
            ),
            id="dlg_body",
        )

    def _price_fmt(self) -> str:
        if self.price <= 0:
            return "Price: [red]N/A[/] (fetching quote...)"
        else:
            return f"Price: [green]${self.price:,.2f}[/]  (auto-updates)"

    def _pos_fmt(self) -> str:
        if self.pos_qty > 0:
            return f"Current position: [cyan]{self.pos_qty}[/] @ [cyan]${self.pos_value}[/]"
        else:
            return f"Current position: [yellow]NO POSITION[/]"

    def _total_fmt(self) -> str:
        return f"Order total: [yellow]${self.total:,.2f}[/]"

    async def on_mount(self, event: events.Mount) -> None:
        qty_input = self.query_one("#dlg_qty_in", Input)
        qty_input.focus()

        pos = self.get_pos(self.symbol)
        if pos:
            self.pos_qty = pos.qty
            self.pos_value = pos.market_value
        log.debug(f"pos_qty: {self.pos_qty}")
        log.debug(f"pos_value: {self.pos_value}")
        self.query_one("#dlg_pos", Static).update(self._pos_fmt())
        if self.side.upper() == "SELL":
            if pos:
                self.qty = float(self.pos_qty) * self.pos_pct
                qty_input.value = str(self.qty)

        self.price = self._get_price(self.symbol)['price']
        self.total = self.qty * self.price
        self.query_one("#dlg_total", Static).update(self._total_fmt())
        # schedule auto-refresh of the quote
        self._refresh_job = self.set_interval(
            self.REFRESH_SECS, self._refresh_price, pause=False
        )

    async def on_unmount(self, event: events.Unmount) -> None:
        # cancel the refresher when the dialog closes
        self._refresh_job.stop()
        self._refresh_job = None


    async def _refresh_price(self):
        if not self.is_mounted:
            return

        #with contextlib.suppress(Exception):   # network hiccups → ignore
        new_price = self._get_price(self.symbol).get("ask")
        log.debug(f"New ask price: {new_price}")
        if new_price:
            self.price = new_price
            self.query_one("#dlg_price", Static).update(self._price_fmt())
            # keep total in sync if user already typed a qty
            self.total = self.qty * self.price
            self.query_one("#dlg_total", Static).update(self._total_fmt())

    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "dlg_qty_in":
            try:
                self.qty = float(event.value)
            except ValueError:
                self.qty = 0
            self.total = self.qty * self.price
            self.query_one("#dlg_total", Static).update(self._total_fmt())

    def on_input_submitted(self, event: Input.Submitted):
        self.action_submit()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "dlg_ok":
            self.action_submit()
        else:
            self.app.pop_screen()

    def action_submit(self) -> None:
        self.post_message(
            self.Submit(
                self,
                symbol=self.symbol,
                side=self.side,
                price=self.price,
                qty=self.qty,
                total=self.total,
            )
        )
        self.app.pop_screen()
