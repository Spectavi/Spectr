import argparse
import asyncio
import contextlib
import logging
import os
import json
import pathlib
import time
import queue
import threading
import traceback
from datetime import datetime, timedelta

import backtrader as bt
import pandas as pd
from dotenv import load_dotenv
from textual.app import App, ComposeResult
from textual.reactive import reactive

import metrics
import utils
from custom_strategy import CustomStrategy
#from CustomStrategy import CustomStrategy
from fetch.broker_interface import BrokerInterface, OrderSide, OrderType
from utils import play_sound, get_historical_data, get_live_data
from views.backtest_input_dialog import BacktestInputDialog
from views.backtest_result_screen import BacktestResultScreen
from views.order_dialog import OrderDialog
from views.portfolio_screen import PortfolioScreen
from views.splash_screen import SplashScreen
from views.symbol_view import SymbolView
from views.ticker_input_dialog import TickerInputDialog
from views.top_overlay import TopOverlay
from views.trades_screen import TradesScreen
from views.strategy_screen import StrategyScreen



# Notes for scanner filter:
# - Already up 5%?
# - 4x relative volume.
# - News catalyst within the last 48 hrs.
# - < 10mill float?
# - Between $1.00 and $50.00?
# - Volume > 50k?

# Show how long it was since last scan. TTS


# --- SOUND PATHS ---
BUY_SOUND_PATH = 'res/buy.mp3'
SELL_SOUND_PATH = 'res/sell.mp3'

REFRESH_INTERVAL = 60  # seconds
SCANNER_INTERVAL = REFRESH_INTERVAL
EQUITY_INTERVAL = 30  # portfolio equity update frequency

