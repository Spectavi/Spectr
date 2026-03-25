"""Symbol management helpers for SpectrApp."""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .spectr import SpectrApp

from .service_modules import StrategyService

log = logging.getLogger(__name__)

BUY_SOUND_PATH = "res/buy.mp3"
SELL_SOUND_PATH = "res/sell.mp3"
INTRO_SOUND_PATH = "res/intro.mp3"
ORDER_SUCCESS_SOUND_PATH = "res/order_success.mp3"


class SymbolManager:
    """Handles symbol-related operations and validation."""

    def __init__(self, app: "SpectrApp"):
        self.app = app

    def get_active_symbol(self) -> str | None:
        if not self.app.ticker_symbols:
            return None
        if not (0 <= self.app.active_symbol_index < len(self.app.ticker_symbols)):
            return None
        return self.app.ticker_symbols[self.app.active_symbol_index]

    def can_trade_now(self) -> bool:
        from . import utils
        return utils.is_market_open_now() or self.app.afterhours_enabled

    def is_splash_active(self) -> bool:
        from .views.splash_screen import SplashScreen
        return bool(
            self.app.screen_stack and isinstance(self.app.screen_stack[-1], SplashScreen)
        )

    def navigate_to_symbol(self, index: int) -> None:
        if self.app.is_backtest:
            return
        self._exit_backtest()

        if not (0 <= index < len(self.app.ticker_symbols)):
            return

        self.app.active_symbol_index = index
        symbol = self.app.ticker_symbols[index]
        log.debug(f"action selected symbol: {symbol}")
        self.app.run_worker(self._poll_one_symbol, name=f"poll_{symbol}", description=f"Poll {symbol}")
        if hasattr(self.app, "_poll_now"):
            self.app._poll_now.set()
        self.app.update_view(symbol)

    def _exit_backtest(self) -> None:
        try:
            if self.app.is_backtest and hasattr(self.app, "_exit_backtest"):
                self.app._exit_backtest()
        except Exception as e:
            log.warning(f"Failed to exit backtest: {e}")

    def _poll_one_symbol(self, symbol: str) -> None:
        from . import utils
        from . import broker_tools
        from . import cache
        from .strategies import metrics
        from datetime import datetime
        import traceback

        if self.app.strategy_class is None:
            return
        try:
            df, quote = self._fetch_data(symbol)
            if df.empty or quote is None:
                self.app.df_cache[symbol] = df
                self.app._update_queue.put(symbol)
                return

            df = self._analyze_indicators(df)

            position = self.app.broker_api.get_position(symbol)
            position = self._normalize_position(position)
            orders = None
            try:
                orders = self.app.broker_api.get_pending_orders(symbol)
            except Exception:
                orders = None

            signal_dict = None
            if self.app.strategy_active and self.app.strategy_service:
                try:
                    signal_dict = self.app.strategy_service.detect_signals(
                        df,
                        symbol,
                        position=position,
                        orders=orders,
                    )
                except Exception as exc:
                    log.error("[poll] signal error: %s", traceback.format_exc())

                    def _flash_error() -> None:
                        self.app.overlay.flash_message(
                            f"Strategy error: {exc}",
                            style="bold red",
                        )

                    self.app.call_from_thread(_flash_error)
                    if self.app.voice_agent:
                        self.app.call_from_thread(
                            self.app.voice_agent.say, f"Strategy error: {exc}"
                        )
                    if self.is_splash_active():
                        self.app.call_from_thread(self.app.pop_screen)
                    return

            if signal_dict and not self.is_splash_active():
                self._handle_signal(symbol, df, quote, signal_dict)

            self.app.df_cache[symbol] = df
            self.app._update_queue.put(symbol)
            if symbol == self.get_active_symbol():
                if self.is_splash_active():
                    self.app.call_from_thread(self.app.pop_screen)
                    if self.app.voice_agent:
                        self.app.voice_agent.say("Welcome to Spectr", wait=True)
                    else:
                        utils.play_sound(INTRO_SOUND_PATH)
                self.app.call_from_thread(
                    self.app.update_view,
                    self.app.ticker_symbols[self.app.active_symbol_index],
                )
        except Exception:
            log.error(f"[poll] {symbol}: {traceback.format_exc()}")

    def _fetch_data(self, symbol: str):
        from datetime import datetime
        from . import utils

        log.debug(f"Fetching live data for {symbol}...")
        df = self.app.data_api.fetch_chart_data(
            symbol,
            from_date=datetime.now().date().strftime("%Y-%m-%d"),
            to_date=datetime.now().date().strftime("%Y-%m-%d"),
        )
        quote = self.app.data_api.fetch_quote(symbol)
        if df.empty or quote is None:
            return pd.DataFrame(), None

        price = quote.get("price")
        if price is not None:
            self.app._latest_quotes[symbol.upper()] = float(price)

        log.debug(f"Injecting quote for {symbol}")
        df = utils.inject_quote_into_df(df, quote)
        return df, quote

    def _analyze_indicators(self, df):
        from .strategies import metrics

        if self.app.strategy_class is None:
            return df
        df = metrics.analyze_indicators(
            df,
            self.app.strategy_class.get_indicators(),
        )
        df["trade"] = None
        df["signal"] = None
        return df

    def _handle_signal(self, symbol: str, df, quote: dict, signal_dict: dict) -> None:
        from . import utils
        from . import broker_tools
        from . import cache
        from .fetch.broker_interface import OrderSide
        from datetime import datetime

        signal = signal_dict.get("signal")
        curr_price = quote.get("price")
        reason = signal_dict.get("reason")
        log.debug(f"Signal detected for {symbol}. Reason: {reason}")
        df.at[df.index[-1], "trade"] = signal

        if signal and self.app.auto_trading_enabled and self.can_trade_now():
            side = (
                OrderSide.BUY
                if signal == "buy"
                else OrderSide.SELL if signal == "sell" else None
            )
            if side:
                if self.app.broker_api.has_pending_order_with_side(symbol, side):
                    log.warning(f"Pending {side.name.lower()} order for {symbol}; ignoring signal!")
                    return
                order = broker_tools.submit_order(
                    self.app.broker_api,
                    symbol,
                    side,
                    curr_price,
                    self.app.trade_amount,
                    self.app.auto_trading_enabled,
                    voice_agent=self.app.voice_agent,
                    success_sound_path=ORDER_SUCCESS_SOUND_PATH,
                )
                if order:
                    cache.attach_order_to_last_signal(
                        self.app.strategy_signals,
                        symbol.upper(),
                        side.name.lower(),
                        order,
                        reason=reason,
                    )

        cache.record_signal(
            self.app.strategy_signals,
            {
                "time": datetime.now(),
                "symbol": symbol,
                "side": signal,
                "price": curr_price,
                "reason": reason,
                "strategy": self.app.strategy_name,
            },
        )
        if signal == "buy":
            utils.play_sound(BUY_SOUND_PATH)
        elif signal == "sell":
            utils.play_sound(SELL_SOUND_PATH)

    def _normalize_position(self, position):
        try:
            from types import SimpleNamespace
            if isinstance(position, dict):
                return SimpleNamespace(**position)
            if position and not hasattr(position, "symbol"):
                return SimpleNamespace(**vars(position))
            return position
        except Exception:
            return position
