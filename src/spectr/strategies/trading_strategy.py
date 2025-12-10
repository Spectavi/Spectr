import logging
from dataclasses import dataclass
from typing import Optional, Any, Iterable
from enum import Enum

import pandas as pd
import backtrader as bt
import inspect

log = logging.getLogger(__name__)

_TRAIL_STATE: dict[int, dict[str, float]] = {}


def _normalize_side(side: Any) -> str:
    """Return ``side`` as a lower-case string."""
    if isinstance(side, Enum):
        side = side.value
    return str(side).lower()


def get_order_sides(orders: Optional[Iterable]) -> set[str]:
    """Return the lowercase order sides present in *orders*."""
    sides: set[str] = set()
    if orders is None:
        return sides

    try:
        if isinstance(orders, pd.DataFrame):
            if "side" in orders.columns:
                sides.update(_normalize_side(s) for s in orders["side"].dropna())
        else:
            for order in orders:
                side = None
                if isinstance(order, dict):
                    side = order.get("side")
                else:
                    # Backtrader orders don't expose a 'side' attribute but
                    # provide 'isbuy()' / 'issell()' helpers.
                    try:
                        # Skip terminal orders if a status attribute is present
                        status = getattr(order, "status", None)
                        if status is not None:
                            terminal = {
                                getattr(bt.Order, "Completed", object()),
                                getattr(bt.Order, "Canceled", object()),
                                getattr(bt.Order, "Rejected", object()),
                                getattr(bt.Order, "Expired", object()),
                            }
                            if status in terminal:
                                continue
                        if hasattr(order, "isbuy") and callable(order.isbuy) and order.isbuy():
                            side = "buy"
                        elif hasattr(order, "issell") and callable(order.issell) and order.issell():
                            side = "sell"
                        else:
                            side = getattr(order, "side", None)
                    except Exception:
                        side = getattr(order, "side", None)
                if side is not None:
                    sides.add(_normalize_side(side))
    except Exception:
        pass
    return sides


def get_position_qty(position: Optional[object]) -> float:
    """Return the numeric quantity for *position* or ``0.0``."""
    if position is None:
        return 0.0
    qty = getattr(position, "qty", getattr(position, "size", 0))
    try:
        return float(qty)
    except Exception:
        return 0.0


def get_entry_price(position: Optional[object]) -> Optional[float]:
    """Return the entry price for *position*, if available."""
    if position is None:
        return None

    for attr in ("avg_entry_price", "entry_price", "avg_price", "price"):
        if hasattr(position, attr):
            try:
                return float(getattr(position, attr))
            except Exception:
                continue
    return None


def check_stop_levels(
    price: float,
    position: Optional[object],
    stop_loss_pct: float,
    take_profit_pct: float,
    *,
    trailing_stop: bool = False,
) -> Optional[dict[str, str]]:
    """Return an exit signal dict if stop levels are hit."""
    qty = get_position_qty(position)
    if qty == 0:
        if position is not None:
            _TRAIL_STATE.pop(id(position), None)
        return None

    entry_price = get_entry_price(position)
    if entry_price is None:
        return None

    trail_key = id(position) if position is not None else None
    trail = _TRAIL_STATE.get(trail_key) if trailing_stop and trail_key else None
    if trailing_stop and trail_key is not None and trail is None:
        trail = {"high": entry_price, "low": entry_price}
        _TRAIL_STATE[trail_key] = trail

    stop_reason = "Stop loss"
    stop_ref = entry_price

    if trailing_stop and trail is not None:
        if qty > 0:
            trail["high"] = max(trail["high"], price)
            stop_ref = trail["high"]
        elif qty < 0:
            trail["low"] = min(trail["low"], price)
            stop_ref = trail["low"]
        stop_reason = "Trailing stop loss"

    if qty > 0:
        if price <= stop_ref * (1 - stop_loss_pct):
            return {"signal": "sell", "reason": stop_reason}
        if price >= entry_price * (1 + take_profit_pct):
            return {"signal": "sell", "reason": "Take profit"}
    elif qty < 0:
        if price >= stop_ref * (1 + stop_loss_pct):
            return {"signal": "buy", "reason": stop_reason}
        if price <= entry_price * (1 - take_profit_pct):
            return {"signal": "buy", "reason": "Take profit"}
    return None


@dataclass
class IndicatorSpec:
    """Specification for an indicator used by a strategy."""

    name: str
    params: dict[str, Any]


