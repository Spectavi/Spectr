import argparse
import asyncio
import logging

import backtrader as bt
import playsound
from dotenv import load_dotenv
from textual.app import App, ComposeResult
from textual.reactive import reactive

from custom_strategy import SignalStrategy
from fetch.broker_interface import BrokerInterface
from metrics import analyze_indicators
from multi_symbol_screen import MultiSymbolScreen
from utils import load_cache, save_cache
from views.graph_view import GraphView
from views.macd_view import MACDView
from views.multi_ticker_input_dialog import MultiTickerInputDialog
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
        #("s", "prompt_multi_symbols", "Load Multiple Symbols"),  # ⬅️ New!
    ]

    auto_trading_enabled: reactive[bool] = reactive(False)
    graph: reactive[GraphView] = reactive(None)
    macd: reactive[MACDView] = reactive(None)

    def __init__(self, args):
        super().__init__()
        self.args = args  # Store CLI arguments
        self.symbol = self.args.symbol
        self.symbols = self.args.symbols
        self.macd_thresh = self.args.macd_thresh
        self.bb_period = self.args.bb_period
        self.bb_dev = self.args.bb_dev

    def compose(self) -> ComposeResult:
        yield TopOverlay(id="overlay-text")
        yield GraphView(id="graph")
        yield MACDView(id="macd-view")

    async def on_mount(self):
        overlay = self.query_one("#overlay-text", TopOverlay)
        overlay.symbol = self.symbol
        overlay.set_auto_trading_mode(self.auto_trading_enabled)
        if self.auto_trading_enabled:
            overlay.update_status(f"{self.symbol} | Auto-Trades: ENABLED", style="red")
        else:
            overlay.update_status(f"{self.symbol} | Auto-Trades: DISABLED", style="green")

        self.graph = self.query_one("#graph", GraphView)
        self.macd = self.query_one("#macd-view", MACDView)
        if self.args.symbol:
            self.query_one("#graph", GraphView).symbol = self.symbol  # Update graph title

        self.graph.args = self.args
        self.macd.args = self.args

        log.debug(f"App mounted in mode: {self.args.mode}")

        # Try to load cache
        cached_df = load_cache(self.args.mode)
        if cached_df is not None:
            log.debug("Loading from cache...")
            self.graph.df = cached_df
            self.macd.df = cached_df
            self.graph.refresh()
            self.macd.refresh()

        asyncio.create_task(self.update_data_loop())

    async def on_shutdown(self):
        log.debug("Shutting down...")
        if hasattr(self, "graph") and hasattr(self.graph, "df"):
            save_cache(self.graph.df, self.args.mode)
            log.debug("Cache saved.")
        else:
            log.debug("Cache not saved.")

    def action_arm_auto_trading(self):
        self.auto_trading_enabled = not self.auto_trading_enabled
        self.query_one("#overlay-text", TopOverlay).set_auto_trading_mode(self.auto_trading_enabled)

        # self.query_one("#overlay-text", TopOverlay).flash_message(
        #     f"Auto Trading {'AUTO-TRADES ON ✅' if self.auto_trading_enabled else 'AUTO-TRADES OFF 🚫'}",
        #     style="bold yellow"
        # )

    def action_prompt_multi_symbols(self):
        self.auto_trading_enabled = False
        self.query_one("#overlay-text", TopOverlay).set_auto_trading_mode(self.auto_trading_enabled)
        self.push_screen(MultiTickerInputDialog(callback=self.on_multi_ticker_submit))

    def on_multi_ticker_submit(self, symbols: list[str]):
        self.symbols = symbols
        self.push_screen(MultiSymbolScreen(symbols, self.args))

    def action_prompt_symbol(self):
        self.auto_trading_enabled = False
        self.query_one("#overlay-text", TopOverlay).set_auto_trading_mode(self.auto_trading_enabled)
        self.push_screen(TickerInputDialog(callback=self.on_ticker_submit))

    def on_ticker_submit(self, symbol: str):
        self.symbol = symbol  # Update the symbol used by the app
        self.query_one("#graph", GraphView).df = None  # Clear graph
        self.query_one("#graph", GraphView).symbol = symbol  # Update graph title
        self.query_one("#overlay-text", TopOverlay).symbol = symbol
        self.query_one("#overlay-text", TopOverlay).update_status(f"🔄 Loading {symbol}...")
        asyncio.create_task(self.update_data_loop())  # Restart fetch/update loop

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

    async def update_data_loop(self):
        while True:
            try:
                df = None
                if args.mode == "live":
                    log.debug("Fetching live data...")
                    df = DATA_API.fetch_data(self.symbol, self.args.lookback_period, self.args.real_trades)
                elif args.mode == "backtest":
                    log.debug("Fetching backtest data...")
                    df = DATA_API.fetch_data_for_backtest(self.symbol, self.args.from_date, self.args.to_date)
                    #df.dropna(inplace=True)

                if df.empty:
                    log.error("Error: No data fetched!")
                    self.query_one("#overlay-text", TopOverlay).update_status(f"⛔ {self.symbol} failed to load!", style='red')
                else:
                    log.debug(f"Data fetched:\n{df}")

                log.debug("Analyzing indicators...")
                df = analyze_indicators(df, self.bb_period, self.bb_dev, self.macd_thresh)

                if self.args.mode == "live":
                    df["signal"] = None
                    log.debug("Detecting live signals...")
                    signal_dict = SignalStrategy.detect_signals(df, self.symbol, BROKER_API.get_position(self.args.symbol, self.args.real_trades))
                    log.debug("Detect signals finished.")
                    signal = signal_dict['signal']
                    price = signal_dict['price']
                    if not self.auto_trading_enabled:
                        log.debug("Auto-trading DISABLED.")
                    if signal:
                        log.debug("Signal detected!")
                        overlay = self.query_one("#overlay-text", TopOverlay)
                        if self.auto_trading_enabled:
                            if signal == "buy":
                                overlay.flash_message(f"BUY @ {price} 🚀", style="bold green")
                                playsound.playsound(BUY_SOUND_PATH)
                            elif signal == "sell":
                                overlay.flash_message(f"SELL @ {price} ⚠️", style="bold red")
                                playsound.playsound(SELL_SOUND_PATH)
                            df.at[df.index[-1], "signal"] = signal
                        else:
                            if signal == "buy":
                                overlay.flash_message(f"**AUTO-TRADES DISABLED** BUY @ {price} 🚀", style="bold green")
                                playsound.playsound(BUY_SOUND_PATH)
                            elif signal == "sell":
                                overlay.flash_message(f"**AUTO-TRADES DISABLED** SELL @ {price} ⚠️", style="bold red")
                                playsound.playsound(SELL_SOUND_PATH)
                elif self.args.mode == "backtest":
                    log.debug("Running backtest...")
                    results = self.run_backtest(df, self.symbol, self.args.bb_period,
                                                self.args.bb_dev, self.args.macd_thresh)
                    log.debug("Backtest completed!")
                    # TODO: Add in trade info.
                    # TODO: Graph the indicators.

                self.graph.df = df
                self.macd.df = df
                self.refresh()
                self.graph.refresh()
                self.macd.refresh()
                self.query_one("#overlay-text", TopOverlay).set_auto_trading_mode(self.auto_trading_enabled)
                log.debug("Views refreshed.")

            except Exception as e:
                log.debug(f"[ERROR] update_data_loop: {e}")
                overlay = self.query_one("#overlay-text", TopOverlay)
                #overlay.flash_message("ERROR! See debug.log for details. ⚠️", style="bold red")
                self.graph.update(f"Error: {e}")
                if self.args.mode == "backtest":
                    exit(1)

            if args.mode == "live":
                await asyncio.sleep(REFRESH_INTERVAL)
            elif args.mode == "backtest":
                break



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", type=str, default='NVDA', help="Ticker symbol (e.g. AAPL)")
    parser.add_argument("--symbols", type=str, default='NVDA,TSLA,GOOG', help="List of ticker symbols (e.g. NVDA,TSLA,GOOG)")
    parser.add_argument("--candles", type=bool, default=True, help="Show candles data")
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
    parser.add_argument("--broker", type=str, choices=["alpaca", "robinhood"], default="alpaca",
        help="Choose which broker to use (Alpaca, Robinhood)"
    )
    parser.add_argument("--data_api", type=str, choices=["alpaca", "robinhood", "fmp"], default="alpaca",
        help="Choose which data provider to use (Alpaca, Robinhood, or FMP)"
    )
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()

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
        DATA_API = AlpacaInterface()
    elif args.data_api == "robinhood":
        from fetch.robinhood import RobinhoodInterface
        DATA_API = RobinhoodInterface()
    elif args.data_api == "fmp":
        from fetch.fmp import FMPInterface
        DATA_API = FMPInterface()

    app = SpectrApp(args)
    app.run()

