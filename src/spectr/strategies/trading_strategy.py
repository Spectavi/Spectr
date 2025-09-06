import logging
from dataclasses import dataclass
from typing import Optional, Any, Iterable
from enum import Enum

import pandas as pd
import backtrader as bt
import inspect

log = logging.getLogger(__name__)


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
) -> Optional[dict[str, str]]:
    """Return an exit signal dict if stop levels are hit."""
    qty = get_position_qty(position)
    if qty == 0:
        return None

    entry_price = get_entry_price(position)
    if entry_price is None:
        return None

    if qty > 0:
        if price <= entry_price * (1 - stop_loss_pct):
            return {"signal": "sell", "reason": "Stop loss"}
        if price >= entry_price * (1 + take_profit_pct):
            return {"signal": "sell", "reason": "Take profit"}
    elif qty < 0:
        if price >= entry_price * (1 + stop_loss_pct):
            return {"signal": "buy", "reason": "Stop loss"}
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
            try:
                from . import metrics

                df = metrics.analyze_indicators(df, specs)
            except Exception:  # pragma: no cover - unexpected
                log.warning("Failed to analyze indicators", exc_info=True)
        return df

    def handle_signal(self, signal: Optional[dict]) -> None:
        if signal:
            log.debug(f"Signal detected: {signal}")

        current_position = self.getposition(self.datas[0])
        qty = getattr(current_position, "qty", getattr(current_position, "size", 0))
        if signal and signal.get("signal") == "sell" and qty:
            log.debug(f"BACKTEST: Sell signal detected: {signal['reason']}")
            self.sell()
            self.sell_signals.append(
                {
                    "type": "sell",
                    "time": self.datas[0].datetime.datetime(0),
                    "price": self.datas[0].close[0],
                }
            )
            self.entry_price = None
            return

        if signal and signal.get("signal") == "buy" and not qty:
            log.debug(f"BACKTEST: Buy signal detected: {signal['reason']}")
            self.buy()
            self.buy_signals.append(
                {
                    "type": "buy",
                    "time": self.datas[0].datetime.datetime(0),
                    "price": self.datas[0].close[0],
                }
            )
            self.entry_price = self.datas[0].close[0]

    def next(self) -> None:
        lookback = self.get_lookback()
        df = self.build_dataframe(lookback)
        kwargs = self.get_signal_args()
        params = inspect.signature(self.detect_signals).parameters
        allowed = set(params) - {"self", "df", "symbol", "position", "orders"}
        filtered = {k: v for k, v in kwargs.items() if k in allowed}

        open_orders = []
        try:
            open_orders = list(self.broker.get_orders_open(safe=True))
        except Exception:  # pragma: no cover - unexpected
            pass

        signal = self.detect_signals(
            df,
            self.p.symbol,
            position=self.position,
            orders=open_orders,
            **filtered,
        )
        self.handle_signal(signal)
