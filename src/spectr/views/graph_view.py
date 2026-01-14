import asyncio
import logging
from textual.reactive import reactive
from textual.widgets import Static

from ..rendering import PlotRenderer, PriceChartInputs, build_price_model

log = logging.getLogger(__name__)
_RENDERER = PlotRenderer()


class GraphView(Static):
    symbol: reactive[str] = reactive("")
    quote: reactive[dict] = reactive(None)
    is_backtest: reactive[bool] = reactive(False)
    indicators: reactive[list] = reactive([])
    frozen: reactive[bool] = reactive(False)
    # When True, limit data to what fits widget width; when False, plot all rows
    crop_to_width: reactive[bool] = reactive(True)
    # Disable periodic refresh loop (used by backtest results modal)
    auto_refresh_enabled: bool = True

    # Internal: handle to periodic refresh timer
    _refresh_timer = None

    def update_symbol(self, value: str):
        self.symbol = value

    def __init__(
        self, df=None, args=None, indicators=None, pre_rendered=None, **kwargs
    ):
        super().__init__(**kwargs)
        self.df = df
        self.args = args
        self.indicators = indicators or []
        self.pre_rendered = pre_rendered

    def on_mount(self):
        if self.frozen:
            return
        # Only start a periodic refresh for live views when enabled
        if self.auto_refresh_enabled and not self.is_backtest:
            self._refresh_timer = self.set_interval(0.5, self.refresh)

    async def on_resize(self, event):
        """Handle resize events.

        For back-test graphs the render can be expensive, so rebuild the
        graph off the UI thread when the widget is resized.  Live graphs are
        lightweight, so they simply trigger a normal refresh.
        """
        if self.frozen:
            # Do not rebuild or refresh when frozen
            return
        if self.is_backtest:
            # Keep the previous render until the updated one is ready to avoid
            # blocking the interface.
            self.pre_rendered = await asyncio.to_thread(self.build_graph)
            self.refresh()
        else:
            self.pre_rendered = None
            self.refresh()  # Force redraw when size changes

    def watch_df(self, old, new):
        if not self.frozen:
            self.pre_rendered = None
            self.refresh()

    def watch_symbol(self, old, new):
        if not self.frozen:
            self.pre_rendered = None
            self.refresh()

    def watch_quote(self, old, new):
        if not self.frozen:
            self.pre_rendered = None
            self.refresh()

    def watch_is_backtest(self, old, new):
        if not self.frozen:
            self.pre_rendered = None
            self.refresh()
        # Stop periodic refresh when entering backtest mode
        if new and self._refresh_timer is not None:
            try:
                self._refresh_timer.stop()
            except Exception:
                pass
            self._refresh_timer = None

    def watch_crop_to_width(self, old, new):
        if not self.frozen:
            self.pre_rendered = None
            self.refresh()

    async def on_unmount(self) -> None:
        # Ensure any periodic timer is stopped when the widget is removed
        if self._refresh_timer is not None:
            try:
                self._refresh_timer.stop()
            except Exception:
                pass
            self._refresh_timer = None

    def load_df(self, df, args, indicators=None):
        """Store the DataFrame and redraw on next refresh."""
        if self.frozen:
            # Ignore updates when frozen to preserve the rendered snapshot
            return
        self.df = df
        self.args = args
        if indicators is not None:
            self.indicators = indicators
        self.pre_rendered = None
        self.refresh()

    def render(self):
        if self.pre_rendered is not None:
            return self.pre_rendered
        if self.frozen:
            # Build once and keep
            self.pre_rendered = self.build_graph()
            return self.pre_rendered
        return self.build_graph()

    def build_graph(self):
        if self.df is None or self.df.empty:
            return "Waiting for chart data..."

        model = build_price_model(
            PriceChartInputs(
                df=self.df,
                symbol=self.symbol,
                indicators=self.indicators,
                args=self.args,
                is_backtest=self.is_backtest,
                crop_to_width=self.crop_to_width,
                width=max(int(self.size.width), 20),
            )
        )
        if model is None:
            return "No plottable price series available."

        width = max(int(self.size.width) - 2, 10)
        height = max(int(self.size.height) - 1, 8)
        return _RENDERER.render(model, width=width, height=height)
