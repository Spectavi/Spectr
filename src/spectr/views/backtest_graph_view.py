import asyncio
from textual.widgets import Static
from .graph_view import GraphView


class BacktestGraphView(GraphView):
    """Isolated graph view for backtest results.

    - Never auto-refreshes.
    - Ignores reactive updates after initial render.
    - Uses a deep copy of the provided DataFrame to avoid external mutation.
    - Always renders the full range with backtest styling.
    """

    def __init__(self, df=None, args=None, **kwargs):
        super().__init__(df=None, args=args, indicators=[], pre_rendered=None, **kwargs)
        # Force backtest rendering mode and no cropping
        self.is_backtest = True
        self.crop_to_width = False
        self.auto_refresh_enabled = False
        self.frozen = False

    def on_mount(self):
        # Do not start any periodic refresh timers
        pass

    # Disable all watchers so no later property changes can trigger redraws
    def watch_df(self, old, new):
        pass

    def watch_symbol(self, old, new):
        pass

    def watch_quote(self, old, new):
        pass

    def watch_is_backtest(self, old, new):
        pass

    def watch_crop_to_width(self, old, new):
        pass

    def load_df(self, df, args, indicators=None):
        # Store a deep copy to ensure isolation from external mutations
        try:
            self.df = df.copy(deep=True)
        except Exception:
            self.df = df
        self.args = args
        self.pre_rendered = None
        # Build once off-thread, then freeze to lock the content
        async def _render_then_freeze():
            self.pre_rendered = await asyncio.to_thread(self.build_graph)
            self.frozen = True
            self.refresh()

        asyncio.create_task(_render_then_freeze())

    async def on_resize(self, event):
        # Ignore resizes once frozen to keep a stable snapshot
        if not self.frozen:
            # Before first freeze, allow a single render using the new size
            self.pre_rendered = await asyncio.to_thread(self.build_graph)
            self.frozen = True
            self.refresh()

    async def on_unmount(self) -> None:
        # Nothing to stop; no intervals were started
        pass