class TradingStrategy(bt.Strategy):

    params = (("symbol", ""),)

    @classmethod
    def get_indicators(cls) -> list[IndicatorSpec]:
        """Return a list of indicator specifications used by this strategy."""
        return []

    def get_lookback(self) -> int:
        """Return how many bars to include in the DataFrame."""
        return 200

    def get_signal_args(self) -> dict[str, Any]:
        """Return keyword arguments to pass to :meth:`detect_signals`."""
        return {}

    def build_dataframe(self, lookback: int) -> pd.DataFrame:
        data = {
            "close": [self.datas[0].close[-i] for i in reversed(range(lookback))],
            "open": [self.datas[0].open[-i] for i in reversed(range(lookback))],
            "high": [self.datas[0].high[-i] for i in reversed(range(lookback))],
            "low": [self.datas[0].low[-i] for i in reversed(range(lookback))],
            "volume": [self.datas[0].volume[-i] for i in reversed(range(lookback))],
        }
        df = pd.DataFrame(data)

        specs = self.get_indicators()
        if specs:
            log.debug("[Backtest] Calculating indicators: %s", specs)
            try:
                from . import metrics

                df = metrics.analyze_indicators(df, specs)
            except Exception:  # pragma: no cover - unexpected
                log.warning("Failed to analyze indicators", exc_info=True)
        else:
            log.debug("[Backtest] No indicators found.")
        return df

    # Backtrader lifecycle hook – initialize per-run tracking containers
    def start(self) -> None:  # pragma: no cover - exercised via backtests
        try:
            # Track portfolio value over time for equity curve output
            self.equity_times: list = []
            self.equity_values: list[float] = []
            # Lightweight pending-side flag to prevent duplicate submits
            self._pending_side: Optional[str] = None  # 'buy' or 'sell'
        except Exception:
            pass

    def stop(self) -> None:  # pragma: no cover - exercised via backtests
        """Ensure a final equity point is recorded at the end of the run.

        Some backtests may end on a bar without triggering another `next()`
        call after fills. Record a last snapshot to align with the final candle.
        """
        try:
            t = self.datas[0].datetime.datetime(0)
            v = float(self.broker.getvalue())
            if not hasattr(self, "equity_times"):
                self.equity_times = []
                self.equity_values = []
            if not self.equity_times or self.equity_times[-1] != t:
                self.equity_times.append(t)
                self.equity_values.append(v)
        except Exception:
            pass

    def handle_signal(self, signal: Optional[dict]) -> None:
        """Execute orders based on the provided *signal*."""
        if signal:
            log.debug(f"[Backtest] Signal detected: {signal}")

        current_position = self.getposition(self.datas[0])
        qty = getattr(current_position, "qty", getattr(current_position, "size", 0))
        # Prevent duplicate orders if one of the same side is pending
        if self._pending_side is not None:
            log.debug(f"[BACKTEST] Skipping signal, pending={self._pending_side}")
            return

        # Also consult broker open orders as a safety net
        open_orders = []
        try:
            open_orders = list(self.broker.get_orders_open(safe=True))
        except Exception:
            open_orders = []
        open_sides = get_order_sides(open_orders)

        if signal and signal.get("signal") == "sell" and qty and "sell" not in open_sides:
            log.debug(f"[BACKTEST]: Sell signal detected: {signal['reason']}")
            self.sell()
            self.sell_signals.append(
                {
                    "type": "sell",
                    "time": self.datas[0].datetime.datetime(0),
                    "price": self.datas[0].close[0],
                    "quantity": qty,
                    "reason": signal.get("reason"),
                }
            )
            self._pending_side = "sell"
            self.entry_price = None
            return

        if signal and signal.get("signal") == "buy" and not qty and "buy" not in open_sides:
            log.debug(f"[BACKTEST]: Buy signal detected: {signal['reason']}")
            cash = self.broker.getcash()
            price = self.datas[0].close[0]
            quantity = cash / price if price else 0
            self.buy()
            self.buy_signals.append(
                {
                    "type": "buy",
                    "time": self.datas[0].datetime.datetime(0),
                    "price": price,
                    "quantity": quantity,
                    "reason": signal.get("reason"),
                }
            )
            self._pending_side = "buy"
            self.entry_price = price

    def next(self) -> None:
        lookback = self.get_lookback()
        df = self.build_dataframe(lookback)
        kwargs = self.get_signal_args()
        params = inspect.signature(self.detect_signals).parameters
        allowed = set(params) - {"self", "df", "symbol", "position", "orders"}
        filtered = {k: v for k, v in kwargs.items() if k in allowed}

        # Clear pending flag when position updates reflect a fill
        try:
            pos_qty = getattr(self.position, "qty", getattr(self.position, "size", 0))
            if self._pending_side == "buy" and pos_qty:
                self._pending_side = None
            elif self._pending_side == "sell" and not pos_qty:
                self._pending_side = None
        except Exception:
            pass

        # Provide open orders to detect_signals so strategies can self-guard
        open_orders = []
        try:
            open_orders = list(self.broker.get_orders_open(safe=True))
        except Exception:  # pragma: no cover - unexpected
            log.error("Failed to get open orders", exc_info=True)
            pass

        signal = self.detect_signals(
            df,
            self.p.symbol,
            position=self.position,
            orders=open_orders,
            **filtered,
        )
        self.handle_signal(signal)

        # Record equity after handling potential orders
        try:
            t = self.datas[0].datetime.datetime(0)
            v = float(self.broker.getvalue())
            # Containers are created in start(); create on-demand if missing
            if not hasattr(self, "equity_times"):
                self.equity_times = []
                self.equity_values = []
            self.equity_times.append(t)
            self.equity_values.append(v)
        except Exception:  # pragma: no cover - defensive
            pass
