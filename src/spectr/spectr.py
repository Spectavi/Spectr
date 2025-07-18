import asyncio
import contextlib
import logging
import os

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import queue
import threading
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import SimpleNamespace

import pandas as pd
from textual import events
from textual.app import App, ComposeResult
from textual.reactive import reactive

from . import cache
from .strategies import metrics
from . import utils
from .agent import VoiceAgent
from .fetch.broker_interface import OrderSide
from .scanners import load_scanner, list_scanners
from .strategies import load_strategy, list_strategies, get_strategy_code
from .utils import (
    get_historical_data,
)
from . import broker_tools
from .backtest import run_backtest
from .views.backtest_input_dialog import BacktestInputDialog
from .views.backtest_result_screen import BacktestResultScreen
from .views.order_dialog import OrderDialog
from .views.portfolio_screen import PortfolioScreen
from .views.splash_screen import SplashScreen
from .views.strategy_screen import StrategyScreen
from .views.symbol_view import SymbolView
from .views.ticker_input_dialog import TickerInputDialog
from .views.top_overlay import TopOverlay
from .views.trades_screen import TradesScreen

# Notes for scanner filter:
# - Already up 5%?
# - 4x relative volume.
# - News catalyst within the last 48 hrs.
# - < 10mill float?
# - Between $1.00 and $50.00?
# - Volume > 50k?

# Show how long it was since last scan. TTS


# --- SOUND PATHS ---
BUY_SOUND_PATH = "res/buy.mp3"
SELL_SOUND_PATH = "res/sell.mp3"

REFRESH_INTERVAL = 60  # seconds
SCANNER_INTERVAL = REFRESH_INTERVAL
EQUITY_INTERVAL = 60  # portfolio equity update frequency
ORDER_STATUS_INTERVAL = 60  # order status refresh frequency

