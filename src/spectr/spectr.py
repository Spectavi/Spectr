import argparse
import asyncio
import logging
import os
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import backtrader as bt
import pandas as pd
import playsound
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from textual import events
from textual.app import App, ComposeResult
from textual.reactive import reactive
import threading, queue, time

import metrics
import utils
from CustomStrategy import CustomStrategy
from fetch.broker_interface import BrokerInterface
from views.trades_screen import TradesScreen
from views.backtest_input_dialog import BacktestInputDialog
from utils import load_cache, save_cache
from views.graph_view import GraphView
from views.macd_view import MACDView
from views.ticker_input_dialog import TickerInputDialog
from views.top_overlay import TopOverlay

# --- SOUND PATHS ---
BUY_SOUND_PATH = 'res/buy.mp3'
SELL_SOUND_PATH = 'res/sell.mp3'

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

# --- Backtest Function ---
class CommInfoFractional(bt.CommissionInfo):
    def getsize(self, price, cash):
        """Returns fractional size for cash operation @price"""
        return self.p.leverage * (cash / price)

class SpectrApp(App):
    CSS_PATH = "default.tcss"
    BINDINGS = [
        ("escape", "quit", "Quit"),
        ("t", "prompt_symbol", "Change Ticker"), # T key
        ("`", "prompt_symbol", "Change Ticker"),  # ~ key
        ("ctrl+a", "arm_auto_trading", "Arms Auto-Trading - REAL trades will occur!"),
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
        ("b", "prompt_backtest", "Back-test"),
        ("tab", "toggle_trades", "Trades Table"),
    ]

    ticker_symbols = reactive([])
    active_symbol_index = reactive(0)
    auto_trading_enabled: reactive[bool] = reactive(False)
    # strategies = reactive({})
    is_backtest: reactive[bool] = reactive(False)  # ‹NEW› flag

    graph: reactive[GraphView] = reactive(None)
    macd: reactive[MACDView] = reactive(None)

    def __init__(self, args):
        super().__init__()
        self.args = args  # Store CLI arguments
        self.macd_thresh = self.args.macd_thresh
        self.bb_period = self.args.bb_period
        self.bb_dev = self.args.bb_dev
        self.df_cache = {symbol: pd.DataFrame() for symbol in self.ticker_symbols}
        if not os.path.exists(utils.CACHE_DIR):
            os.mkdir(utils.CACHE_DIR)

        self._update_queue: queue.Queue[str] = queue.Queue()
        self._stop_event = threading.Event()

    def compose(self) -> ComposeResult:
        yield TopOverlay(id="overlay-text")
        yield GraphView(id="graph")
        yield MACDView(id="macd-view")


    async def on_mount(self):
        # Set symbols and active symbol
        self.ticker_symbols = self.args.symbols
        self.active_symbol_index = 0
        symbol = self.ticker_symbols[0]
        log.debug(f"self.ticker_symbols: {self.ticker_symbols}")
        log.debug(f"self.active_symbol_index: {self.active_symbol_index}")
        log.debug(f"symbol: {symbol}")

        # Populate view with active symbols data.
        self.graph = self.query_one("#graph", GraphView)
        self.macd = self.query_one("#macd-view", MACDView)
        self.graph.symbol = symbol  # Update graph title
        self.graph.args = self.args
        self.macd.args = self.args

        log.debug("App mounted.")
        today = datetime.now().date()
        # Step 1: Fetch data for all symbols and store in df_cache
        for symbol in self.ticker_symbols:
            cache = load_cache(symbol)
            if not cache.empty:
                log.debug(f"Loaded cache: {symbol}")

                last_bar_date = cache.index.max().date()
                if last_bar_date <= today:
                    # Pull only the missing slice [last_bar_date .. today]
                    df_new, quote_new = await asyncio.to_thread(
                        self.get_historical_data,
                        symbol,
                        from_date=last_bar_date.strftime("%Y-%m-%d"),
                        to_date=today.strftime("%Y-%m-%d"),
                    )
            else:
                df_new, quote_new = await asyncio.to_thread(
                        self.get_historical_data,
                        symbol,
                        from_date=today - timedelta(days=365),
                        to_date=today.strftime("%Y-%m-%d"),
                    )
                if df_new.empty:
                    log.error(f"No data for {symbol}")
                    continue


            if not df_new.empty and quote_new is not None:
                df_new = utils.inject_quote_into_df(df_new, quote_new)

                # Merge & dedupe
                combined = pd.concat([cache, df_new])
                df_new = combined[~combined.index.duplicated(keep="last")].sort_index()
                log.info(f"Cache for {symbol} extended to {df_new.index.max().date()}")


            self.df_cache[symbol] = df_new
            save_cache(symbol, df_new)

        # Kick off producer & consumer
        threading.Thread(target=self._polling_loop,
                         name="data-poller",
                         daemon=True).start()
        self.update_status_bar()
        asyncio.create_task(self._process_updates())  # async consumer

    def get_live_data(self, symbol):
        log.debug(f"Fetching live data for {symbol}...")
        df = DATA_API.fetch_chart_data(symbol, from_date=datetime.now().date(), to_date=datetime.now().date())
        quote = DATA_API.fetch_quote(symbol)
        return df, quote

    # def get_historical_data(self, symbol, from_date, to_date):
    #     log.debug(f"Fetching historical data for {symbol}...")
    #     df = DATA_API.fetch_chart_data(symbol, from_date=from_date, to_date=to_date)
    #     df = metrics.analyze_indicators(df, self.bb_period, self.bb_dev, self.macd_thresh)
    #     quote = DATA_API.fetch_quote(symbol)
    #     return df, quote

    # Grabs 1-day more than requested, calculates indicators, then trims to requested range.
    def get_historical_data(self, symbol: str, from_date: str, to_date: str):
        """
        Fetch OHLCV + quote for *symbol* in [from_date .. to_date] **inclusive**,
        but ensure that indicators that need a look-back window are fully
        initialised by pulling an extra day of data before `from_date`.
        """
        log.debug(f"Fetching historical data for {symbol}…")

        # ➊ Extend the request one calendar day back
        dt_from = datetime.strptime(from_date, "%Y-%m-%d").date()
        extended_from = (dt_from - timedelta(days=1)).strftime("%Y-%m-%d")
        log.debug(f"dt_from: {dt_from}")
        log.debug(f"extended_from: {extended_from}")

        # ➋ Pull the data and quote
        df = DATA_API.fetch_chart_data_for_backtest(symbol, from_date=extended_from, to_date=to_date)
        if df.empty:
            df = DATA_API.fetch_chart_data_for_backtest(symbol, from_date=extended_from, to_date=to_date, interval="5min")
        # ➌ Compute indicators on the *full* frame (needs the extra bar)
        df = metrics.analyze_indicators(df, self.bb_period, self.bb_dev, self.macd_thresh)
        try:
            quote = DATA_API.fetch_quote(symbol)
        except Exception:
            log.warning(f"Failed to fetch quote for {symbol}")

        # ➍ Trim back to the exact range the caller requested
        df = df.loc[from_date:to_date]  # string slice → inclusive

        return df, quote if quote else None

    def _polling_loop(self) -> None:
        """Runs in *native* thread; never touches the UI directly."""
        if self.is_backtest:  # ← back-tests freeze live updates
            return  # simply skip this tick and try again next time
        while not self._stop_event.is_set():
            signal_detected = []
            for symbol in self.ticker_symbols:
                try:
                    df, quote = self.get_live_data(symbol)
                    if df.empty or quote is None:
                        continue

                    df = utils.inject_quote_into_df(df, quote)
                    df = metrics.analyze_indicators(df,
                                                    self.bb_period,
                                                    self.bb_dev,
                                                    self.macd_thresh)
                    df['trade'] = None
                    df["signal"] = None
                    log.debug("Detecting live signals...")
                    signal_dict = CustomStrategy.detect_signals(df, symbol,
                                                                BROKER_API.get_position(self.args.symbol,
                                                                                        self.args.real_trades))
                    log.debug("Detect signals finished.")

                    # Check for signal
                    signal = signal_dict['signal']
                    curr_price = quote.get("price")
                    if signal:
                        log.debug(f"Signal detected for {symbol}.")
                        df.at[df.index[-1], 'trade'] = signal  # mark bar for plotting
                        self.update_view(symbol)
                        if signal == "buy":
                            log.debug("Buy signal detected!")
                            signal_detected.append((symbol, curr_price, signal))
                            playsound.playsound(BUY_SOUND_PATH)
                        elif signal == "sell":
                            log.debug("Sell signal detected!")
                            signal_detected.append((symbol, curr_price, signal))
                            playsound.playsound(SELL_SOUND_PATH)

                    # Update current df
                    self.df_cache[symbol] = df  # thread-safe – dict ops are atomic
                    self._update_queue.put(symbol)  # notify main loop
                except Exception as exc:
                    log.error(f"[poll] {symbol}: {exc}")

            symbol = self.ticker_symbols[self.active_symbol_index]
            # If a buy signal was triggered, switch to that symbol
            if len(signal_detected) > 0:
                for signal in signal_detected:
                    sym, price, sig = signal
                    index = self.ticker_symbols.index(sym)
                    self.active_symbol_index = index
                    self.update_view(sym)
                    msg = f"{sym} @ {price} 🚀"
                    if sig == 'buy':
                        msg = f"BUY {msg}"
                    if sig == 'sell':
                        msg = f"SELL {msg}"

                    if not self.auto_trading_enabled:
                        msg = f"AUTO DISABLED! {msg}"
                    else:
                        msg = f"ORDER SUBMITTED! {msg}"
                        if not self.args.real_trades:
                            msg = f"PAPER {msg}"
                        else:
                            msg = f"REAL {msg}"
                        BROKER_API.submit_order(symbol, signal, 1, self.args.real_trades)

                    overlay = self.query_one("#overlay-text", TopOverlay)
                    overlay.flash_message(msg, style="bold green")
                    playsound.playsound(BUY_SOUND_PATH if sig == "buy" else SELL_SOUND_PATH)
            time.sleep(REFRESH_INTERVAL)

    async def _process_updates(self) -> None:
        """Runs in Textual’s event loop; applies any fresh data to the UI."""
        while True:
            symbol: str = await asyncio.to_thread(self._update_queue.get)

            # If the update is for the symbol the user is currently looking at,
            # push it straight into the Graph/MACD views.
            if symbol == self.ticker_symbols[self.active_symbol_index]:
                if not self.is_backtest:
                    df = self.df_cache.get(symbol)
                    if df is not None:
                        self.graph.df = df
                        self.macd.df = df
                        self.graph.refresh()
                        self.macd.refresh()
                        self.refresh()

    # async def on_shutdown(self, event) -> None:
    #     self._stop_event.set()  # stop the producer
    #     await asyncio.to_thread(self._update_queue.put, None)  # unblock consumer
    #     log.debug("Shutting down...")
    #     save_cache(self.df_cache)
    #     log.debug("Cache saved.")
    #     sys.exit(0)

    ### Action Functions ###

    def action_select_symbol(self, key: str):
        self._exit_backtest()
        index = (int(key) - 1) if key != "0" else 9

        if index <= len(self.ticker_symbols)-1:
            self.active_symbol_index = index
            symbol = self.ticker_symbols[index]
            log.debug(f"action selected symbol: {symbol}")
            self._exit_backtest()
            self.update_view(symbol)

    def action_arm_auto_trading(self):
        self.auto_trading_enabled = not self.auto_trading_enabled
        self.update_status_bar()

    def action_prompt_symbol(self):
        self.auto_trading_enabled = False
        self.push_screen(TickerInputDialog(callback=self.on_ticker_submit))

    def on_ticker_submit(self, symbols: str):
        self.ticker_symbols = [x.strip().upper() for x in symbols.split(',')] # Update the symbol used by the app
        self.active_symbol_index = 0
        symbol = self.ticker_symbols[self.active_symbol_index]
        self.graph.df = None
        self.macd.df = None
        self.update_view(symbol)

    def action_toggle_trades(self) -> None:
        # Only meaningful after a back-test has just finished
        if getattr(self, "_last_backtest_trades", None):
            if self.screen_stack and isinstance(self.screen_stack[-1], TradesScreen):
                self.pop_screen()  # already open → close
            else:
                self.push_screen(TradesScreen(self._last_backtest_trades))

    def update_view(self, symbol: str):
        self.query_one("#graph", GraphView).symbol = symbol  # Update graph title
        self.query_one("#overlay-text", TopOverlay).symbol = symbol

        if self.df_cache.get(symbol) is not None and not self.is_backtest:
            self.query_one("#graph", GraphView).df = self.df_cache.get(symbol)
            self.query_one('#macd-view', MACDView).df = self.df_cache.get(symbol)

        self.update_status_bar()
        #asyncio.create_task(self.update_data_loop())  # Restart fetch/update loop

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

            overlay.update_status(f"Backtest completed. Final portfolio value: ${result['final_value']:,.2f} | Buy count: {num_buys}")
            price_df = result["price_data"].copy()

            buy_times = {sig["time"] for sig in result["buy_signals"]}
            sell_times = {sig["time"] for sig in result["sell_signals"]}

            price_df["buy_signals"] = price_df.index.isin(buy_times)
            price_df["sell_signals"] = price_df.index.isin(sell_times)
            # left-join adds open/high/low/volume from the original df
            df = df.join(price_df[["buy_signals", "sell_signals"]])

            # Switch the UI into back-test mode
            self.graph.is_backtest = True
            self.graph.df = df
            self.macd.is_backtest = True
            self.macd.df = df
            self.graph.symbol = symbol
            self.graph.refresh()
            self.macd.refresh()
            #self.update_view(symbol)

        except Exception as exc:
            self.query_one("#overlay-text", TopOverlay).flash_message(
                f"Back-test error: {exc}", style="bold red"
            )
            log.error("Back-test error: %s", traceback.format_exc())
            self.is_backtest = False

            # Turn is_backtest off for every graph shown.
            self.graph.is_backtest = False
            self.macd.is_backtest = False
            self.update_status_bar()

    def _exit_backtest(self) -> None:
        """Return to live data when the user presses 0-9."""
        self.is_backtest = False
        # Turn is_backtest off for every graph shown.
        self.graph.is_backtest = False
        self.macd.is_backtest = False

        current = self.ticker_symbols[self.active_symbol_index]
        self.update_view(current)

    def run_backtest(self, df, symbol, args, starting_cash=1000):
        cerebro = bt.Cerebro()
        cerebro.addstrategy(CustomStrategy, symbol=symbol, bb_period=args.bb_period, bb_dev=args.bb_dev, macd_thresh=args.macd_thresh, is_backtest=True)

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
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", type=str, default='AAPL,AMZN,META,MSFT,NVDA,TSLA,GOOG,VTI,GLD', help="List of ticker symbols (e.g. NVDA,TSLA,AAPL)")
    parser.add_argument("--candles", action="store_true", help="Show candlestick chart.")
    parser.add_argument("--macd_thresh", type=float, default=0.002, help="MACD threshold")
    parser.add_argument("--bb_period", type=int, default=170, help="Bollinger Band period")
    parser.add_argument("--bb_dev", type=float, default=2.0, help="Bollinger Band std dev")
    parser.add_argument("--real_trades", action='store_true', help="Enable live trading (vs paper)")
    parser.add_argument('--interval', default='1min')
    #parser.add_argument('--mode', choices=['live', 'backtest'], required=True)
    parser.add_argument('--from_date', default='2025-04-17')
    parser.add_argument('--to_date', default='2025-04-21')
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

    args.symbols = [s.strip().upper() for s in args.symbols.split(",")][:10]
    args.symbol = args.symbols[0]  # set initial active symbol
    log.debug(f"Loading symbols: {args.symbols}")

    # Loading from .env file
    load_dotenv()

    BROKER_API = None
    DATA_API = None

    if args.broker == "alpaca":
        from fetch.alpaca import AlpacaInterface
        BROKER_API: BrokerInterface = AlpacaInterface()
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
            DATA_API = AlpacaInterface()
    elif args.data_api == "robinhood":
        from fetch.robinhood import RobinhoodInterface
        if args.broker == "robinhood":
            DATA_API = BROKER_API
        else:
            DATA_API = RobinhoodInterface()
    elif args.data_api == "fmp":
        from fetch.fmp import FMPInterface, FMPDataFeed
        # FMP can only be a data_api, not valid for broker.
        DATA_API = FMPInterface()

    app = SpectrApp(args)
    app.run()
