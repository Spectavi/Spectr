from textual.screen import Screen
from textual.widgets import TabbedContent, TabPane
from views.graph_view import GraphView
from views.macd_view import MACDView

# UNDER CONSTRUCTION
class MultiSymbolScreen(Screen):
    def __init__(self, symbols: list[str], args):
        super().__init__()
        self.symbols = symbols
        self.args = args

    def compose(self):
        yield TabbedContent(*[
            TabPane(
                GraphView(symbol=symbol, id=f"graph-{symbol}"),
                MACDView(symbol=symbol, id=f"macd-{symbol}"),
                title=symbol
            )
            for symbol in self.symbols
        ])
