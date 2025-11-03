import logging
import asyncio
from types import SimpleNamespace
import pandas as pd
from textual.screen import ModalScreen
from textual.widgets import Static, DataTable
from textual.containers import Vertical

from .backtest_graph_view import BacktestGraphView


log = logging.getLogger(__name__)


class BacktestResultScreen(ModalScreen):
    """Screen displaying the back‑test graph and summary metrics."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
    ]

    def __init__(
        self,
        df: pd.DataFrame,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
        start_value: float,
        end_value: float,
        num_buys: int,
        num_sells: int,
        trades: list[dict],
        args_snapshot: object | None = None,
    ) -> None:
        super().__init__()
        self._graph: GraphView | None = None
        self._df = df
        self.report = Static(id="backtest-report")
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.start_value = start_value
        self.end_value = end_value
        self.num_buys = num_buys
        self.num_sells = num_sells
        self.trades = trades
        self._args_snapshot = args_snapshot

    def compose(self):
        log.debug("BacktestResultScreen.compose")
        self._graph = BacktestGraphView(id="backtest-graph")
        self.report.update(self._make_report())
        table = DataTable(id="backtest-trades", zebra_stripes=True)
        table.styles.height = 10
        table.add_columns(
            "Date/Time",
            "Signal",
            "Price",
            "Quantity",
            "Value",
            "Profit",
            "Reason",
        )

        # Compute per-sell realized profit using equity deltas since last buy
        last_buy_value = None
        for trade in self.trades:
            # Format timestamp
            t = trade.get("time")
            if hasattr(t, "strftime"):
                ts = t.strftime("%Y-%m-%d %H:%M:%S")
            else:
                ts = str(t) if t is not None else "—"

            typ = str(trade.get("type", "")).upper()
            price = trade.get("price")
            qty = trade.get("quantity", 0)
            value = trade.get("value")

            price_s = f"${price:.2f}" if price is not None else "—"
            qty_s = f"{qty:.4f}" if qty is not None else "—"
            value_s = f"${value:.2f}" if value is not None else "—"

            profit_s = "—"
            if typ == "BUY":
                last_buy_value = value if value is not None else last_buy_value
            elif typ == "SELL":
                if value is not None and last_buy_value is not None:
                    profit = float(value) - float(last_buy_value)
                    profit_s = f"${profit:.2f}"
                # Reset last_buy_value after a sell
                last_buy_value = None

            table.add_row(
                ts,
                typ,
                price_s,
                qty_s,
                value_s,
                profit_s,
                trade.get("reason", ""),
            )
        yield Vertical(self._graph, self.report, table, id="backtest-result-container")

    async def on_mount(self) -> None:
        log.debug("BacktestResultScreen mounted")
        # Keep backtest mode while visible
        try:
            self.app.is_backtest = True
        except Exception:
            pass
        # Snapshot args to decouple from live view toggles
        try:
            args_obj = self._args_snapshot or getattr(self.app, "args", None)
            bt_args = SimpleNamespace(**vars(args_obj)) if args_obj else SimpleNamespace(scale=1.0)
        except Exception:
            bt_args = SimpleNamespace(scale=1.0)

        # Prepare and load the graph
        try:
            self._graph.update_symbol(self.symbol)
        except Exception:
            self._graph.symbol = self.symbol
        self._graph.load_df(self._df, bt_args, indicators=[])

        # Allow layout to compute final size, then render once and freeze
        # BacktestGraphView self-freezes after its first render.

    async def on_unmount(self) -> None:
        log.debug("BacktestResultScreen unmounted")
        # Leave backtest mode and restore the live view state
        try:
            # Prefer the app helper that resets child widgets as needed
            if hasattr(self.app, "_exit_backtest"):
                self.app._exit_backtest()
            else:
                self.app.is_backtest = False
        except Exception:
            pass

    def _make_report(self) -> str:
        # Compute Buy & Hold profit using the price series in the backtest range
        buy_hold_line = "Buy & Hold: —"
        try:
            s = self._df["close"].dropna() if isinstance(self._df, pd.DataFrame) else None
            if s is not None and not s.empty and self.start_value is not None:
                start_px = float(s.iloc[0])
                end_px = float(s.iloc[-1])
                if start_px > 0:
                    shares = float(self.start_value) / start_px
                    bh_end_value = shares * end_px
                    bh_profit = bh_end_value - float(self.start_value)
                    sign = "+" if bh_profit > 0 else ("-" if bh_profit < 0 else "")
                    buy_hold_line = f"Buy & Hold: {sign}${abs(bh_profit):,.2f}"
        except Exception:
            # Leave placeholder on error
            pass

        return (
            f"Symbol: {self.symbol}\n"
            f"From: {self.start_date}\n"
            f"To: {self.end_date}\n"
            f"Start Value: ${self.start_value:,.2f}\n"
            f"End Value: ${self.end_value:,.2f}\n"
            f"{buy_hold_line}\n"
            f"Buys: {self.num_buys}\n"
            f"Sells: {self.num_sells}"
        )
