"""Trading operations for SpectrApp."""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .spectr import SpectrApp
    from .fetch.broker_interface import OrderSide

log = logging.getLogger(__name__)

BUY_SOUND_PATH = "res/buy.mp3"
SELL_SOUND_PATH = "res/sell.mp3"
INTRO_SOUND_PATH = "res/intro.mp3"
ORDER_SUCCESS_SOUND_PATH = "res/order_success.mp3"


class TradingOperationsHandler:
    """Handles trading operations and order dialogs."""

    def __init__(self, app: "SpectrApp"):
        self.app = app

    def open_order_dialog(
        self, side: "OrderSide", pos_pct: float, symbol: str, reason=None
    ) -> None:
        if self._is_splash_active():
            return
        if self.app.trading_service.has_pending_order_with_side(symbol, side):
            log.warning(f"Pending {side.name} order for {symbol}; dialog not opened")
            if hasattr(self.app, "overlay") and self.app.overlay:
                self.app.overlay.flash_message(
                    f"Pending {side.name} order for {symbol}",
                    style="bold yellow",
                    duration=5.0,
                )
            return
        from . import broker_tools
        from .views.order_dialog import OrderDialog

        order_type, limit_price = broker_tools.prepare_order_details(
            symbol, side, self.app.broker_api, self.app.afterhours_enabled
        )
        self.app.push_screen(
            OrderDialog(
                side=side,
                symbol=symbol,
                pos_pct=pos_pct,
                get_pos_cb=self.app.trading_service.get_position,
                get_price_cb=self.app.data_service.fetch_quote,
                trade_amount=self.app.trade_amount if side.name == "BUY" else 0.0,
                reason=reason,
                default_order_type=order_type,
                default_limit_price=limit_price,
            )
        )

    def on_order_dialog_submit(self, msg) -> None:
        log.info(
            f"Placing {msg.side} {msg.qty} {msg.symbol} @ ${msg.price:.2f} "
            f"(total ${msg.total:,.2f})"
        )
        if self.app.trading_service.has_pending_order_with_side(msg.symbol, msg.side):
            log.warning(f"Pending {msg.side.name} order for {msg.symbol}; not submitting")
            if hasattr(self.app, "overlay") and self.app.overlay:
                self.app.overlay.flash_message(
                    f"Pending {msg.side.name} order for {msg.symbol}",
                    style="bold yellow",
                    duration=5.0,
                )
            return
        try:
            from . import cache

            if msg.side.name == "BUY":
                order = self.app.trading_service.submit_buy_order(
                    msg.symbol,
                    msg.price,
                    qty=msg.qty,
                )
            else:
                order = self.app.trading_service.submit_sell_order(
                    msg.symbol,
                    msg.price,
                    qty=msg.qty,
                )
            if order:
                cache.attach_order_to_last_signal(
                    self.app.strategy_signals,
                    msg.symbol.upper(),
                    msg.side.name.lower(),
                    order,
                    reason=None,
                )
        except Exception as e:
            log.error(e)
            if hasattr(self.app, "flash_message"):
                self.app.flash_message(f"{e.__str__()[:60]}")
            return

        symbol = msg.symbol.upper()
        df = self.app.df_cache.get(symbol)
        if df is not None and not df.empty:
            last_ts = df.index[-1]

            if msg.side.name == "BUY":
                if "buy_signals" not in df.columns:
                    df["buy_signals"] = None
                df.at[last_ts, "buy_signals"] = True
            elif msg.side.name == "SELL":
                if "sell_signals" not in df.columns:
                    df["sell_signals"] = None
                df.at[last_ts, "sell_signals"] = True

            self.app.df_cache[symbol] = df

            if symbol == self.app.ticker_symbols[self.app.active_symbol_index]:
                self.app.update_view(symbol)

    def _is_splash_active(self) -> bool:
        from .views.splash_screen import SplashScreen
        return bool(
            self.app.screen_stack and isinstance(self.app.screen_stack[-1], SplashScreen)
        )

    def open_buy_dialog(self, symbol: str, reason=None) -> None:
        from .fetch.broker_interface import OrderSide

        pos = self.app.broker_api.get_position(symbol)
        pos_pct = 1.0
        if hasattr(pos, "qty"):
            try:
                pos_pct = abs(float(pos.qty))
            except (TypeError, ValueError):
                pos_pct = 1.0
        self.open_order_dialog(OrderSide.BUY, pos_pct, symbol, reason)

    def open_sell_dialog(self, symbol: str, reason=None) -> None:
        from .fetch.broker_interface import OrderSide

        pos = self.app.broker_api.get_position(symbol)
        pos_pct = 1.0
        if hasattr(pos, "qty"):
            try:
                pos_pct = abs(float(pos.qty))
            except (TypeError, ValueError):
                pos_pct = 1.0
        self.open_order_dialog(OrderSide.SELL, pos_pct, symbol, reason)

    def open_sell_half_dialog(self, symbol: str) -> None:
        from .fetch.broker_interface import OrderSide

        pos = self.app.broker_api.get_position(symbol)
        pos_qty = 1.0
        if hasattr(pos, "qty") and pos.qty:
            try:
                pos_qty = abs(float(pos.qty))
                if pos_qty > 0:
                    pos_pct = pos_qty / 2.0
                else:
                    pos_pct = 0.5
            except (TypeError, ValueError):
                pos_pct = 0.5
        else:
            pos_pct = 0.5
        self.open_order_dialog(OrderSide.SELL, pos_pct, symbol)

    def open_sell_quarter_dialog(self, symbol: str) -> None:
        from .fetch.broker_interface import OrderSide

        pos = self.app.broker_api.get_position(symbol)
        pos_qty = 1.0
        if hasattr(pos, "qty") and pos.qty:
            try:
                pos_qty = abs(float(pos.qty))
                if pos_qty > 0:
                    pos_pct = pos_qty / 4.0
                else:
                    pos_pct = 0.25
            except (TypeError, ValueError):
                pos_pct = 0.25
        else:
            pos_pct = 0.25
        self.open_order_dialog(OrderSide.SELL, pos_pct, symbol)
