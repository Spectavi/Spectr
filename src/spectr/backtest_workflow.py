import asyncio
from datetime import datetime

import pandas as pd

from .backtest import split_backtest_frames
from .backtest_models import BacktestInput
from .service_modules.backtest_service import BacktestService
from .cache import save_last_backtest, attach_order_to_last_signal
from .config import ORDER_SUCCESS_SOUND_PATH
from .fetch.broker_interface import OrderSide
from .strategies import load_strategy
from .utils import get_historical_data, play_sound


class BacktestWorkflow:
    def __init__(self, app):
        self.app = app
        self._backtest_cancelled = False
        self._bt_skipping_updates = False
        self._last_backtest_trades = None

    async def run(self, symbol: str, from_date: str, to_date: str, cash: float, strategy_name: str) -> dict:
        """Run a backtest and return results."""
        self.app.is_backtest = True
        self._backtest_cancelled = False
        
        try:
            loading = BacktestLoadingScreen(message=f"Running backtest for {symbol}...")
            await self.app.push_screen(loading, wait_for_dismiss=False)
            
            overlay = self.app.overlay
            overlay.update_status("Running backtest...")
            
            strategy_cls = load_strategy(strategy_name)
            
            df, _ = await asyncio.to_thread(
                get_historical_data,
                self.app.data_api,
                self.app.config.bb_period,
                self.app.config.bb_dev,
                self.app.config.macd_thresh,
                symbol,
                from_date=from_date,
                to_date=to_date,
            )
            
            if df.empty:
                raise ValueError("No data returned for that period.")
            
            self._validate_data_range(df, from_date, to_date)
            
            report = await asyncio.to_thread(
                BacktestService().run,
                BacktestInput(
                    df=df,
                    symbol=symbol,
                    config=self.app.config,
                    strategy_class=strategy_cls,
                    starting_cash=float(cash),
                    start_date=from_date,
                    end_date=to_date,
                ),
            )
            
            if self._backtest_cancelled:
                self.app.is_backtest = False
                return {}
            
            return self._process_results(report, symbol, from_date, to_date, strategy_name, float(cash))
            
        except Exception as exc:
            await self._handle_error(exc)
            return {}

    def _validate_data_range(self, df: pd.DataFrame, requested_from: str, requested_to: str) -> None:
        """Validate that data covers the requested date range."""
        data_index = df.index
        data_from = _coerce_timestamp_to_index(data_index.min(), data_index)
        data_to = _coerce_timestamp_to_index(data_index.max(), data_index)
        req_from = _coerce_timestamp_to_index(requested_from, data_index)
        req_to = _coerce_timestamp_to_index(requested_to, data_index)

        covers = data_from.date() <= req_from.date() and data_to.date() >= req_to.date()
        
        if not covers:
            tolerance = req_from + pd.Timedelta(days=1)
            if data_from.date() <= tolerance.date():
                import logging
                logging.warning(
                    f"Data starts later than requested ({requested_from}→{requested_to}) "
                    f"but within 1-day tolerance; proceeding."
                )
            else:
                raise ValueError(
                    f"Data available {data_from} → {data_to} does not cover "
                    f"requested range {req_from} → {req_to}"
                )

    def _process_results(self, report, symbol, from_date, to_date, strategy_name, cash):
        """Process backtest results and prepare for display."""
        num_buys = len(report.buy_signals)
        num_sells = len(report.sell_signals)
        self._last_backtest_trades = report.trades
        
        equity_serialized = []
        for ts, val in self._get_equity_items(report.equity_curve):
            iso_val = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            equity_serialized.append({"time": iso_val, "value": float(val)})
        
        graph_df = self._prepare_graph_data(graph_df=split_backtest_frames(report)[1])
        
        save_last_backtest({
            "symbol": symbol,
            "from": from_date,
            "to": to_date,
            "strategy": strategy_name,
            "starting_cash": cash,
            "final_value": report.end_value,
            "num_buys": num_buys,
            "num_sells": num_sells,
            "trades": self._serialize_trades(report.trades),
            "equity_curve": equity_serialized,
            "config": self.app.config.__dict__,
        })
        
        return {
            "report": report,
            "graph_df": graph_df,
            "buys": num_buys,
            "sells": num_sells,
        }

    def _get_equity_items(self, equity_curve):
        """Extract items from equity curve data."""
        if isinstance(equity_curve, pd.Series):
            return equity_curve.items()
        elif isinstance(equity_curve, pd.DataFrame):
            return [(ts, row.iloc[-1]) for ts, row in equity_curve.iterrows()]
        elif isinstance(equity_curve, list):
            return enumerate(equity_curve)
        return []

    def _prepare_graph_data(self, graph_df):
        """Add buy/sell signals to graph dataframe."""
        buy_times = {sig["time"] for sig in self.app._last_backtest_trades.get("buy_signals", [])}
        sell_times = {sig["time"] for sig in self.app._last_backtest_trades.get("sell_signals", [])}
        
        if hasattr(graph_df, "index"):
            graph_df["buy_signals"] = graph_df.index.isin(buy_times)
            graph_df["sell_signals"] = graph_df.index.isin(sell_times)
        
        return graph_df

    def _serialize_trades(self, trades):
        """Serialize trades for caching."""
        result = []
        for trade in trades:
            entry = {**trade}
            if "time" in entry:
                entry["time"] = entry["time"].isoformat() if hasattr(entry["time"], "isoformat") else str(entry["time"])
            result.append(entry)
        return result

    async def _handle_error(self, exc: Exception) -> None:
        """Handle backtest errors gracefully."""
        try:
            if self.app.screen_stack and isinstance(
                self.app.screen_stack[-1], BacktestLoadingScreen
            ):
                await self.app.pop_screen()
        except Exception:
            pass
        
        import logging
        logging.exception("Back-test error")
        
        try:
            await self.app.push_screen(BacktestErrorScreen(f"Backtest failed:\n{exc}"))
        except Exception:
            self.app.overlay.flash_message(f"Back-test error: {exc}", style="bold red")
        
        self.app.is_backtest = False

    def cancel(self) -> None:
        """Cancel in-flight backtest."""
        self._backtest_cancelled = True
        
        try:
            if self.app.screen_stack and isinstance(
                self.app.screen_stack[-1], BacktestLoadingScreen
            ):
                self.app.pop_screen()
        except Exception:
            pass
        
        self.app.is_backtest = False

    def exit_backtest(self) -> None:
        """Exit backtest mode and restore live view."""
        if not self.app.is_backtest:
            return
        
        self.app.is_backtest = False
        self._restore_symbol_view()
        
        current = self.app._get_active_symbol()
        if current:
            self.app.update_view(current)

    def _restore_symbol_view(self) -> None:
        """Ensure SymbolView exists and is properly configured."""
        try:
            sv = self.app.query_one("#symbol-view", SymbolView)
        except Exception:
            sv = None
        
        if sv is None:
            try:
                self.app.mount(SymbolView(id="symbol-view"))
                sv = self.app.query_one("#symbol-view", SymbolView)
            except Exception:
                return
        
        self.app.symbol_view = sv
        
        if sv and getattr(sv, "graph", None):
            sv.graph.is_backtest = False
        if sv and getattr(sv, "macd", None):
            sv.macd.is_backtest = False
