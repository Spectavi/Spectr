import logging
import math
import traceback

from .fetch.broker_interface import BrokerInterface, OrderSide, OrderType
from .utils import is_market_open_now, is_crypto_symbol, play_sound

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Helper for building order details
# ----------------------------------------------------------------------


def prepare_order_details(
    symbol: str, side: OrderSide, broker: BrokerInterface
) -> tuple[OrderType, float | None]:
    """Return the order type and limit price for *symbol* based on market hours."""
    order_type = OrderType.MARKET
    limit_price: float | None = None

    if not is_market_open_now() and not is_crypto_symbol(symbol):
        quote = broker.fetch_quote(symbol)
        order_type = OrderType.LIMIT
        if side == OrderSide.BUY:
            limit_price = (
                quote.get("ask")
                or quote.get("ask_price")
                or quote.get("askPrice")
                or quote.get("price")
            )
            if limit_price:
                limit_price *= 1.003
                limit_price = round(limit_price, 2)
        else:
            limit_price = (
                quote.get("bid")
                or quote.get("bid_price")
                or quote.get("bidPrice")
                or quote.get("price")
            )
            if limit_price:
                limit_price *= 0.997
                limit_price = round(limit_price, 2)

    log.debug(
        f"Order details for {symbol}: type={order_type}, limit_price={limit_price}"
    )
    return order_type, limit_price


# ----------------------------------------------------------------------
# Submit an order via the broker interface
# ----------------------------------------------------------------------


def submit_order(
    broker: BrokerInterface,
    symbol: str,
    side: OrderSide,
    price: float,
    trade_amount: float,
    auto_trading_enabled: bool,
    *,
    voice_agent=None,
    buy_sound_path: str | None = None,
    sell_sound_path: str | None = None,
) -> object | None:
    """Prepare and submit an order, handling fractional reattempts.

    Returns
    -------
    object | None
        The order object returned by ``broker.submit_order`` when available.
    """
    order_type, limit_price = prepare_order_details(symbol, side, broker)

    qty = 1.0
    if side == OrderSide.BUY and trade_amount > 0 and price > 0:
        qty = trade_amount / price
    elif side == OrderSide.SELL:
        pos = broker.get_position(symbol)
        if pos:
            log.debug(f"Position for {symbol}: {pos}")
            qty = float(pos.qty)
        else:
            log.debug(f"WARNING: No position to sell for {symbol}")
            return

    try:
        order = broker.submit_order(
            symbol=symbol,
            side=side,
            type=order_type,
            quantity=qty,
            limit_price=limit_price,
            market_price=price,
        )
        if buy_sound_path and sell_sound_path:
            play_sound(buy_sound_path if side == OrderSide.BUY else sell_sound_path)
        return order
    except Exception as e:  # noqa: BLE001
        err_msg = str(e)
        msgs = [err_msg]
        if hasattr(e, "message"):
            msgs.append(str(getattr(e, "message")))
        try:
            import json

            parsed = json.loads(err_msg)
            if isinstance(parsed, dict) and "message" in parsed:
                msgs.append(str(parsed["message"]))
        except Exception:
            pass

        err_msg = " ".join(msgs).lower()
        retried = False
        if (
            side == OrderSide.BUY
            and not float(qty).is_integer()
            and any(w in err_msg for w in {"fraction", "integer", "whole"})
        ):
            fallback_qty = math.floor(qty)
            total = fallback_qty * price
            if fallback_qty > 0 and 0 < total <= trade_amount:
                log.warning(
                    f"{symbol} not fractionable, retrying with qty={fallback_qty}"
                )
                try:
                    res = broker.submit_order(
                        symbol=symbol,
                        side=side,
                        type=order_type,
                        quantity=fallback_qty,
                        limit_price=limit_price,
                        market_price=price,
                        real_trades=auto_trading_enabled,
                    )
                    if buy_sound_path and sell_sound_path:
                        play_sound(
                            buy_sound_path if side == OrderSide.BUY else sell_sound_path
                        )
                    retried = True
                    order = res
                except Exception as exc2:  # noqa: BLE001
                    e = exc2
        if not retried:
            log.error(f"Failed to submit order for {symbol}: {traceback.format_exc()}")
            if voice_agent is not None:
                voice_agent.say(text=f"Failed to submit order for {symbol}: {e}")
            raise
    return order if "order" in locals() else None
