from __future__ import annotations

"""Composite widget that vertically stacks price, MACD, and volume views for a single symbol.

Usage
-----
SymbolView expects the hosting app to:

1. Construct it once (typically in `on_mount`) and dock it like any other
   Textual widget.

2. Call ``load_df(df, args, indicators)`` whenever the DataFrame for the *active* symbol
   changes.  All three sub‑views share the same DataFrame instance, so they
   stay in perfect sync.
"""

import logging
from textual.widget import Widget
from textual.containers import Vertical
from textual.app import ComposeResult

from .graph_view import GraphView
from .macd_view import MACDView
from .volume_view import VolumeView

__all__ = ["SymbolView"]

log = logging.getLogger(__name__)


class SymbolView(Widget):
    """A single panel that shows price, MACD, and volume stacked vertically."""

    DEFAULT_CSS = """
    SymbolView > Vertical {
        height: 1fr;           /* fill parent but let internal views size themselves */
        width: 100%;
    }

    /* Allocate space: 60% price, 20% MACD, 20% volume (adjust to taste) */
    SymbolView GraphView   { height: 6fr; }
    SymbolView MACDView    { height: 2fr; }
    SymbolView VolumeView  { height: 2fr; }
    """

    def __init__(self, *, id: str | None = None) -> None:  # noqa: D401
        """Create the composite view.

        Parameters
        ----------
        id : str | None
            CSS‑id for the widget (optional).
        """
        super().__init__(id=id)

        # child widgets are created in compose()
        self.graph: GraphView | None = None
        self.macd: MACDView | None = None
        self.volume: VolumeView | None = None

    def compose(self) -> ComposeResult:  # noqa: D401
        """Create and arrange the three sub‑views."""
        self.graph = GraphView()
        self.macd = MACDView()
        self.volume = VolumeView()

        with Vertical():
            yield self.graph
            yield self.macd
            yield self.volume

    def load_df(self, symbol, df, args, indicators=None) -> None:
        """Push *df* + *args* down to every child view and refresh them."""
        if not (self.graph and self.macd and self.volume):
            log.debug("SymbolView.load_df called before compose finished")
            return

        self.graph.symbol = symbol
        self.graph.load_df(df, args, indicators)
        has_macd = any(spec.name.lower() == "macd" for spec in (indicators or []))
        self.macd.display = has_macd
        if has_macd:
            self.macd.load_df(df, args)
        self.volume.load_df(df, args)

        # Request a refresh so the composite itself re‑renders promptly
        self.refresh()
