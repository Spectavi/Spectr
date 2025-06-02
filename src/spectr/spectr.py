import argparse
import asyncio
import contextlib
import logging
import os
import queue
import sys
import threading
import traceback
from concurrent.futures._base import wait
from concurrent.futures.thread import ThreadPoolExecutor
from datetime import datetime, timedelta

import backtrader as bt
import pandas as pd
import playsound
from dotenv import load_dotenv
from textual.app import App, ComposeResult
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Static

import metrics
import utils
from CustomStrategy import CustomStrategy
from fetch.broker_interface import BrokerInterface, OrderSide, OrderType
from utils import load_cache, save_cache
from views.backtest_input_dialog import BacktestInputDialog
from views.order_dialog import OrderDialog
from views.portfolio_screen import PortfolioScreen
from views.splash_screen import SplashScreen
from views.symbol_view import SymbolView
from views.ticker_input_dialog import TickerInputDialog
from views.top_overlay import TopOverlay
from views.trades_screen import TradesScreen

# Notes for scanner filter:
# - Already up 5%.
# - 3x relative volume
# - News catalyst within the last 48 hrs.
# - < 10mill float?
# - Between $1.00 and $50.00?
# - Volume > 50k?

# Add float metric.

# Multi-thread scanner calls.
# Show how long it was since last scan.


# --- SOUND PATHS ---
BUY_SOUND_PATH = 'src/spectr/res/buy.mp3'
SELL_SOUND_PATH = 'src/spectr/res/sell.mp3'

