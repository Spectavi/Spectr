import argparse
import asyncio
import logging
import traceback

import backtrader as bt
import pandas as pd
import playsound
from dotenv import load_dotenv
from textual.app import App, ComposeResult
from textual.reactive import reactive
import threading, queue, time

import metrics
import utils
from custom_strategy import SignalStrategy
from fetch.broker_interface import BrokerInterface
from utils import load_cache, save_cache
from views.graph_view import GraphView
from views.macd_view import MACDView
from views.ticker_input_dialog import TickerInputDialog
from views.top_overlay import TopOverlay

# --- SOUND PATHS ---
BUY_SOUND_PATH = 'res/buy.mp3'
SELL_SOUND_PATH = 'res/sell.mp3'

REFRESH_INTERVAL = 5  # seconds

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
    ]

    ticker_symbols = reactive([])
    active_symbol_index = reactive(0)
    auto_trading_enabled: reactive[bool] = reactive(False)
    strategies = reactive({})

    graph: reactive[GraphView] = reactive(None)
    macd: reactive[MACDView] = reactive(None)

    def __init__(self, args):
        super().__init__()
        self.args = args  # Store CLI arguments
        self.macd_thresh = self.args.macd_thresh
        self.bb_period = self.args.bb_period
        self.bb_dev = self.args.bb_dev
        self.df_cache = {symbol: pd.DataFrame() for symbol in self.ticker_symbols}

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

        log.debug(f"App mounted in mode: {self.args.mode}")
        # Kick off producer & consumer
        threading.Thread(target=self._polling_loop,
                         name="data-poller",
                         daemon=True).start()
        asyncio.create_task(self._process_updates())  # async consumer

        # Step 1: Fetch data for all symbols and store in df_cache
        for symbol in self.ticker_symbols:
            try:
                df, quote = await asyncio.to_thread(self.get_live_data, symbol)
                if df.empty or quote is None:
                    log.error(f"No data for {symbol}")
                    continue

                df = utils.inject_quote_into_df(df, quote)
                df = metrics.analyze_indicators(df, self.bb_period, self.bb_dev, self.macd_thresh)
                self.df_cache[symbol] = df
                strat = SignalStrategy()
                strat.symbol = symbol
                self.strategies[symbol] = SignalStrategy

            except Exception as e:
                log.error(f"[on_mount] Failed to fetch data for {symbol}: {e}")

        self.update_status_bar()
        asyncio.create_task(self.update_data_loop())

    def _polling_loop(self) -> None:
        """Runs in *native* thread; never touches the UI directly."""
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

                    df["signal"] = None
                    log.debug("Detecting live signals...")
                    signal_dict = SignalStrategy.detect_signals(df, symbol,
                                                                BROKER_API.get_position(self.args.symbol,
                                                                                        self.args.real_trades))
                    log.debug("Detect signals finished.")

                    # Check for signal
                    signal = signal_dict['signal']
                    curr_price = quote.get("price")
                    if signal:
                        log.debug(f"Signal detected for {symbol}.")
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
                df = self.df_cache.get(symbol)
                if df is not None:
                    self.graph.df = df
                    self.macd.df = df
                    self.graph.refresh()
                    self.macd.refresh()
                    self.refresh()

    async def on_shutdown(self):
        self._stop_event.set()  # stop the producer
        await asyncio.to_thread(self._update_queue.put, None)  # unblock consumer
        log.debug("Shutting down...")
        if hasattr(self, "graph") and hasattr(self.graph, "df"):
            save_cache(self.graph.df, self.args.mode)
            log.debug("Cache saved.")
        else:
            log.debug("Cache not saved.")


    ### Action Functions ###

    def action_select_symbol(self, key: str):
        index = (int(key) - 1) if key != "0" else 9

        if index < len(self.ticker_symbols):
            self.active_symbol_index = index
            symbol = self.ticker_symbols[index]
            log.debug(f"action selected symbol: {symbol}")
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
        self.update_view(symbol)


    ### ------------------------------------------------- ###

    def update_view(self, symbol: str):
        self.query_one("#graph", GraphView).symbol = symbol  # Update graph title
        self.query_one("#overlay-text", TopOverlay).symbol = symbol

        if self.df_cache.get(symbol) is not None:
            self.query_one("#graph", GraphView).df = self.df_cache.get(symbol)
            self.query_one('#macd-view', MACDView).df = self.df_cache.get(symbol)
        else:
            self.query_one("#graph", GraphView).df = None
            self.query_one('#macd-view', MACDView).df = None

        self.update_status_bar()
        asyncio.create_task(self.update_data_loop())  # Restart fetch/update loop

    def update_status_bar(self):
        live_icon = "🤖" if self.auto_trading_enabled else "🚫"
        if self.auto_trading_enabled:
            auto_trade_state = f"Auto-Trades: [BOLD GREEN]ENABLED[/BOLD GREEN] {live_icon}"
        else:
            auto_trade_state = f"Auto-Trades: [BOLD RED]DISABLED[/BOLD RED] {live_icon}"

        overlay = self.query_one("#overlay-text", TopOverlay)
        overlay.symbol = self.ticker_symbols[self.active_symbol_index]
        overlay.update_status(
            f"Mode: {self.args.mode} | {self.active_symbol_index + 1} / {len(self.ticker_symbols) + 1} | {auto_trade_state}"
        )

    def run_backtest(df, symbol, bb_period, bb_dev, macd_thresh):
        cerebro = bt.Cerebro()
        cerebro.addstrategy(SignalStrategy, symbol=symbol, bb_period=bb_period, bb_dev=bb_dev, macd_thresh=macd_thresh)

        data = bt.feeds.PandasData(dataname=df)
        cerebro.adddata(data)

        cerebro.broker.setcash(10000.0)
        cerebro.broker.addcommissioninfo(CommInfoFractional())
        cerebro.broker.setcommission(commission=0.00)
        cerebro.addsizer(bt.sizers.AllInSizer, percents=100)

        log.debug(f"Starting Portfolio Value: {cerebro.broker.getvalue():.2f}")
        results = cerebro.run()
        log.debug(f"Final Portfolio Value: {cerebro.broker.getvalue():.2f}")
        # cerebro.plot() # Hawk TUI!

        # Extract trades
        trades = []
        strat = results[0]
        log.debug(f"strat: {strat}")
        for i in range(len(strat)):
            if hasattr(strat, 'buy_signals') and strat.buy_signals:
                trades.extend(strat.buy_signals)

        # Generate equity curve
        portfolio_values = [strat.broker.get_value()]  # or track each day manually
        timestamps = df.index.tolist()
        equity_curve = list(zip(timestamps, portfolio_values))

        return {
            'final_value': cerebro.broker.getvalue(),
            'trades': trades,
            'equity_curve': equity_curve,
            'price_data': df[['close']].copy(),
            'timestamps': timestamps,
            'buys': strat.buy_signals,
            'sells': strat.sell_signals,
        }

    def get_live_data(self, symbol):
        log.debug(f"Fetching live data for {symbol}...")
        df = DATA_API.fetch_chart_data(symbol, lookback=self.args.lookback_period)
        quote = DATA_API.fetch_quote(symbol)
        return df, quote

    async def update_data_loop(self):
        while True:
            try:
                signal_detected = []
                overlay = self.query_one("#overlay-text", TopOverlay)

                # Batch update all symbols
                for symbol in self.ticker_symbols:
                    try:
                        df, quote = await asyncio.to_thread(self.get_live_data, symbol)
                        log.debug(f"Fetched live data.")
                        log.debug(f"Quote: {quote}")
                        curr_price = quote.get("price")

                        # Create live row
                        log.debug("Injecting latest quote data...")
                        df = utils.inject_quote_into_df(df, quote)
                        log.debug("Injected latest quote data.")

                        latest_row = df.iloc[-1]

                        log.debug("Analyzing indicators...")
                        df = metrics.analyze_indicators(df, self.args.bb_period, self.args.bb_dev, self.args.macd_thresh)

                        df["signal"] = None
                        log.debug("Detecting live signals...")
                        signal_dict = SignalStrategy.detect_signals(df, symbol,
                                                                    BROKER_API.get_position(self.args.symbol,
                                                                                            self.args.real_trades))
                        log.debug("Detect signals finished.")
                        signal = signal_dict['signal']
                        price = signal_dict['price']

                        # Check for signal
                        if signal:
                            log.debug(f"Signal detected for {symbol}.")
                            self.update_view(symbol)
                            if signal == "buy":
                                log.debug("Buy signal detected!")
                                signal_detected.append((symbol, curr_price, signal))
                                playsound.playsound(BUY_SOUND_PATH)
                            elif signal == "sell":
                                log.debug("Buy signal detected!")
                                signal_detected.append((symbol, curr_price, signal))
                                playsound.playsound(SELL_SOUND_PATH)

                        # Update current df
                        self.df_cache[symbol] = df

                    except Exception as e:
                        log.debug(f"[ERROR] Symbol {symbol}: {e}")

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
                        overlay.flash_message(msg, style="bold green")
                        playsound.playsound(BUY_SOUND_PATH if sig == "buy" else SELL_SOUND_PATH)
                        await asyncio.sleep(5)

                # Update current symbol's UI
                df = self.df_cache.get(symbol)
                print(f"Loading df_cache for views: {symbol}")
                if df is not None:
                    self.graph.df = df
                    self.graph.symbol = symbol
                    self.macd.df = df
                    self.graph.refresh()
                    self.macd.refresh()

                self.refresh()

            except Exception as e:
                log.debug(f"[ERROR] update_data_loop: {traceback.format_exc()}")
                self.query_one("#overlay-text", TopOverlay).flash_message("Live error", style="bold red")
                self.graph.update(f"Error: {e}")
                if self.args.mode == "backtest":
                    exit(1)


            await asyncio.sleep(10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", type=str, default='AAPL,AMZN,META,MSFT,NVDA,TSLA,GOOG,VTI,GLD', help="List of ticker symbols (e.g. NVDA,TSLA,AAPL)")
    parser.add_argument("--candles", action="store_true", help="Show candlestick chart.")
    parser.add_argument("--macd_thresh", type=float, default=0.002, help="MACD threshold")
    parser.add_argument("--bb_period", type=int, default=200, help="Bollinger Band period")
    parser.add_argument("--bb_dev", type=float, default=2.0, help="Bollinger Band std dev")
    parser.add_argument("--real_trades", action='store_true', help="Enable live trading (vs paper)")
    parser.add_argument('--interval', default='1m')
    parser.add_argument('--mode', choices=['live', 'backtest'], required=True)
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