# Setup logging to file
log_path = "debug.log"
logging.basicConfig(
    filename=log_path,
    filemode="w",
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


class OrderSignal:
    """A simple class to hold order signals."""
    def __init__(self, symbol: str, side: OrderSide, pos_pct: float = 100.0):
        self.symbol = symbol
        self.side = side
        self.pos_pct = pos_pct

# --- Backtest Function ---
class CommInfoFractional(bt.CommissionInfo):
    def getsize(self, price, cash):
        """Returns fractional size for cash operation @price"""
        return self.p.leverage * (cash / price)


class SpectrApp(App):
    CSS_PATH = "default.tcss"
    BINDINGS = [
        ("escape", "quit", "Quit"),
        ("t", "prompt_symbol", "Change Ticker"),  # T key
        ("`", "prompt_symbol", "Change Ticker"),  # ~ key
        ("ctrl+a", "arm_auto_trading", "Arms Auto-Trading - REAL trades will occur!"),
        ("ctrl+q", "buy_current_symbol", "Opens buy dialog for current symbol."),
        ("ctrl+z", "sell_current_symbol", "Opens sell dialog for current symbol, set to 100% of position"),
        ("ctrl+x", "sell_half_current_symbol", "Opens sell dialog for current symbol, set to 50% of position"),
        ("ctrl+c", "sell_quarter_current_symbol", "Opens sell dialog for current symbol, set to 25% of position"),
        ("1", "select_symbol('1')", "Symbol 1"),
        ("2", "select_symbol('2')", "Symbol 2"),
        ("3", "select_symbol('3')", "Symbol 3"),
        ("4", "select_symbol('4')", "Symbol 4"),
        ("5", "select_symbol('5')", "Symbol 5"),
        ("6", "select_symbol('6')", "Symbol 6"),
        ("7", "select_symbol('7')", "Symbol 7"),
        ("8", "select_symbol('8')", "Symbol 8"),
        ("9", "select_symbol('9')", "Symbol 9"),
        ("0", "select_symbol('0')", "Symbol 10"),
        ("=", "next_symbol", "Next Symbol"),  # + key
        ("-", "prev_symbol", "Previous Symbol"),
        ("b", "prompt_backtest", "Back-test"),
        ("tab", "toggle_trades", "Trades Table"),
        ("p", "toggle_portfolio", "Portfolio"),
        ("s", "toggle_strategy_signals", "Strategy Signals"),
    ]

    ticker_symbols = reactive([])
    active_symbol_index = reactive(0)
    auto_trading_enabled: reactive[bool] = reactive(False)
    is_backtest: reactive[bool] = reactive(False)
    trade_amount: reactive[float] = reactive(0.0)

    symbol_view: reactive[SymbolView] = reactive(None)

    def _is_splash_active(self) -> bool:
        """Return ``True`` if the splash screen is currently visible."""
        return bool(self.screen_stack and isinstance(self.screen_stack[-1], SplashScreen))

    def _prepend_open_positions(self) -> None:
        """Ensure open position symbols are at the start of ``ticker_symbols``."""
        try:
            positions = BROKER_API.get_positions()
        except Exception as exc:
            log.warning(f"Failed to fetch open positions: {exc}")
            return

        owned = []
        for pos in positions or []:
            sym = getattr(pos, "symbol", None)
            if sym:
                sym = sym.upper()
                if sym not in owned:
                    owned.append(sym)

        if not owned:
            return

        # remove any owned symbols already present in the list
        remaining = [s for s in self.ticker_symbols if s.upper() not in owned]

        self.ticker_symbols = owned + remaining

    def __init__(self, args):
        super().__init__()
        if not hasattr(self, "exit_event"):
            self.exit_event = asyncio.Event()
        self._consumer_task = None
        self.args = args  # Store CLI arguments
        self._sig_lock = threading.Lock()  # protects self.signal_detected
        self._poll_worker = None
        self._scanner_worker = None
        self._equity_worker = None
        self.macd_thresh = self.args.macd_thresh
        self.bb_period = self.args.bb_period
        self.bb_dev = self.args.bb_dev
        self.df_cache = {symbol: pd.DataFrame() for symbol in self.ticker_symbols}
        if not os.path.exists(utils.CACHE_DIR):
            os.mkdir(utils.CACHE_DIR)

        self._update_queue: queue.Queue[str] = queue.Queue()
        self.signal_detected = []
        self.strategy_signals: list[dict] = []
        self._shutting_down = False

        self.trade_amount = 0.0

        self._scanner_cache_file = pathlib.Path.home() / ".spectr_scanner_cache.json"
        self.scanner_results: list[dict] = self._load_scanner_cache()
        self._gainers_cache_file = pathlib.Path.home() / ".spectr_gainers_cache.json"
        self.top_gainers: list[dict] = self._load_gainers_cache()

        # Track latest quotes and equity curve
        self._latest_quotes: dict[str, float] = {}
        self._equity_curve_data: list[tuple[datetime, float, float]] = []

        # Cache for portfolio data so reopening the portfolio screen is instant
        self._portfolio_balance_cache: dict | None = None
        self._portfolio_positions_cache: list | None = None
        self._portfolio_orders_cache: list | None = None

    def compose(self) -> ComposeResult:
        yield TopOverlay(id="overlay-text")
        yield SymbolView(id="symbol-view")

    async def on_mount(self):
        # Show splash screen without waiting for it to close
        self.push_screen(SplashScreen())
        # Set symbols and active symbol
        self.ticker_symbols = self.args.symbols
        # Ensure any open positions are at the start of the watchlist.
        self._prepend_open_positions()
        self.args.symbols = self.ticker_symbols
        self.active_symbol_index = 0

        log.debug(f"self.ticker_symbols: {self.ticker_symbols}")
        log.debug("App mounted.")

        # Kick off background workers
        self._poll_worker = self.run_worker(self._polling_loop, thread=False)
        self._scanner_worker = self.run_worker(self._scanner_loop, thread=False)
        self._equity_worker = self.run_worker(self._equity_loop, thread=False)

        self.update_status_bar()
        if self.args.broker == "robinhood" and self.args.real_trades:
            self.query_one("#overlay-text", TopOverlay).flash_message(
                "Robinhood does NOT support PAPER TRADING!", style="bold red"
            )
        log.debug("starting consumer task")
        self._consumer_task = asyncio.create_task(self._process_updates())



    def _poll_one_symbol(self, symbol: str):
        try:
            log.debug(f"Fetching live data for {symbol}...")
            df, quote = get_live_data(DATA_API, symbol)
            if df.empty or quote is None:
                return

            price = quote.get("price")
            if price is not None:
                self._latest_quotes[symbol.upper()] = float(price)

            log.debug(f"Injecting quote for {symbol}")
            df = utils.inject_quote_into_df(df, quote)

            log.debug(f"Analyzing {symbol}...")
            df = metrics.analyze_indicators(
                df, self.bb_period, self.bb_dev, self.macd_thresh
            )
            df["trade"] = None
            df["signal"] = None

            signal_dict = CustomStrategy.detect_signals(
                df,
                symbol,
                position=BROKER_API.get_position(symbol),
            )
            log.debug("Detect signals finished.")

            # Check for signal
            if signal_dict and not self._is_splash_active():
                signal = signal_dict.get("signal")
                curr_price = quote.get("price")
                reason = signal_dict.get("reason")
                log.debug(f"Signal detected for {symbol}. Reason: {reason}")
                df.at[df.index[-1], 'trade'] = signal  # mark bar for plotting
                if signal == "buy":
                    log.debug("Buy signal detected!")
                    self.signal_detected.append((symbol, curr_price, signal, reason))
                    self.strategy_signals.append({
                        "time": datetime.now(),
                        "symbol": symbol,
                        "side": "buy",
                        "price": curr_price,
                        "reason": reason,
                    })
                    play_sound(BUY_SOUND_PATH)
                elif signal == "sell":
                    log.debug("Sell signal detected!")
                    self.signal_detected.append((symbol, curr_price, signal, reason))
                    self.strategy_signals.append({
                        "time": datetime.now(),
                        "symbol": symbol,
                        "side": "sell",
                        "price": curr_price,
                        "reason": reason,
                    })
                    play_sound(SELL_SOUND_PATH)

            # Notify UI thread
            self.df_cache[symbol] = df
            self._update_queue.put(symbol)
            if symbol == self.ticker_symbols[self.active_symbol_index]:
                if self.screen_stack and isinstance(self.screen_stack[-1], SplashScreen):
                    # schedule screen pop on the main thread – we are in an executor
                    self.call_from_thread(self.pop_screen)
                # refresh the active view from the UI thread
                self.call_from_thread(self.update_view, self.ticker_symbols[self.active_symbol_index])

        except Exception as exc:
            log.error(f"[poll] {symbol}: {traceback.format_exc()}")

    async def _polling_loop(self) -> None:
        """Poll all symbols at regular intervals."""
        if self.is_backtest:
            return

        log.debug("_polling_loop start")

        while not self.exit_event.is_set():
            tasks = [asyncio.to_thread(self._poll_one_symbol, sym) for sym in self.ticker_symbols]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            try:
                await asyncio.wait_for(self.exit_event.wait(), timeout=REFRESH_INTERVAL)
            except asyncio.TimeoutError:
                pass

        log.debug("_polling_loop exit")

    async def _process_updates(self) -> None:
        """Runs in Textual’s event loop; applies any fresh data to the UI."""
        log.debug("_process_updates start")
        while True:
            symbol: str = await asyncio.to_thread(self._update_queue.get)
            if symbol is None:
                log.debug("_process_updates exit")
                return
            # If the update is for the symbol the user is currently looking at,
            # push it straight into the Graph/MACD views.
            # If a buy signal was triggered, switch to that symbol
            if len(self.signal_detected) > 0:
                for signal in self.signal_detected:
                    sym, price, sig, reason = signal
                    index = self.ticker_symbols.index(sym)
                    self.active_symbol_index = index
                    msg = f"{sym} @ {price} 🚀"
                    if sig == 'buy':
                        msg = f"BUY {msg}"
                        side = OrderSide.BUY
                    if sig == 'sell':
                        msg = f"SELL {msg}"
                        side = OrderSide.SELL

                    if not self.auto_trading_enabled and sig:
                        self.signal_detected.remove(signal)
                        if (self.screen_stack and not isinstance(self.screen_stack[-1], OrderDialog)):
                            self.open_order_dialog(side=side, pos_pct=100.0, symbol=sym, reason=reason)
                        continue
                    else:
                        msg = f"ORDER SUBMITTED! {msg}"
                        if not self.args.real_trades:
                            msg = f"PAPER {msg}"
                        else:
                            msg = f"REAL {msg}"
                        self.signal_detected.remove(signal)
                        BROKER_API.submit_order(symbol, side, OrderType.MARKET, self.args.real_trades)
                        play_sound(BUY_SOUND_PATH if sig == "buy" else SELL_SOUND_PATH)
            elif symbol == self.ticker_symbols[self.active_symbol_index]:
                if not self.is_backtest:
                    df = self.df_cache.get(symbol)
                    if df is not None:
                        self.update_view(symbol)


    def _save_scanner_cache(self, rows: list[dict]) -> None:
        try:
            self._scanner_cache_file.write_text(json.dumps({"t": time.time(), "rows": rows}, indent=0))
        except Exception as exc:
            log.error(f"cache write failed: {exc}")

    def _save_gainers_cache(self, rows: list[dict]) -> None:
        try:
            self._gainers_cache_file.write_text(json.dumps({"t": time.time(), "rows": rows}, indent=0))
        except Exception as exc:
            log.error(f"gainers cache write failed: {exc}")

    def _load_scanner_cache(self) -> list[dict]:
        try:
            blob = json.loads(self._scanner_cache_file.read_text())
            if time.time() - blob.get("t", 0) > 900:
                return []
            return blob.get("rows", [])
        except Exception:
            return []

    def _load_gainers_cache(self) -> list[dict]:
        try:
            blob = json.loads(self._gainers_cache_file.read_text())
            if time.time() - blob.get("t", 0) > 900:
                return []
            return blob.get("rows", [])
        except Exception:
            return []

    def _check_scan_symbol(self, row):
        """Fetch extra metrics for *row* and flag if it passes the filter."""
        sym = row["symbol"]
        quote = DATA_API.fetch_quote(sym)
        if not quote:
            return None

        profile = {}
        if hasattr(DATA_API, "fetch_company_profile"):
            try:
                profile = DATA_API.fetch_company_profile(sym) or {}
            except Exception:
                profile = {}

        prev = quote.get("previousClose") or 0

        avg_vol = quote.get("avgVolume") or profile.get("volAvg") or 0
        volume = quote.get("volume") or 0
        float_shares = (
            profile.get("float")
            or profile.get("floatShares")
            or quote.get("sharesOutstanding")
            or 0
        )

        rel_vol_pct = 100 * volume / avg_vol if avg_vol else 0

        passed = True
        if prev == 0 or (quote["price"] - prev) / prev < 0.05:
            passed = False
        if avg_vol == 0 or volume < 3 * avg_vol:
            passed = False
        if not DATA_API.has_recent_positive_news(sym, hours=48):
            passed = False

        return {
            **row,
            "open_price": quote["price"] - quote["change"],
            "avg_volume": avg_vol,
            "volume_pct": rel_vol_pct,
            "float": float_shares,
            "passed": passed,
        }

    async def _run_scanner(self) -> list[dict]:
        if self.exit_event.is_set():
            return []

        gainers = DATA_API.fetch_top_movers(limit=50)
        if self.exit_event.is_set():
            return []

        tasks = [asyncio.to_thread(self._check_scan_symbol, row) for row in gainers]
        results = []
        for coro in asyncio.as_completed(tasks):
            if self.exit_event.is_set():
                break
            data = await coro
            if data is not None:
                results.append(data)

        self.top_gainers = results
        self._save_gainers_cache(results)
        return [r for r in results if r.get("passed")]

    async def _scanner_loop(self) -> None:
        log.debug("_scanner_loop start")
        self.scanner_results = self._load_scanner_cache()
        self.top_gainers = self._load_gainers_cache()
        while not self.exit_event.is_set():
            try:
                results = await self._run_scanner()
                self.scanner_results = results
                self._save_scanner_cache(results)
                if results:
                    try:
                        play_sound(BUY_SOUND_PATH)
                    except Exception as exc:
                        log.error(f"scan-sound failed: {exc}")
            except Exception as exc:
                log.error(f"[scanner] {exc}")

            try:
                await asyncio.wait_for(self.exit_event.wait(), timeout=SCANNER_INTERVAL)
            except asyncio.TimeoutError:
                pass

        log.debug("_scanner_loop exit")

    async def _equity_loop(self) -> None:
        """Periodically update portfolio equity using cached quotes."""
        log.debug("_equity_loop start")
        while not self.exit_event.is_set():
            try:
                self._update_portfolio_equity()
            except Exception as exc:
                log.error(f"[equity] {exc}")

            try:
                await asyncio.wait_for(self.exit_event.wait(), timeout=EQUITY_INTERVAL)
            except asyncio.TimeoutError:
                pass

        log.debug("_equity_loop exit")

    def _update_portfolio_equity(self) -> None:
        """Calculate portfolio value using cached quotes and record a point."""
        try:
            balance = BROKER_API.get_balance() or {}
            cash = balance.get("cash", 0.0)
        except Exception as exc:
            log.warning(f"Failed to fetch balance: {exc}")
            cash = 0.0
            balance = {}

        try:
            positions = BROKER_API.get_positions() or []
        except Exception as exc:
            log.warning(f"Failed to fetch positions: {exc}")
            positions = []

        total = cash
        for pos in positions:
            sym = getattr(pos, "symbol", "").upper()
            qty = float(getattr(pos, "qty", 0))
            price = self._latest_quotes.get(sym)
            if price is None:
                try:
                    q = DATA_API.fetch_quote(sym)
                    price = q.get("price") if q else None
                    if price is not None:
                        self._latest_quotes[sym] = float(price)
                except Exception:
                    price = None

            if price is not None:
                total += qty * float(price)
            else:
                mv = getattr(pos, "market_value", None)
                if mv is not None:
                    total += float(mv)

        self._portfolio_balance_cache = {
            "cash": cash,
            "buying_power": balance.get("buying_power", 0.0),
            "portfolio_value": total,
        }

        self._record_equity_point(cash, total)

    def _record_equity_point(self, cash: float, total: float) -> None:
        now = datetime.now()
        cutoff = now - timedelta(hours=4)
        self._equity_curve_data.append((now, cash, total))
        self._equity_curve_data = [d for d in self._equity_curve_data if d[0] >= cutoff]

        # Update any open portfolio screen
        if self.screen_stack and isinstance(self.screen_stack[-1], PortfolioScreen):
            screen = self.screen_stack[-1]
            screen.cash = cash
            screen.portfolio_value = total
            screen.equity_view.data = list(self._equity_curve_data)
            screen.equity_view.refresh()

    async def action_quit(self):
        """Handle the Escape key to quit the app."""
        log.debug("Escape key pressed, quitting app.")
        self.exit_event.set()

        log.debug("on_shutdown start")
        # tell every background task we are quitting
        self._exit_backtest()
        self.auto_trading_enabled = False
        self._shutting_down = True

        # Cancel workers
        if self._scanner_worker:
            log.debug("cancelling scanner worker")
            self._scanner_worker.cancel()
            self._scanner_worker = None

        if self._poll_worker:
            log.debug("cancelling poll worker")
            self._poll_worker.cancel()
            self._poll_worker = None

        if self._equity_worker:
            log.debug("cancelling equity worker")
            self._equity_worker.cancel()
            self._equity_worker = None

        if self._consumer_task:
            log.debug("cancelling consumer task")
            self._update_queue.put_nowait(None)
            self._consumer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                self._consumer_task = None

        log.debug("on_shutdown complete")
        self.exit()



    # ------------ Action Functions -------------

    def action_select_symbol(self, key: str):
        self._exit_backtest()
        index = (int(key) - 1) if key != "0" else 9

        if index <= len(self.ticker_symbols) - 1:
            self.active_symbol_index = index
            symbol = self.ticker_symbols[index]
            log.debug(f"action selected symbol: {symbol}")
            symbol = self.ticker_symbols[index]
            self.run_worker(self._poll_one_symbol, symbol, thread=True)
            if hasattr(self, "_poll_now"):
                self._poll_now.set()
            self.update_view(symbol)

    def action_prev_symbol(self):
        self._exit_backtest()
        new_index = self.active_symbol_index - 1
        if new_index < 0:
            new_index = len(self.ticker_symbols) - 1
        self.active_symbol_index = new_index
        symbol = self.ticker_symbols[new_index]
        self.run_worker(self._poll_one_symbol, symbol, thread=True)
        if hasattr(self, "_poll_now"):
            self._poll_now.set()
        self.update_view(symbol)

    def action_next_symbol(self):
        self._exit_backtest()
        new_index = self.active_symbol_index + 1
        if new_index > len(self.ticker_symbols) - 1:
            new_index = 0
        self.active_symbol_index = new_index
        symbol = self.ticker_symbols[new_index]
        self.run_worker(self._poll_one_symbol, symbol, thread=True)
        if hasattr(self, "_poll_now"):
            self._poll_now.set()
        self.update_view(symbol)



    # ------------- Order Dialog -------------

    def action_buy_current_symbol(self):
        if self._is_splash_active():
            return
        self._exit_backtest()
        symbol = self.ticker_symbols[self.active_symbol_index]
        self.open_order_dialog(OrderSide.BUY, 0.00, symbol)

    def action_sell_current_symbol(self):
        if self._is_splash_active():
            return
        self._exit_backtest()
        symbol = self.ticker_symbols[self.active_symbol_index]
        self.open_order_dialog(OrderSide.SELL, 100.0, symbol)

    def action_sell_half_current_symbol(self):
        if self._is_splash_active():
            return
        self._exit_backtest()
        symbol = self.ticker_symbols[self.active_symbol_index]
        self.open_order_dialog(OrderSide.SELL, 50.0, symbol)

    def action_sell_quarter_current_symbol(self):
        if self._is_splash_active():
            return
        self._exit_backtest()
        symbol = self.ticker_symbols[self.active_symbol_index]
        self.open_order_dialog(OrderSide.SELL, 25.0, symbol)

    def open_order_dialog(self, side: OrderSide, pos_pct: float, symbol: str, reason: str | None = None):
        if self._is_splash_active():
            return
        self.push_screen(
            OrderDialog(
                side=side,
                symbol=symbol,
                pos_pct=pos_pct,
                get_pos_cb=BROKER_API.get_position,
                get_price_cb=DATA_API.fetch_quote,
                trade_amount=self.trade_amount if side == OrderSide.BUY else 0.0,
                reason=reason,
            )
        )



    # ------------ Arm / Dis-arm -------------

    def action_arm_auto_trading(self):
        self.auto_trading_enabled = not self.auto_trading_enabled
        self.update_status_bar()



    # ------------ Select Ticker -------------

    def action_prompt_symbol(self):
        if self._is_splash_active():
            return
        self.auto_trading_enabled = False
        self.push_screen(
            TickerInputDialog(
                callback=self.on_ticker_submit,
                top_movers_cb=DATA_API.fetch_top_movers,
                quote_cb=DATA_API.fetch_quote,
                profile_cb=getattr(DATA_API, "fetch_company_profile", None),
                scanner_results=self.scanner_results,
                scanner_results_cb=lambda: self.scanner_results,
                gainers_results=self.top_gainers,
                gainers_results_cb=lambda: self.top_gainers,
            )
        )

    def on_ticker_submit(self, symbols: str):
        if (symbols):
            log.debug(f"on_ticker_submit: {symbols}")
            self.ticker_symbols = [x.strip().upper() for x in symbols.split(',')]
            self._prepend_open_positions()
            self.args.symbols = self.ticker_symbols
            log.debug(f"on_ticker_submit: {self.ticker_symbols}")
            self.active_symbol_index = 0
            symbol = self.ticker_symbols[self.active_symbol_index]

            self.run_worker(self._poll_one_symbol, symbol, thread=True)
            if hasattr(self, "_poll_now"):
                self._poll_now.set()
            self.update_view(symbol)

    def action_toggle_trades(self) -> None:
        if self._is_splash_active():
            return
        # Only meaningful after a back-test has just finished
        if getattr(self, "_last_backtest_trades", None):
            if self.screen_stack and isinstance(self.screen_stack[-1], TradesScreen):
                self.pop_screen()  # already open → close
            else:
                self.push_screen(TradesScreen(self._last_backtest_trades))

    def action_toggle_strategy_signals(self) -> None:
        if self._is_splash_active():
            return
        if self.screen_stack and isinstance(self.screen_stack[-1], StrategyScreen):
            self.pop_screen()
        else:
            self.push_screen(StrategyScreen(list(self.strategy_signals)))


    # ------------ Order Dialog Submit Logic -------------

    async def on_order_dialog_submit(self, msg: OrderDialog.Submit) -> None:
        """Receive the order details and route them to your broker layer."""
        log.info(
            f"Placing {msg.side} {msg.qty} {msg.symbol} @ ${msg.price:.2f} "
            f"(total ${msg.total:,.2f})"
        )
        try:
            BROKER_API.submit_order(
                symbol=msg.symbol,
                side=msg.side,
                type=msg.order_type,
                quantity=msg.qty,
            )
        except Exception as e:
            log.error(e)
            self.flash_message(f"{e.__str__()[:60]}")

        # mark the last bar so GraphView can plot the trade immediately
        symbol = msg.symbol.upper()
        df = self.df_cache.get(symbol)
        if df is not None and not df.empty:
            last_ts = df.index[-1]

            # add / update the helper columns used by GraphView
            if msg.side == OrderSide.BUY:
                if "buy_signals" not in df.columns: df["buy_signals"] = None
                df.at[last_ts, "buy_signals"] = True
            elif msg.side == OrderSide.SELL:
                if "sell_signals" not in df.columns: df["sell_signals"] = None
                df.at[last_ts, "sell_signals"] = True

            # cache the modified frame
            self.df_cache[symbol] = df

            # if the user is currently viewing that symbol, refresh the plot now
            if symbol == self.ticker_symbols[self.active_symbol_index]:
                self.update_view(symbol)

    # --------------

    def action_toggle_portfolio(self) -> None:
        if self._is_splash_active():
            return
        if self.screen_stack and isinstance(self.screen_stack[-1], PortfolioScreen):
            self.pop_screen()
        else:
            # Pull any cached portfolio data so the screen shows it immediately.
            balance = self._portfolio_balance_cache or {}
            cash = balance.get("cash") if balance else None
            buying_power = balance.get("buying_power") if balance else None
            portfolio_value = balance.get("portfolio_value") if balance else None

            positions = self._portfolio_positions_cache
            orders = self._portfolio_orders_cache

            # Open the portfolio screen immediately. If cached data exists it
            # will be displayed right away; otherwise placeholders are shown
            # while background tasks load the data.
            self.push_screen(
                PortfolioScreen(
                    cash,
                    buying_power,
                    portfolio_value,
                    positions,
                    orders,
                    BROKER_API.get_all_orders,
                    BROKER_API.cancel_order,
                    self.args.real_trades,
                    self.set_real_trades,
                    self.args.broker == "robinhood" and self.args.real_trades,
                    self.auto_trading_enabled,
                    self.set_auto_trading,
                    BROKER_API.get_balance,
                    BROKER_API.get_positions,
                    equity_data=self._equity_curve_data,
                    trade_amount=self.trade_amount,
                    set_trade_amount_cb=self.set_trade_amount,
                )
            )

    # --------------

    def update_view(self, symbol: str):
        self.query_one("#overlay-text", TopOverlay).symbol = symbol

        df = self.df_cache.get(symbol)
        if df is not None and not self.is_backtest:
            self.symbol_view = self.query_one("#symbol-view", SymbolView)
            self.symbol_view.load_df(symbol, df, self.args)

        self.update_status_bar()
        if self.query("#splash") and df is not None and not df.empty:
            self.remove(self.query_one("#splash"))

    def update_status_bar(self):
        live_icon = "🤖" if self.auto_trading_enabled else "🚫"
        if self.auto_trading_enabled:
            auto_trade_state = f"Auto-Trades: [BOLD GREEN]ENABLED[/BOLD GREEN] {live_icon}"
        else:
            auto_trade_state = f"Auto-Trades: [BOLD RED]DISABLED[/BOLD RED] {live_icon}"

        overlay = self.query_one("#overlay-text", TopOverlay)
        overlay.symbol = self.ticker_symbols[self.active_symbol_index]
        overlay.update_status(
            f"{self.active_symbol_index + 1} / {len(self.ticker_symbols)} | {auto_trade_state}"
        )

    def flash_message(self, msg: str):
        overlay = self.query_one("#overlay-text", TopOverlay)
        overlay.flash_message(f"ORDER FAILED: {msg}", 10)

    def set_real_trades(self, enabled: bool) -> None:
        """Update trading mode for the app and broker."""
        self.args.real_trades = enabled
        if hasattr(BROKER_API, "_real_trades"):
            setattr(BROKER_API, "_real_trades", enabled)

    def set_auto_trading(self, enabled: bool) -> None:
        """Enable or disable auto trading mode."""
        self.auto_trading_enabled = enabled
        self.update_status_bar()

    def set_trade_amount(self, amount: float) -> None:
        """Persist the trade amount value used for BUY orders."""
        try:
            self.trade_amount = float(amount)
        except ValueError:
            self.trade_amount = 0.0

    # ---------- Back-test workflow ----------

    def action_prompt_backtest(self) -> None:
        """Open the back-test input dialog (bound to the ‘b’ key)."""
        if self._is_splash_active():
            return
        current_symbol = self.ticker_symbols[self.active_symbol_index]
        self.push_screen(
            BacktestInputDialog(
                callback=self.on_backtest_submit,
                default_symbol=current_symbol,  # ← new arg
            )
        )

    async def on_backtest_submit(self, form: dict) -> None:
        """
        form = {"symbol": str, "from": str, "to": str, "cash": str}
        Runs in a thread to keep the UI responsive.
        """
        try:
            log.debug("Backtest starting...")
            overlay = self.query_one("#overlay-text", TopOverlay)
            overlay.update_status("Running backtest...")
            symbol = form["symbol"]
            starting_cash = float(form["cash"])

            # Fetch historical bars
            df, _ = await asyncio.to_thread(
                get_historical_data,
                DATA_API,
                symbol,
                from_date=form["from"],
                to_date=form["to"],
            )
            if df.empty:
                raise ValueError("No data returned for that period.")
            else:
                log.debug(f"Found {len(df)} data points for {symbol}.")

            # Run the back-test
            log.debug(f"Running backtest for {symbol}.")
            result = await asyncio.to_thread(
                self.run_backtest, df, symbol, self.args, starting_cash
            )
            log.debug("Backtest completed successfully.")

            num_buys = len(result.get("buy_signals", []))
            num_sells = len(result.get("sell_signals", []))

            equity_curve = result["equity_curve"]
            if isinstance(equity_curve, (pd.Series, pd.DataFrame)):
                equity_lookup = equity_curve.to_dict()
            else:
                equity_lookup = dict(zip(result.get("timestamps", []), equity_curve))

            trades = []
            for rec in result.get("buy_signals", []) + result.get("sell_signals", []):
                t = rec["time"]
                trades.append({
                    **rec,
                    "value": equity_lookup.get(t),
                })
            trades.sort(key=lambda r: r["time"])
            self._last_backtest_trades = trades
            log.debug(f"trades: {trades}")

            overlay.update_status(
                f"Backtest completed. Final portfolio value: ${result['final_value']:,.2f} | Buy count: {num_buys}")
            price_df = result["price_data"].copy()

            buy_times = {sig["time"] for sig in result["buy_signals"]}
            sell_times = {sig["time"] for sig in result["sell_signals"]}

            price_df["buy_signals"] = price_df.index.isin(buy_times)
            price_df["sell_signals"] = price_df.index.isin(sell_times)
            # left-join adds open/high/low/volume from the original df
            df = df.join(price_df[["buy_signals", "sell_signals"]])

            # Show results screen with summary information
            await self.push_screen(
                BacktestResultScreen(
                    df,
                    self.args,
                    symbol=symbol,
                    start_date=form["from"],
                    end_date=form["to"],
                    start_value=starting_cash,
                    end_value=result["final_value"],
                    num_buys=num_buys,
                    num_sells=num_sells,
                )
            )

        except Exception as exc:
            self.query_one("#overlay-text", TopOverlay).flash_message(
                f"Back-test error: {exc}", style="bold red"
            )
            log.error("Back-test error: %s", traceback.format_exc())

    def _exit_backtest(self) -> None:
        """Return to live data when the user presses 0-9."""
        if self.is_backtest:
            self.is_backtest = False
            # Turn is_backtest off for every graph shown.
            self.symbol_view.graph.is_backtest = False
            self.symbol_view.macd.is_backtest = False

            current = self.ticker_symbols[self.active_symbol_index]
            self.update_view(current)

    def run_backtest(self, df, symbol, args, starting_cash=1000.00):
        cerebro = bt.Cerebro()
        cerebro.addstrategy(
            CustomStrategy,
            symbol=symbol,
            bb_period=args.bb_period,
            bb_dev=args.bb_dev,
            macd_thresh=args.macd_thresh,
        )

        data = bt.feeds.PandasData(dataname=df)
        cerebro.adddata(data)
        cerebro.broker.setcash(starting_cash)
        cerebro.broker.addcommissioninfo(CommInfoFractional())
        cerebro.broker.setcommission(commission=0.00)
        cerebro.addsizer(bt.sizers.AllInSizer, percents=100)

        log.debug(f"Starting Portfolio Value: {cerebro.broker.getvalue():.2f}")
        results = cerebro.run()
        log.debug(f"Final Portfolio Value: {cerebro.broker.getvalue():.2f}")
        # cerebro.plot() # Hawk TUI!

        strat = results[0]

        # Generate equity curve
        portfolio_values = [strat.broker.get_value()]  # or track each day manually
        timestamps = df.index.tolist()
        equity_curve = list(zip(timestamps, portfolio_values))

        return {
            'final_value': cerebro.broker.getvalue(),
            'equity_curve': equity_curve,
            'price_data': df[['close']].copy(),
            'timestamps': timestamps,
            'buy_signals': strat.buy_signals,
            'sell_signals': strat.sell_signals,
        }


if __name__ == "__main__":
    # Show splash screen in a separate thread
    # splash_thread = threading.Thread(target=show_splash)
    # splash_thread.daemon = True  # So the thread dies when the program exits
    # splash_thread.start()

    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", type=str, default='AAPL,AMZN,META,MSFT,NVDA,TSLA,GOOG,VTI,GLD,BTCUSD',
                        help="List of ticker symbols (e.g. NVDA,TSLA,AAPL)")
    parser.add_argument("--candles", action="store_true", help="Show candlestick chart.")
    parser.add_argument("--macd_thresh", type=float, default=0.002, help="MACD threshold")
    parser.add_argument("--bb_period", type=int, default=200, help="Bollinger Band period")
    parser.add_argument("--bb_dev", type=float, default=2.0, help="Bollinger Band std dev")
    parser.add_argument("--real_trades", action='store_true', help="Enable live trading (vs paper)")
    parser.add_argument('--interval', default='1min')
    parser.add_argument('--stop_loss_pct', type=float, default=0.01, help="Stop loss pct")
    parser.add_argument('--take_profit_pct', type=float, default=0.05, help="Take profit pct")
    parser.add_argument('--lookback_period', type=int, default=1000, help="Lookback period")
    parser.add_argument('--scale', type=float, default=0.2, help="Scale factor")
    parser.add_argument("--broker", type=str, choices=["alpaca", "robinhood"], default="robinhood",
                        help="Choose which broker to use (Alpaca, Robinhood)"
                        )
    parser.add_argument("--data_api", type=str, choices=["alpaca", "robinhood", "fmp"], default="robinhood",
                        help="Choose which data provider to use (Alpaca, Robinhood, or FMP)"
                        )
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()

    args.symbols = [s.strip().upper() for s in args.symbols.split(",")]
    args.symbol = args.symbols[0]  # set initial active symbol
    log.debug(f"Loading symbols: {args.symbols}")

    # Loading from .env file
    load_dotenv()

    BROKER_API = None
    DATA_API = None

    if args.broker == "alpaca":
        from fetch.alpaca import AlpacaInterface

        BROKER_API: BrokerInterface = AlpacaInterface(real_trades=args.real_trades)
    elif args.broker == "robinhood":
        from fetch.robinhood import RobinhoodInterface, RobinhoodInterface

        BROKER_API = RobinhoodInterface()
    elif args.broker == "fmp":
        raise ValueError("Invalid broker: FMP does not support broker services, only data.")
    else:
        raise ValueError(f"Unknown broker: {args.broker}")

    if args.data_api == "alpaca":
        from fetch.alpaca import AlpacaInterface

        if args.broker == "alpaca":
            DATA_API = BROKER_API
        else:
            DATA_API = AlpacaInterface(real_trades=args.real_trades)
    elif args.data_api == "robinhood":
        from fetch.robinhood import RobinhoodInterface

        if args.broker == "robinhood":
            DATA_API = BROKER_API
        else:
            DATA_API = RobinhoodInterface()
    elif args.data_api == "fmp":
        from fetch.fmp import FMPInterface

        # FMP can only be a data_api, not valid for broker.
        DATA_API = FMPInterface()

    app = SpectrApp(args)
    app.run()
