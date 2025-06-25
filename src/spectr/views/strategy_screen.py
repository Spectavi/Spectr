from datetime import datetime
import inspect

from textual.screen import Screen
from textual.widgets import DataTable, Header, Footer, Static, Select
from textual.containers import Vertical
from textual.reactive import reactive

from rich.syntax import Syntax

from ..strategies import load_strategy

class StrategyScreen(Screen):
    """Modal screen listing live strategy signals."""
    BINDINGS = [
        ("s", "app.pop_screen", "Back"),
        ("escape", "app.pop_screen", "Back"),
    ]

    signals: reactive[list] = reactive([])

    def __init__(self, signals: list[dict], strategies: list[str], current: str, callback=None):
        super().__init__()
        self.signals = signals
        self.strategy_names = strategies
        self.current = current
        self.callback = callback
        self.code_str = self._get_strategy_code(current)

    def _get_strategy_code(self, name: str) -> str:
        """Return the source code of detect_signals for *name* strategy."""
        try:
            cls = load_strategy(name)
            func = getattr(cls, "detect_signals")
            return inspect.getsource(func)
        except Exception as exc:  # pragma: no cover - best effort
            return f"Unable to load strategy code: {exc}"

    def compose(self):
        table = DataTable(zebra_stripes=True, id="signals-table")
        table.add_columns(
            "Date/Time",
            "Symbol",
            "Side",
            "Price",
            "Reason",
            "Strategy",
            "Order Status",
        )
        for sig in sorted(
            self.signals,
            key=lambda r: r.get("time") or datetime.min,
            reverse=True,
        ):
            dt_raw = sig.get("time")
            dt = dt_raw.strftime("%Y-%m-%d %H:%M") if dt_raw else ""
            price = sig.get("price")
            table.add_row(
                dt,
                sig.get("symbol", ""),
                sig.get("side", "").upper(),
                f"{price:.2f}" if price is not None else "",
                sig.get("reason", ""),
                sig.get("strategy", ""),
                sig.get("order_status", ""),
            )

        select = Select(
            id="strategy-select",
            prompt="Strategy",
            value=self.current,
            options=[(name, name) for name in self.strategy_names],
        )
        self.code_widget = Static(
            Syntax(self.code_str, "python"), id="strategy-code"
        )
        yield Vertical(
            Static("Strategy Info", id="strategy-title"),
            select,
            table,
            self.code_widget,
            id="strategy-screen",
        )

    async def on_select_changed(self, event: Select.Changed):
        if event.select.id == "strategy-select":
            self.current = event.value
            self.code_str = self._get_strategy_code(self.current)
            self.code_widget.update(Syntax(self.code_str, "python"))
            if callable(self.callback):
                self.callback(event.value)