REFRESH_INTERVAL = 30  # seconds

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
    ]

    ticker_symbols = reactive([])
    active_symbol_index = reactive(0)
    auto_trading_enabled: reactive[bool] = reactive(False)
    is_backtest: reactive[bool] = reactive(False)

    symbol_view: reactive[SymbolView] = reactive(None)

    def __init__(self, args):
        super().__init__()
        self._consumer_task = None
        self.args = args  # Store CLI arguments
        self._poll_pool: ThreadPoolExecutor | None = None
        # self._sig_lock = threading.Lock()  # protects self.signal_detected
        # self._poll_now = asyncio.Event()
        self._poll_thread = threading.Thread()
        self.macd_thresh = self.args.macd_thresh
        self.bb_period = self.args.bb_period
        self.bb_dev = self.args.bb_dev
        self.df_cache = {symbol: pd.DataFrame() for symbol in self.ticker_symbols}
        if not os.path.exists(utils.CACHE_DIR):
            os.mkdir(utils.CACHE_DIR)

        self._update_queue: queue.Queue[str] = queue.Queue()
        self._stop_event = threading.Event()
        self.signal_detected = []
        self._shutting_down = False

    def compose(self) -> ComposeResult:
        yield TopOverlay(id="overlay-text")
        yield SymbolView(id="symbol-view")

    async def on_mount(self):
        await self.push_screen(SplashScreen())
        # Set symbols and active symbol
        self.ticker_symbols = self.args.symbols
        self.active_symbol_index = 0
        symbol = self.ticker_symbols[0]
        log.debug(f"self.ticker_symbols: {self.ticker_symbols}")
        log.debug(f"self.active_symbol_index: {self.active_symbol_index}")
        log.debug(f"symbol: {symbol}")

        # Populate view with active symbols data.

        log.debug("App mounted.")
        # self.update_cache()
        log.debug("Cache updated.")

        # Kick off producer & consumer
        self._poll_pool = ThreadPoolExecutor(
            max_workers=min(8, len(self.ticker_symbols)),  # tweak as you wish
            thread_name_prefix="poll",
        )

        threading.Thread(target=self._polling_loop,
                         name="data-poller",
                         daemon=True).start()
        # self._poll_thread.start()
        self.update_status_bar()
        asyncio.create_task(self._process_updates())

    def update_cache(self, symbol: str, df_new: pd.DataFrame):
        try:
            cache = load_cache(symbol)
            # Merge & dedupe
            if not cache.empty:
                combined = pd.concat([cache, df_new])
                df_new = combined[~combined.index.duplicated(keep="last")].sort_index()
                log.info(f"Cache for {symbol} extended to {df_new.index.max().date()}")

            save_cache(symbol, df_new)
        except Exception as e:
            log.error(f"Failed to update cache for {symbol}: {traceback.format_exc()}")

    def get_live_data(self, symbol):
        df = DATA_API.fetch_chart_data(symbol, from_date=datetime.now().date().strftime("%Y-%m-%d"),
                                       to_date=datetime.now().date().strftime("%Y-%m-%d"))
        quote = DATA_API.fetch_quote(symbol)
        return df, quote

    # Grabs 1-day more than requested, calculates indicators, then trims to requested range.
    def get_historical_data(self, symbol: str, from_date: str, to_date: str):
        """
        Fetch OHLCV + quote for *symbol* in [from_date .. to_date] **inclusive**,
        but ensure that indicators that need a look-back window are fully
        initialised by pulling an extra day of data before `from_date`.
        """
        log.debug(f"Fetching historical data for {symbol}…")

        # Extend the request one calendar day back
        dt_from = datetime.strptime(from_date, "%Y-%m-%d").date()
        extended_from = (dt_from - timedelta(days=1)).strftime("%Y-%m-%d")
        log.debug(f"dt_from: {dt_from}")
        log.debug(f"extended_from: {extended_from}")

        # Pull the data and quote
        df = DATA_API.fetch_chart_data_for_backtest(symbol, from_date=extended_from, to_date=to_date)

        # Fallback to 5min data if 1min isn't present.
        if df.empty:
            df = DATA_API.fetch_chart_data_for_backtest(symbol, from_date=extended_from, to_date=to_date,
                                                        interval="5min")
        # Compute indicators on the *full* frame (needs the extra bar)
        df = metrics.analyze_indicators(df, self.bb_period, self.bb_dev, self.macd_thresh)
        quote = None
        try:
            quote = DATA_API.fetch_quote(symbol)
        except Exception:
            log.warning(f"Failed to fetch quote for {symbol}")

        # Trim back to the exact range the caller requested
        df = df.loc[from_date:to_date]  # string slice → inclusive

        return df, quote

    def _poll_one_symbol(self, symbol: str):
        try:
            log.debug(f"Fetching live data for {symbol}...")
            df, quote = self.get_live_data(symbol)
            if df.empty or quote is None:
                return

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
            if signal_dict:
                signal = signal_dict.get("signal")
                curr_price = quote.get("price")
                log.debug(f"Signal detected for {symbol}.")
                df.at[df.index[-1], 'trade'] = signal  # mark bar for plotting
                # self.update_view(symbol)
                if signal == "buy":
                    log.debug("Buy signal detected!")
                    self.signal_detected.append((symbol, curr_price, signal))
                    playsound.playsound(BUY_SOUND_PATH)
                elif signal == "sell":
                    log.debug("Sell signal detected!")
                    self.signal_detected.append((symbol, curr_price, signal))
                    playsound.playsound(SELL_SOUND_PATH)

            # Notify UI thread
            self.df_cache[symbol] = df
            self.update_cache(symbol, df)  # Update cache files.
            self._update_queue.put(symbol)
            if symbol == self.ticker_symbols[self.active_symbol_index]:
                if self.screen_stack and isinstance(self.screen_stack[-1], SplashScreen):
                    self.pop_screen()
            self.update_view(self.ticker_symbols[self.active_symbol_index])

        except Exception as exc:
            log.error(f"[poll] {symbol}: {traceback.format_exc()}")

    def _polling_loop(self) -> None:
        """Runs in *one* native thread; spins a pool for the symbols."""
        if self.is_backtest:
            return

        while not self._stop_event.is_set() and not self._shutting_down:
            # Fan-out
            futures = [
                self._poll_pool.submit(self._poll_one_symbol, sym)
                for sym in self.ticker_symbols
            ]

            # Fan-in – wait until ALL symbols finish
            wait(futures, return_when="ALL_COMPLETED")

            # (optional) bail early if any worker raised
            for f in futures:
                if exc := f.exception():
                    log.error(f"Worker crashed: {exc}")

            if self._stop_event.wait(REFRESH_INTERVAL):
                break

    async def _process_updates(self) -> None:
        """Runs in Textual’s event loop; applies any fresh data to the UI."""
        while True:
            symbol: str = await asyncio.to_thread(self._update_queue.get)
            if symbol is None:
                return
            # If the update is for the symbol the user is currently looking at,
            # push it straight into the Graph/MACD views.
            # If a buy signal was triggered, switch to that symbol
            if len(self.signal_detected) > 0:
                for signal in self.signal_detected:
                    sym, price, sig = signal
                    index = self.ticker_symbols.index(sym)
                    self.active_symbol_index = index
                    msg = f"{sym} @ {price} 🚀"
                    if sig == 'buy':
                        msg = f"BUY {msg}"
                    if sig == 'sell':
                        msg = f"SELL {msg}"

                    if not self.auto_trading_enabled and sig:
                        self.signal_detected.remove(signal)
                        self.open_order_dialog(side=sig, pos_pct=100.0, symbol=sym)
                        continue
                    else:
                        msg = f"ORDER SUBMITTED! {msg}"
                        if not self.args.real_trades:
                            msg = f"PAPER {msg}"
                        else:
                            msg = f"REAL {msg}"
                        self.signal_detected.remove(signal)
                        BROKER_API.submit_order(symbol, sig, 1, self.args.real_trades)
                        playsound.playsound(BUY_SOUND_PATH if sig == "buy" else SELL_SOUND_PATH)
            elif symbol == self.ticker_symbols[self.active_symbol_index]:
                if not self.is_backtest:
                    df = self.df_cache.get(symbol)
                    if df is not None:
                        self.update_view(symbol)

    def _safe_submit(self, fn, *args, **kw):
        if (
                self._shutting_down
                or self._poll_pool is None
                or self._poll_pool._shutdown
        ):
            return None
        try:
            return self._poll_pool.submit(fn, *args, **kw)
        except RuntimeError:
            return None

    async def on_shutdown(self, event):
        # 🚦 tell every background task we are quitting
        self._exit_backtest()

        self._shutting_down = True
        self._stop_event.set()

        loop = asyncio.get_running_loop()
        await loop.shutdown_default_executor()  # ← kills the to_thread workers

        # 📨 unblock and cancel the queue consumer **before** closing the pool
        if hasattr(self, "_consumer_task"):
            self._update_queue.put_nowait(None)  # sentinel wakes .get()
            self._consumer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._consumer_task

        # 🏊 shut down the worker pool and wait until every worker thread dies
        if self._poll_pool:
            self._poll_pool.shutdown(wait=False, cancel_futures=True)
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join()



    # ------------ Action Functions -------------

    def action_select_symbol(self, key: str):
        self._exit_backtest()
        index = (int(key) - 1) if key != "0" else 9

        if index <= len(self.ticker_symbols) - 1:
            self.active_symbol_index = index
            symbol = self.ticker_symbols[index]
            log.debug(f"action selected symbol: {symbol}")
            symbol = self.ticker_symbols[index]
            if self._poll_pool:
                self._safe_submit(self._poll_one_symbol, symbol)
            if hasattr(self, "_poll_now"):
                self._poll_now.set()
            # self.update_view(symbol)

    def action_prev_symbol(self):
        self._exit_backtest()
        new_index = self.active_symbol_index - 1
        if new_index < 0:
            new_index = len(self.ticker_symbols) - 1
        self.active_symbol_index = new_index
        symbol = self.ticker_symbols[new_index]
        if self._poll_pool:
            self._safe_submit(self._poll_one_symbol, symbol)
        if hasattr(self, "_poll_now"):
            self._poll_now.set()
        # self.update_view(symbol)

    def action_next_symbol(self):
        self._exit_backtest()
        new_index = self.active_symbol_index + 1
        if new_index > len(self.ticker_symbols) - 1:
            new_index = 0
        self.active_symbol_index = new_index
        symbol = self.ticker_symbols[new_index]
        if self._poll_pool:
            self._safe_submit(self._poll_one_symbol, symbol)
        if hasattr(self, "_poll_now"):
            self._poll_now.set()
        # self.update_view(symbol)



    # ------------- Order Dialog -------------

    def action_buy_current_symbol(self):
        self._exit_backtest()
        symbol = self.ticker_symbols[self.active_symbol_index]
        self.open_order_dialog(OrderSide.BUY, 0.00, symbol)

    def action_sell_current_symbol(self):
        self._exit_backtest()
        symbol = self.ticker_symbols[self.active_symbol_index]
        self.open_order_dialog(OrderSide.SELL, 1.0, symbol)

    def action_sell_half_current_symbol(self):
        self._exit_backtest()
        symbol = self.ticker_symbols[self.active_symbol_index]
        self.open_order_dialog(OrderSide.SELL, 0.50, symbol)

    def action_sell_quarter_current_symbol(self):
        self._exit_backtest()
        symbol = self.ticker_symbols[self.active_symbol_index]
        self.open_order_dialog(OrderSide.SELL, 0.25, symbol)

    def open_order_dialog(self, side: OrderSide, pos_pct: float, symbol: str):
        self.push_screen(OrderDialog(side=side, symbol=symbol, pos_pct=pos_pct,
                                     get_pos_cb=BROKER_API.get_position,
                                     get_price_cb=DATA_API.fetch_quote))



    # ------------ Arm / Dis-arm -------------

    def action_arm_auto_trading(self):
        self.auto_trading_enabled = not self.auto_trading_enabled
        self.update_status_bar()



    # ------------ Select Ticker -------------

    def action_prompt_symbol(self):
        self.auto_trading_enabled = False
        self.push_screen(TickerInputDialog(callback=self.on_ticker_submit, top_movers_cb=DATA_API.fetch_top_movers,
                                           quote_cb=DATA_API.fetch_quote,
                                           has_recent_positive_news_cb=DATA_API.has_recent_positive_news))

    def on_ticker_submit(self, symbols: str):
        if (symbols):
            log.debug(f"on_ticker_submit: {symbols}")
            self.ticker_symbols = [x.strip().upper() for x in symbols.split(',')]  # Update the symbol used by the app
            log.debug(f"on_ticker_submit: {self.ticker_symbols}")
            self.active_symbol_index = 0
            symbol = self.ticker_symbols[self.active_symbol_index]

            if self._poll_pool:
                self._safe_submit(self._poll_one_symbol, symbol)
            if hasattr(self, "_poll_now"):
                self._poll_now.set()
            self.update_view(symbol)

    def action_toggle_trades(self) -> None:
        # Only meaningful after a back-test has just finished
        if getattr(self, "_last_backtest_trades", None):
            if self.screen_stack and isinstance(self.screen_stack[-1], TradesScreen):
                self.pop_screen()  # already open → close
            else:
                self.push_screen(TradesScreen(self._last_backtest_trades))


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
                side=OrderSide.SELL if msg.side == "SELL" else OrderSide.BUY,
                type=msg.order_type,
                quantity=msg.qty,
            )
        except Exception as e:
            log.error(e)
            self.flash_message(f"{e}")

        # mark the last bar so GraphView can plot the trade immediately
        symbol = msg.symbol.upper()
        side = msg.side.lower()  # "buy" / "sell"
        df = self.df_cache.get(symbol)
        if df is not None and not df.empty:
            last_ts = df.index[-1]

            # add / update the helper columns used by GraphView
            if side == "buy":
                if "buy_signals" not in df.columns: df["buy_signals"] = None
                df.at[last_ts, "buy_signals"] = True
            elif side == "sell":
                if "sell_signals" not in df.columns: df["sell_signals"] = None
                df.at[last_ts, "sell_signals"] = True

            # cache the modified frame
            self.df_cache[symbol] = df

            # if the user is currently viewing that symbol, refresh the plot now
            if symbol == self.ticker_symbols[self.active_symbol_index]:
                self.update_view(symbol)

    # --------------

    def action_toggle_portfolio(self) -> None:
        if self.screen_stack and isinstance(self.screen_stack[-1], PortfolioScreen):
            self.pop_screen()
        else:
            # pass your broker instance; adjust if you keep it elsewhere
            balance_info = BROKER_API.get_balance()
            if not balance_info:
                self.flash_message("ERROR ACCESSING BROKER ACCOUNT!")

            cash = balance_info.get("cash") if balance_info else 0.00
            buying_power = balance_info.get("buying_power") if balance_info else 0.00
            portfolio_value = balance_info.get("portfolio_value") if balance_info else 0.00
            positions = BROKER_API.get_positions()

            self.push_screen(PortfolioScreen(cash, buying_power, portfolio_value, positions, BROKER_API.get_all_orders,
                                             self.args.real_trades))

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

    # ---------- Back-test workflow ----------

    def action_prompt_backtest(self) -> None:
        """Open the back-test input dialog (bound to the ‘b’ key)."""
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
                self.get_historical_data,
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
            self.is_backtest = True

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

            # Switch the UI into back-test mode
            self.symbol_view.graph.is_backtest = True
            self.symbol_view.macd.is_backtest = True
            self.update_view(symbol)

        except Exception as exc:
            self.query_one("#overlay-text", TopOverlay).flash_message(
                f"Back-test error: {exc}", style="bold red"
            )
            log.error("Back-test error: %s", traceback.format_exc())
            self.is_backtest = False

            # Turn is_backtest off for every graph shown.
            self.symbol_view.graph.is_backtest = False
            self.symbol_view.macd.is_backtest = False
            self.update_status_bar()

    def _exit_backtest(self) -> None:
        """Return to live data when the user presses 0-9."""
        if self.is_backtest:
            self.is_backtest = False
            # Turn is_backtest off for every graph shown.
            self.symbol_view.graph.is_backtest = False
            self.symbol_view.macd.is_backtest = False

            current = self.ticker_symbols[self.active_symbol_index]
            self.update_view(current)

    def run_backtest(self, df, symbol, args, starting_cash=1000):
        cerebro = bt.Cerebro()
        cerebro.addstrategy(CustomStrategy, symbol=symbol, bb_period=args.bb_period, bb_dev=args.bb_dev,
                            macd_thresh=args.macd_thresh, is_backtest=True)

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


# def show_splash():
#     # Clear the terminal window
#     if sys.platform == 'win32':
#         os.system('cls')
#     else:
#         os.system('clear')
#
#     # Center the ASCII art
#     terminal_width = 80  # You might want to calculate this dynamically
#     spaces = ' ' * ((terminal_width - len(max(GHOST.split('\n'), key=len))) // 2)
#
#     print(spaces + "Loading... Please wait")
#     print()
#     for line in GHOST.split('\n'):
#         if line.strip() != '':
#             print(spaces + line)

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