# Setup logging to file
log_path = "debug.log"
logging.basicConfig(
    filename=log_path,
    filemode="w",
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


@dataclass
class AppConfig:
    """Configuration values for indicator analysis."""

    macd_thresh: float = 0.002
    bb_period: int = 200
    bb_dev: float = 2.0
    stop_loss_pct: float = 0.01
    take_profit_pct: float = 0.05
    lookback_period: int = 1000
    interval: str = "1min"
    scale: float = 0.2


class OrderSignal:
    """A simple class to hold order signals."""

    def __init__(self, symbol: str, side: OrderSide, pos_pct: float = 100.0):
        self.symbol = symbol
        self.side = side
        self.pos_pct = pos_pct


class SpectrApp(App):
    CSS_PATH = "default.tcss"
    BINDINGS = [
        ("escape", "quit", "Quit"),
        ("t", "prompt_symbol", "Change Ticker"),  # T key
        ("`", "prompt_symbol", "Change Ticker"),  # ~ key
        ("ctrl+a", "arm_auto_trading", "Arms Auto-Trading - REAL trades will occur!"),
        ("ctrl+q", "buy_current_symbol", "Opens buy dialog for current symbol."),
        (
            "ctrl+z",
            "sell_current_symbol",
            "Opens sell dialog for current symbol, set to 100% of position",
        ),
        (
            "ctrl+x",
            "sell_half_current_symbol",
            "Opens sell dialog for current symbol, set to 50% of position",
        ),
        (
            "ctrl+c",
            "sell_quarter_current_symbol",
            "Opens sell dialog for current symbol, set to 25% of position",
        ),
        (
            "ctrl+d",
            "remove_current_symbol",
            "Remove the active symbol from the watchlist",
        ),
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
        ("v", "ask_agent", "Voice Assistant"),
    ]

    ticker_symbols = reactive([])
    active_symbol_index = reactive(0)
    auto_trading_enabled: reactive[bool] = reactive(False)
    afterhours_enabled: reactive[bool] = reactive(True)
    strategy_active: reactive[bool] = reactive(True)
    is_backtest: reactive[bool] = reactive(False)
    trade_amount: reactive[float] = reactive(0.0)
    confirm_quit: reactive[bool] = reactive(False)

    symbol_view: reactive[SymbolView] = reactive(None)

    def on_key(self, event) -> None:
        if self.confirm_quit and isinstance(event, events.Key):
            if event.key.lower() == "y":
                event.stop()
                asyncio.create_task(self._shutdown())
            elif event.key.lower() == "n":
                event.stop()
                self.confirm_quit = False
                self.overlay.clear_prompt()
                self.update_status_bar()

    def _is_splash_active(self) -> bool:
        """Return ``True`` if the splash screen is currently visible."""
        return bool(
            self.screen_stack and isinstance(self.screen_stack[-1], SplashScreen)
        )

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

    def __init__(self, args, config: AppConfig):
        super().__init__()
        if not hasattr(self, "exit_event"):
            self.exit_event = asyncio.Event()
        self._consumer_task = None
        self.args = args  # Store CLI arguments
        self.config = config
        self._sig_lock = threading.Lock()  # protects self.signal_detected
        self._poll_worker = None
        self._scanner_worker = None
        self._equity_worker = None
        self._order_status_worker = None
        self._voice_worker = None
        self.df_cache = {symbol: pd.DataFrame() for symbol in self.ticker_symbols}
        if not os.path.exists(cache.CACHE_DIR):
            os.mkdir(cache.CACHE_DIR)

        self._update_queue: queue.Queue[str] = queue.Queue()
        self.signal_detected = []
        self.strategy_signals: list[dict] = cache.load_strategy_cache()
        self.available_strategies = list_strategies()
        saved_strategy = cache.load_selected_strategy()
        if saved_strategy and saved_strategy in self.available_strategies:
            self.strategy_name = saved_strategy
            self.strategy_class = load_strategy(saved_strategy)
        else:
            self.strategy_name = "CustomStrategy"
            self.strategy_class = load_strategy(self.strategy_name)
            cache.save_selected_strategy(None)
        self._shutting_down = False

        self.trade_amount = 0.0
        cached_amount = cache.load_trade_amount()
        if cached_amount is not None:
            self.trade_amount = cached_amount

        self.voice_agent = VoiceAgent(
            broker_api=BROKER_API,
            data_api=DATA_API,
            get_cached_orders=lambda: self._portfolio_orders_cache,
            add_symbol=self.add_symbol,
            remove_symbol=self.remove_symbol,
            get_strategy_code=lambda: (
                get_strategy_code(self.strategy_name) if self.strategy_name else ""
            ),
            stream_voice=getattr(args, "voice_streaming", False),
        )
        if getattr(args, "listen", False):
            self.voice_agent.start_wake_word_listener(
                getattr(args, "wake_word", "spectr")
            )

        # Available background scanners
        self.available_scanners = list_scanners()
        saved_scanner = cache.load_selected_scanner()
        default_scanner = saved_scanner or "CustomScanner"
        if default_scanner in self.available_scanners:
            self.scanner_name = default_scanner
        else:
            self.scanner_name = next(iter(self.available_scanners))
        self.scanner_class = load_scanner(self.scanner_name)
        cache.save_selected_scanner(self.scanner_name)
        self.scanner = self.scanner_class(DATA_API, self.exit_event)

        # Track latest quotes and equity curve
        self._latest_quotes: dict[str, float] = {}
        self._equity_curve_data: list[tuple[datetime, float, float]] = []

        # Cache for portfolio data so reopening the portfolio screen is instant
        self._portfolio_balance_cache: dict | None = None
        self._portfolio_positions_cache: list | None = None
        self._portfolio_orders_cache: list | None = None

    @property
    def scanner_results(self) -> list[dict]:
        return self.scanner.scanner_results

    @property
    def top_gainers(self) -> list[dict]:
        return self.scanner.top_gainers

    def compose(self) -> ComposeResult:
        self.overlay = TopOverlay(id="overlay-text")
        yield self.overlay
        yield SymbolView(id="symbol-view")

    def _fetch_data(self, symbol: str, quote: dict | None = None):
        """Fetch the latest data and inject the most recent quote."""
        log.debug(f"Fetching live data for {symbol}...")
        df = DATA_API.fetch_chart_data(
            symbol,
            from_date=datetime.now().date().strftime("%Y-%m-%d"),
            to_date=datetime.now().date().strftime("%Y-%m-%d"),
        )
        if quote is None:
            quote = DATA_API.fetch_quote(symbol)
        if df.empty or quote is None:
            return pd.DataFrame(), None

        price = quote.get("price")
        if price is not None:
            self._latest_quotes[symbol.upper()] = float(price)

        log.debug(f"Injecting quote for {symbol}")
        df = utils.inject_quote_into_df(df, quote)
        return df, quote

    def _analyze_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        log.debug("Analyzing indicators")
        if self.strategy_class is None:
            return df
        df = metrics.analyze_indicators(
            df,
            self.strategy_class.get_indicators(),
        )
        df["trade"] = None
        df["signal"] = None
        return df

    def _handle_signal(
        self, symbol: str, df: pd.DataFrame, quote: dict, signal_dict: dict
    ) -> None:
        """Record signals and queue order events."""
        signal = signal_dict.get("signal")
        curr_price = quote.get("price")
        reason = signal_dict.get("reason")
        log.debug(f"Signal detected for {symbol}. Reason: {reason}")
        df.at[df.index[-1], "trade"] = signal
        # Append signal to queue to show order dialog, or auto-trade.
        self.call_from_thread(
            self.signal_detected.append, (symbol, curr_price, signal, reason)
        )

        if (
            signal
            and self.auto_trading_enabled
            and self.afterhours_enabled
            and not utils.is_market_open_now()
        ):
            side = (
                OrderSide.BUY
                if signal == "buy"
                else OrderSide.SELL if signal == "sell" else None
            )
            if side:
                broker_tools.submit_order(
                    BROKER_API,
                    symbol,
                    side,
                    curr_price,
                    self.trade_amount,
                    self.auto_trading_enabled,
                    voice_agent=self.voice_agent,
                    buy_sound_path=BUY_SOUND_PATH,
                    sell_sound_path=SELL_SOUND_PATH,
                )
                self.call_from_thread(
                    self.signal_detected.remove,
                    (symbol, curr_price, signal, reason),
                )

        self.call_from_thread(
            cache.record_signal,
            self.strategy_signals,
            {
                "time": datetime.now(),
                "symbol": symbol,
                "side": signal,
                "price": curr_price,
                "reason": reason,
                "strategy": self.strategy_name,
            },
        )
        if signal:
            self.voice_agent.say(f"{signal.capitalize()} signal for {symbol}")

    async def on_mount(self, event: events.Mount) -> None:
        await self.push_screen(SplashScreen(id="splash"), wait_for_dismiss=False)
        self.refresh()

        overlay = self.overlay
        self.voice_agent._on_speech_start = lambda: self.call_from_thread(
            overlay.start_voice_animation
        )
        self.voice_agent._on_speech_end = lambda: self.call_from_thread(
            overlay.stop_voice_animation
        )

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
        self._scanner_worker = self.run_worker(self.scanner.scanner_loop, thread=False)
        self._equity_worker = self.run_worker(self._equity_loop, thread=False)
        self._order_status_worker = self.run_worker(
            self._order_status_loop, thread=False
        )

        # self.update_status_bar()
        if self.args.broker == "robinhood" and self.args.real_trades:
            self.overlay.flash_message(
                "Robinhood does NOT support PAPER TRADING!", style="bold red"
            )
        log.debug("starting consumer task")
        self._consumer_task = asyncio.create_task(self._process_updates())

    def _normalize_position(self, position):
        """Return a copy of ``position`` with numeric qty/market_value fields."""
        if position is None:
            return None
        try:
            if hasattr(position, "qty"):
                val = getattr(position, "qty")
                if isinstance(val, str):
                    setattr(position, "qty", float(val))
            elif hasattr(position, "size"):
                val = getattr(position, "size")
                if isinstance(val, str):
                    setattr(position, "size", float(val))
        except Exception:
            pass

        try:
            if hasattr(position, "market_value"):
                val = getattr(position, "market_value")
                if isinstance(val, str):
                    setattr(position, "market_value", float(val))
        except Exception:
            pass

        return position

    def _poll_one_symbol(self, symbol: str, quote: dict | None = None, position=None):
        if self.strategy_class is None:
            return
        try:
            df, quote = self._fetch_data(symbol, quote)
            if df.empty or quote is None:
                self.df_cache[symbol] = df
                self._update_queue.put(symbol)
                return

            df = self._analyze_indicators(df)

            if position is None:
                position = BROKER_API.get_position(symbol)

            position = self._normalize_position(position)
            orders = None
            try:
                orders = BROKER_API.get_pending_orders(symbol)
            except Exception:
                orders = None

            signal_dict = None
            if self.strategy_active:
                try:
                    signal_dict = self.strategy_class.detect_signals(
                        df,
                        symbol,
                        position=position,
                        orders=orders,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.error("[poll] signal error: %s", traceback.format_exc())

                    def _flash_error() -> None:
                        self.overlay.flash_message(
                            f"Strategy error: {exc}",
                            style="bold red",
                        )

                    self.call_from_thread(_flash_error)
                    self.call_from_thread(
                        self.voice_agent.say, f"Strategy error: {exc}"
                    )
                    if self._is_splash_active():
                        self.call_from_thread(self.pop_screen)
                    return

            # Check for signal
            if signal_dict and not self._is_splash_active():
                self._handle_signal(symbol, df, quote, signal_dict)

            self.df_cache[symbol] = df
            self._update_queue.put(symbol)
            if symbol == self.ticker_symbols[self.active_symbol_index]:
                if self._is_splash_active():
                    self.call_from_thread(self.pop_screen)
                    self.voice_agent.say("Welcome to Spectr", wait=True)
                # refresh the active view from the UI thread
                self.call_from_thread(
                    self.update_view, self.ticker_symbols[self.active_symbol_index]
                )
        except Exception:
            log.error(f"[poll] {symbol}: {traceback.format_exc()}")

    async def _polling_loop(self) -> None:
        """Poll all symbols at regular intervals."""
        if self.is_backtest:
            return

        while not self.exit_event.is_set():
            try:
                quotes = DATA_API.fetch_quotes(list(self.ticker_symbols))
            except Exception as exc:
                log.error(f"[poll] batch quote error: {exc}")
                quotes = {sym: None for sym in self.ticker_symbols}

            try:
                positions = BROKER_API.get_positions() or []
            except Exception as exc:
                log.warning(f"Failed to fetch positions: {exc}")
                positions = []

            pos_map = {getattr(pos, "symbol", "").upper(): pos for pos in positions}

            tasks = [
                asyncio.to_thread(
                    self._poll_one_symbol,
                    sym,
                    quotes.get(sym.upper()),
                    pos_map.get(sym.upper()),
                )
                for sym in self.ticker_symbols
            ]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            try:
                await asyncio.wait_for(self.exit_event.wait(), timeout=REFRESH_INTERVAL)
            except asyncio.TimeoutError:
                pass

    async def _process_updates(self) -> None:
        """Runs in Textual’s event loop; applies any fresh data to the UI."""
        while True:
            symbol: str = await asyncio.to_thread(self._update_queue.get)
            if symbol is None:
                log.debug("_process_updates exit")
                return
            # If the update is for the symbol the user is currently looking at,
            # push it straight into the Graph/MACD views.
            # If a buy signal was triggered, switch to that symbol
            if len(self.signal_detected) > 0:
                for signal in list(self.signal_detected):
                    _sym, _price, _sig, _reason = signal
                    index = self.ticker_symbols.index(_sym)
                    self.active_symbol_index = index
                    msg = f"{_sym} @ {_price} 🚀"
                    log.debug(f"Signal for {_sym}: {msg} ({_sig})")
                    side = None
                    if _sig == "buy":
                        msg = f"BUY {msg}"
                        side = OrderSide.BUY
                    if _sig == "sell":
                        msg = f"SELL {msg}"
                        side = OrderSide.SELL

                    if not self.auto_trading_enabled and _sig and side:
                        should_prompt = not self.auto_trading_enabled or (
                            self.auto_trading_enabled
                            and not self.afterhours_enabled
                            and not utils.is_market_open_now()
                        )
                        if should_prompt and _sig and side:
                            log.debug(f"Signal detected, opening dialog: {msg}")
                            if BROKER_API.has_pending_order(_sym):
                                log.warning(
                                    f"Pending order for {_sym}; ignoring signal!"
                                )

                                self.signal_detected.remove(signal)
                                continue
                            self.signal_detected.remove(signal)
                            if self.screen_stack and not isinstance(
                                self.screen_stack[-1], OrderDialog
                            ):
                                self.open_order_dialog(
                                    side=side,
                                    pos_pct=100.0,
                                    symbol=_sym,
                                    reason=_reason,
                                )
                            continue
                    elif self.auto_trading_enabled and _sig and side:
                        log.info(
                            f"AUTO-TRADE: Submitting order for {_sym} at {_price} with side {_sig}"
                        )
                        # Skip auto-ordering if there's already an open order
                        if BROKER_API.has_pending_order(_sym):
                            log.warning(f"Pending order for {_sym}; ignoring signal!")
                            self.signal_detected.remove(signal)
                            self.voice_agent.say(
                                f"Ignoring {_sig.capitalize()} signal for {_sym}, pending order already exists."
                            )
                            return

                        self.signal_detected.remove(signal)
                        order = broker_tools.submit_order(
                            BROKER_API,
                            _sym,
                            side,
                            _price,
                            self.trade_amount,
                            self.auto_trading_enabled,
                            voice_agent=self.voice_agent,
                            buy_sound_path=BUY_SOUND_PATH,
                            sell_sound_path=SELL_SOUND_PATH,
                        )
                        # Save to cache.
                        cache.attach_order_to_last_signal(
                            self.strategy_signals,
                            _sym.upper(),
                            side.name.lower(),
                            order,
                        )
            elif symbol == self.ticker_symbols[self.active_symbol_index]:
                if not self.is_backtest:
                    df = self.df_cache.get(symbol)
                    if df is not None:
                        self.update_view(symbol)

    async def _equity_loop(self) -> None:
        """Periodically update portfolio equity using cached quotes."""
        while not self.exit_event.is_set():
            try:
                await asyncio.to_thread(self._update_portfolio_equity)
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

    async def _order_status_loop(self) -> None:
        """Periodic update of open order statuses."""
        while not self.exit_event.is_set():
            try:
                # Determine if any signals need status refresh
                open_ids = {
                    str(rec["order_id"])
                    for rec in self.strategy_signals
                    if rec.get("order_id")
                    and str(rec.get("order_status", "")).lower()
                    not in {"filled", "canceled", "cancelled", "expired", "rejected"}
                }
                if open_ids:
                    orders = BROKER_API.get_all_orders()
                    if isinstance(orders, pd.DataFrame):
                        if not orders.empty:
                            orders = [
                                SimpleNamespace(**rec)
                                for rec in orders.to_dict(orient="records")
                            ]
                        else:
                            orders = []
                    cache.update_order_statuses(self.strategy_signals, orders)
            except Exception as exc:  # pragma: no cover - best effort
                log.error(f"[order_status] {exc}")

            try:
                await asyncio.wait_for(
                    self.exit_event.wait(), timeout=ORDER_STATUS_INTERVAL
                )
            except asyncio.TimeoutError:
                pass

        log.debug("_order_status_loop exit")

    async def _shutdown(self) -> None:
        """Stop background tasks and exit the application."""
        log.info("on_shutdown start")
        try:
            self.exit_event.set()
            self._exit_backtest()
            self.auto_trading_enabled = False
            self._shutting_down = True

            cache.save_symbols_cache(self.ticker_symbols)

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

            if self._order_status_worker:
                log.debug("cancelling order status worker")
                self._order_status_worker.cancel()
                self._order_status_worker = None

            if self._consumer_task:
                log.debug("cancelling consumer task")
                self._update_queue.put_nowait(None)
                self._consumer_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    self._consumer_task = None

            self.voice_agent.stop_wake_word_listener()

        except Exception:
            log.exception("on_shutdown encountered an error")
            os._exit(1)

        log.info("on_shutdown complete")
        self.exit(return_code=0)

    async def action_quit(self):
        """Prompt the user for confirmation before quitting."""
        if not self.confirm_quit:
            self.confirm_quit = True
            self.overlay.show_prompt("Quit Y/N?", style="bold red")
            return

        # Second ESC cancels the prompt
        self.confirm_quit = False
        self.overlay.clear_prompt()
        self.update_status_bar()

    # ------------ Action Functions -------------

    def action_select_symbol(self, key: str):
        self._exit_backtest()
        index = (int(key) - 1) if key != "0" else 9

        if index <= len(self.ticker_symbols) - 1:
            self.active_symbol_index = index
            symbol = self.ticker_symbols[index]
            log.debug(f"action selected symbol: {symbol}")
            symbol = self.ticker_symbols[index]
            self.run_worker(lambda: self._poll_one_symbol(symbol), thread=True)
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
        self.run_worker(lambda: self._poll_one_symbol(symbol), thread=True)
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
        self.run_worker(lambda: self._poll_one_symbol(symbol), thread=True)
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

    def open_order_dialog(
        self, side: OrderSide, pos_pct: float, symbol: str, reason: str | None = None
    ):
        if self._is_splash_active():
            return
        if BROKER_API.has_pending_order(symbol):
            log.warning(f"Pending order for {symbol}; dialog not opened")
            if hasattr(self, "overlay") and self.overlay:
                self.overlay.flash_message(
                    f"Pending order for {symbol}", style="bold yellow", duration=5.0
                )
            return
        order_type, limit_price = broker_tools.prepare_order_details(
            symbol, side, BROKER_API
        )
        self.push_screen(
            OrderDialog(
                side=side,
                symbol=symbol,
                pos_pct=pos_pct,
                get_pos_cb=BROKER_API.get_position,
                get_price_cb=BROKER_API.fetch_quote,
                trade_amount=self.trade_amount if side == OrderSide.BUY else 0.0,
                reason=reason,
                default_order_type=order_type,
                default_limit_price=limit_price,
            )
        )

    def action_remove_current_symbol(self) -> None:
        """Remove the active symbol from the watchlist."""
        if self._is_splash_active():
            return
        self._exit_backtest()
        if not self.ticker_symbols:
            return
        symbol = self.ticker_symbols[self.active_symbol_index]
        self.remove_symbol(symbol)

    # ------------ Arm / Dis-arm -------------

    def action_arm_auto_trading(self):
        self.set_auto_trading(not self.auto_trading_enabled)

    # ------------ Select Ticker -------------

    def action_prompt_symbol(self):
        if self._is_splash_active():
            return
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
                scanner_names=list(self.available_scanners.keys()),
                current_scanner=self.scanner_name,
                set_scanner_cb=self.set_scanner,
            )
        )

    def on_ticker_submit(self, symbols: str):
        if symbols:
            log.debug(f"on_ticker_submit: {symbols}")
            self.ticker_symbols = [x.strip().upper() for x in symbols.split(",")]
            self._prepend_open_positions()
            self.args.symbols = self.ticker_symbols
            log.debug(f"on_ticker_submit: {self.ticker_symbols}")
            self.active_symbol_index = 0
            symbol = self.ticker_symbols[self.active_symbol_index]

            self.run_worker(lambda: self._poll_one_symbol(symbol), thread=True)
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
            self.push_screen(
                StrategyScreen(
                    list(self.strategy_signals),
                    list(self.available_strategies.keys()),
                    self.strategy_name,
                    self.set_strategy,
                )
            )

    def action_ask_agent(self) -> None:
        if self._is_splash_active():
            return
        if self._voice_worker and self._voice_worker.is_running:
            self.voice_agent.stop()
            self._voice_worker.cancel()
            self.overlay.clear_prompt()
            self.update_status_bar()
            return
        self._voice_worker = self.run_worker(self._ask_agent, thread=True)

    def _ask_agent(self) -> None:
        """Run the voice assistant and display errors in the overlay."""
        overlay = self.overlay
        self.call_from_thread(overlay.show_prompt, "Listening...")
        try:
            self.voice_agent.listen_and_answer()
        except Exception as exc:
            log.error("Voice agent error: %s", traceback.format_exc())
            self.call_from_thread(overlay.clear_prompt)
            self.call_from_thread(
                overlay.flash_message,
                f"Voice error: {exc}",
            )
        else:
            self.call_from_thread(overlay.clear_prompt)
        finally:
            self.call_from_thread(self.update_status_bar)
            self._voice_worker = None

    # ------------ Order Dialog Submit Logic -------------

    async def on_order_dialog_submit(self, msg: OrderDialog.Submit) -> None:
        """Receive the order details and route them to your broker layer."""
        log.info(
            f"Placing {msg.side} {msg.qty} {msg.symbol} @ ${msg.price:.2f} "
            f"(total ${msg.total:,.2f})"
        )
        if BROKER_API.has_pending_order(msg.symbol):
            log.warning(f"Pending order for {msg.symbol}; not submitting")
            if hasattr(self, "overlay") and self.overlay:
                self.overlay.flash_message(
                    f"Pending order for {msg.symbol}",
                    style="bold yellow",
                    duration=5.0,
                )
            return
        try:
            order = broker_tools.submit_order(
                BROKER_API,
                msg.symbol,
                msg.side,
                msg.price,
                self.trade_amount,
                self.auto_trading_enabled,
                qty=msg.qty,
                voice_agent=self.voice_agent,
                buy_sound_path=BUY_SOUND_PATH,
                sell_sound_path=SELL_SOUND_PATH,
            )
            cache.attach_order_to_last_signal(
                self.strategy_signals,
                msg.symbol.upper(),
                msg.side.name.lower(),
                order,
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
                if "buy_signals" not in df.columns:
                    df["buy_signals"] = None
                df.at[last_ts, "buy_signals"] = True
            elif msg.side == OrderSide.SELL:
                if "sell_signals" not in df.columns:
                    df["sell_signals"] = None
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
                    os.getenv("PAPER_API_KEY", "") == ""
                    or os.getenv("PAPER_SECRET", "") == "",
                    self.auto_trading_enabled,
                    self.set_auto_trading,
                    self.afterhours_enabled,
                    self.set_afterhours,
                    BROKER_API.get_balance,
                    BROKER_API.get_positions,
                    equity_data=self._equity_curve_data,
                    trade_amount=self.trade_amount,
                    set_trade_amount_cb=self.set_trade_amount,
                )
            )

    # --------------

    def update_view(self, symbol: str):
        self.overlay.symbol = symbol

        df = self.df_cache.get(symbol)
        if df is not None and not self.is_backtest:
            self.symbol_view = self.query_one("#symbol-view", SymbolView)
            indicators = (
                self.strategy_class.get_indicators()
                if self.strategy_class is not None
                else []
            )
            self.symbol_view.load_df(symbol, df, self.args, indicators)

        self.update_status_bar()
        if self.query("#splash") and df is not None:
            self.remove(self.query_one("#splash"))

    def update_status_bar(self):
        live_icon = "🤖" if self.auto_trading_enabled else "🚫"
        if self.auto_trading_enabled:
            auto_trade_state = (
                f"Auto-Trades: [BOLD GREEN]ENABLED[/BOLD GREEN] {live_icon}"
            )
        else:
            auto_trade_state = f"Auto-Trades: [BOLD RED]DISABLED[/BOLD RED] {live_icon}"

        overlay = self.overlay
        overlay.symbol = self.ticker_symbols[self.active_symbol_index]
        overlay.live_icon = live_icon
        if self.strategy_name:
            status = "ACTIVE" if self.strategy_active else "INACTIVE"
            strat_status = f"{self.strategy_name} ({status})"
        else:
            strat_status = "NO STRATEGY (INACTIVE)"
        overlay.update_status(
            f"{self.active_symbol_index + 1} / {len(self.ticker_symbols)} | {strat_status} | {auto_trade_state}"
        )

    def flash_message(self, msg: str):
        overlay = self.overlay
        overlay.flash_message(f"ORDER FAILED: {msg}", 10)

    def set_real_trades(self, enabled: bool) -> None:
        """Update trading mode for the app and broker."""
        self.args.real_trades = enabled
        if hasattr(BROKER_API, "_real_trades"):
            setattr(BROKER_API, "_real_trades", enabled)

    def set_auto_trading(self, enabled: bool) -> None:
        """Enable or disable auto trading mode."""
        self.auto_trading_enabled = enabled
        if enabled:
            self.set_strategy_active(True)
        # Update the portfolio screen toggle if it's currently visible
        if self.screen_stack and isinstance(self.screen_stack[-1], PortfolioScreen):
            screen = self.screen_stack[-1]
            screen.auto_trading_enabled = enabled
            screen.auto_switch.value = enabled
        self.update_status_bar()

    def set_afterhours(self, enabled: bool) -> None:
        """Enable or disable afterhours trading."""
        self.afterhours_enabled = enabled
        if self.screen_stack and isinstance(self.screen_stack[-1], PortfolioScreen):
            screen = self.screen_stack[-1]
            screen.afterhours_enabled = enabled
            screen.afterhours_switch.value = enabled
        self.update_status_bar()

    def set_strategy_active(self, enabled: bool) -> None:
        """Enable or disable strategy signal generation."""
        self.strategy_active = enabled
        self.update_status_bar()

    def set_trade_amount(self, amount: float) -> None:
        """Persist the trade amount value used for BUY orders."""
        try:
            self.trade_amount = float(amount)
        except ValueError:
            self.trade_amount = 0.0
        cache.save_trade_amount(self.trade_amount)
        self.update_status_bar()

    def set_strategy(self, name: str | None) -> None:
        """Change the active trading strategy."""
        if not name:
            self.strategy_name = None
            self.strategy_class = None
            cache.save_selected_strategy(None)
            self.update_status_bar()
            return
        if name not in self.available_strategies:
            log.error(f"Unknown strategy: {name}")
            return
        self.strategy_name = name
        self.strategy_class = load_strategy(name)
        cache.save_selected_strategy(name)

        # Re-analyze any cached data using the newly selected strategy
        specs = self.strategy_class.get_indicators()
        for sym, df in list(self.df_cache.items()):
            if df is not None and not df.empty:
                try:
                    self.df_cache[sym] = metrics.analyze_indicators(df, specs)
                except Exception:
                    log.error("Failed to update indicators for %s", sym)

        current = self.ticker_symbols[self.active_symbol_index]
        self.update_view(current)
        self.update_status_bar()

    def set_scanner(self, name: str) -> None:
        """Change the active scanner implementation."""
        if name not in self.available_scanners:
            log.error(f"Unknown scanner: {name}")
            return
        self.scanner_name = name
        self.scanner_class = load_scanner(name)
        cache.save_selected_scanner(name)
        # stop old worker if running
        if self._scanner_worker:
            self._scanner_worker.cancel()
            self._scanner_worker = None
        self.scanner = self.scanner_class(DATA_API, self.exit_event)
        self._scanner_worker = self.run_worker(self.scanner.scanner_loop, thread=False)

    def add_symbol(self, symbol: str) -> list[str]:
        """Append *symbol* to ``ticker_symbols`` and return the updated list."""
        sym = symbol.strip().upper()
        if not sym:
            return self.ticker_symbols
        if sym not in self.ticker_symbols:
            self.ticker_symbols.append(sym)
            self._prepend_open_positions()
            self.args.symbols = self.ticker_symbols
            self.df_cache.setdefault(sym, pd.DataFrame())
            cache.save_symbols_cache(self.ticker_symbols)
            self.overlay.flash_message(f"Added {sym}", duration=5.0, style="bold green")
        return self.ticker_symbols

    def remove_symbol(self, symbol: str) -> list[str]:
        """Remove *symbol* from ``ticker_symbols`` and return the updated list."""
        sym = symbol.strip().upper()
        if sym in self.ticker_symbols:
            if BROKER_API.has_position(sym):
                msg = (
                    f"I'm sorry, you currently have an open position for {sym}. "
                    "If we remove it from the watchlist we could miss a sell signal."
                )
                self.voice_agent.say(msg)
                self.overlay.flash_message(
                    f"Failed to remove {sym}, has open position!",
                    duration=6.0,
                    style="bold red",
                )
                return self.ticker_symbols

            self.ticker_symbols.remove(sym)
            self.df_cache.pop(sym, None)
            if self.active_symbol_index >= len(self.ticker_symbols):
                self.active_symbol_index = max(0, len(self.ticker_symbols) - 1)
            self.args.symbols = self.ticker_symbols
            cache.save_symbols_cache(self.ticker_symbols)
            if self.ticker_symbols:
                self.update_view(self.ticker_symbols[self.active_symbol_index])
            self.overlay.flash_message(
                f"Removed {sym} from watchlist.",
                duration=5.0,
                style="bold yellow",
            )
        return self.ticker_symbols

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
        if self.strategy_class is None:
            self.overlay.flash_message("No active strategy", style="bold red")
            return
        try:
            log.debug("Backtest starting...")
            overlay = self.overlay
            overlay.update_status("Running backtest...")
            symbol = form["symbol"]
            starting_cash = float(form["cash"])

            # Fetch historical bars
            df, _ = await asyncio.to_thread(
                get_historical_data,
                DATA_API,
                self.config.bb_period,
                self.config.bb_dev,
                self.config.macd_thresh,
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
                run_backtest,
                df,
                symbol,
                self.config,
                self.strategy_class,
                starting_cash,
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
                trades.append(
                    {
                        **rec,
                        "value": equity_lookup.get(t),
                    }
                )
            trades.sort(key=lambda r: r["time"])
            self._last_backtest_trades = trades
            log.debug(f"trades: {trades}")

            overlay.update_status(
                f"Backtest completed. Final portfolio value: ${result['final_value']:,.2f} | Buy count: {num_buys}"
            )
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
                    indicators=(
                        self.strategy_class.get_indicators()
                        if self.strategy_class is not None
                        else []
                    ),
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
            self.overlay.flash_message(f"Back-test error: {exc}", style="bold red")
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


BROKER_API = None
DATA_API = None


from .cli import main


if __name__ == "__main__":
    main()
