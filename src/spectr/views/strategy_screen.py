from datetime import datetime
import sys
import importlib
import pathlib
import black

from textual import events
from textual.screen import Screen
from textual.widgets import DataTable, Static, Select, TextArea, Button
from textual.widget import Widget
from textual.containers import Vertical, VerticalScroll, Horizontal
from textual.reactive import reactive


class StrategyScreen(Screen):
    """Modal screen listing live strategy signals."""

    BINDINGS = [
        ("s", "app.pop_screen", "Back"),
        ("escape", "app.pop_screen", "Back"),
    ]

    signals: reactive[list] = reactive([])

    def __init__(
        self, signals: list[dict], strategies: list[str], current: str, callback=None
    ):
        super().__init__()
        self.signals = signals
        self.strategy_names = strategies
        self.current = current
        self.callback = callback
        self.file_path = self._get_strategy_file(current)
        self.code_str = self.file_path.read_text(encoding="utf-8")

    def _get_strategy_file(self, name: str) -> pathlib.Path:
        """Return the path to the strategy module for ``name``."""
        strategies_dir = pathlib.Path(__file__).resolve().parents[1] / "strategies"
        for path in strategies_dir.glob("*.py"):
            if path.stem in {"__init__", "trading_strategy", "metrics"}:
                continue
            try:
                if f"class {name}" in path.read_text(encoding="utf-8"):
                    return path
            except Exception:
                continue
        raise FileNotFoundError(f"Unable to locate file for strategy {name}")

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
            prompt="",
            value=self.current,
            options=[(name, name) for name in self.strategy_names],
        )
        try:
            self.code_widget = TextArea(
                self.code_str,
                language="python",
                theme="monokai",
                show_line_numbers=True,
                id="strategy-code-content",
            )
        except Exception:
            self.code_widget = TextArea(
                self.code_str,
                language=None,
                theme="monokai",
                show_line_numbers=True,
                id="strategy-code-content",
            )
        toolbar = Horizontal(
            Button("Undo", id="strategy-undo"),
            Button("Redo", id="strategy-redo"),
            Button("Indent", id="strategy-indent"),
            Button("Outdent", id="strategy-outdent"),
            Button("Format", id="strategy-format"),
            Button("Save", id="strategy-save", variant="success"),
            Button("Activate", id="strategy-activate", variant="primary"),
            Button("Deactivate", id="strategy-deactivate", variant="warning"),
            id="strategy-toolbar",
        )
        code_scroll = VerticalScroll(self.code_widget, id="strategy-code")
        yield Vertical(
            Static("Strategy Info", id="strategy-title"),
            select,
            table,
            Static("", id="strategy-spacer"),
            toolbar,
            code_scroll,
            id="strategy-screen",
        )

    async def on_mount(self, event: events.Mount) -> None:
        if hasattr(self.app, "update_status_bar"):
            self.app.update_status_bar()
        overlay = getattr(self.app, "overlay", None)
        if isinstance(overlay, Widget):
            if overlay.parent:
                await overlay.remove()
            await self.mount(overlay, before=0)
        # Focus the strategy selector so users can immediately change strategies
        self.query_one("#strategy-select", Select).focus()

    async def on_select_changed(self, event: Select.Changed):
        if event.select.id == "strategy-select":
            self.current = event.value
            self.file_path = self._get_strategy_file(self.current)
            self.code_str = self.file_path.read_text(encoding="utf-8")
            self.code_widget.text = self.code_str
            try:
                self.code_widget.language = "python"
            except Exception:
                self.code_widget.language = None
            event.select.blur()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "strategy-undo":
            self.code_widget.undo()
        elif event.button.id == "strategy-redo":
            self.code_widget.redo()
        elif event.button.id == "strategy-indent":
            self._indent_selection()
        elif event.button.id == "strategy-outdent":
            self._indent_selection(outdent=True)
        elif event.button.id == "strategy-format":
            self._format_code()
        elif event.button.id == "strategy-save":
            await self._save_strategy()
        elif event.button.id == "strategy-activate":
            if callable(self.callback):
                self.callback(self.current)
            if hasattr(self.app, "set_strategy_active"):
                self.app.set_strategy_active(True)
                self.app.overlay.flash_message(
                    "Strategy activated",
                    duration=3.0,
                    style="bold green",
                )
        elif event.button.id == "strategy-deactivate":
            if hasattr(self.app, "set_strategy_active"):
                self.app.set_strategy_active(False)
                self.app.overlay.flash_message(
                    "Strategy deactivated",
                    duration=3.0,
                    style="bold yellow",
                )

    async def _save_strategy(self) -> None:
        """Write edits to disk and reload the strategy."""
        try:
            self.file_path.write_text(self.code_widget.text, encoding="utf-8")
            module_name = f"spectr.strategies.{self.file_path.stem}"
            if module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
            else:
                importlib.import_module(module_name)
            if callable(self.callback):
                self.callback(self.current)
            self.app.overlay.flash_message(
                "Strategy saved", duration=3.0, style="bold green"
            )
        except Exception as exc:  # pragma: no cover - best effort
            self.app.overlay.flash_message(
                f"Error saving: {exc}", duration=5.0, style="bold red"
            )

    def _indent_selection(self, outdent: bool = False) -> None:
        """Indent or outdent the currently selected lines."""
        widget = self.code_widget
        indent = " " * widget.indent_width
        start, end = sorted(widget.selection)
        start_line = start[0]
        end_line = end[0]
        if end[1] == 0 and end_line > start_line:
            end_line -= 1
        for line_no in range(start_line, end_line + 1):
            line = widget.document.get_line(line_no)
            if outdent:
                if line.startswith("\t"):
                    new_line = line[1:]
                elif line.startswith(indent):
                    new_line = line[len(indent) :]
                else:
                    prefix = len(line) - len(line.lstrip())
                    new_line = line[min(prefix, len(indent)) :]
            else:
                new_line = indent + line
            widget.replace(new_line, (line_no, 0), (line_no, len(line)))

    def _format_code(self) -> None:
        """Format the entire code block using Black."""
        try:
            formatted = black.format_str(self.code_widget.text, mode=black.FileMode())
        except Exception as exc:
            self.app.overlay.flash_message(
                f"Format error: {exc}", duration=5.0, style="bold red"
            )
            return
        if formatted != self.code_widget.text:
            self.code_widget.text = formatted
            self.app.overlay.flash_message(
                "Code formatted", duration=3.0, style="bold green"
            )

    async def on_unmount(self, event: events.Unmount) -> None:
        overlay = getattr(self.app, "overlay", None)
        if isinstance(overlay, Widget):
            if overlay.parent:
                await overlay.remove()
            if getattr(self.app, "_screen_stack", None):
                await self.app.mount(overlay, before=0)
