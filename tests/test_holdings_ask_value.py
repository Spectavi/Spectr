import asyncio
from types import SimpleNamespace

import spectr.spectr as appmod
from spectr.views.portfolio_screen import PortfolioScreen
from textual.app import App
from textual.widgets import DataTable


class DummyApp(App):
    def __init__(self, pos):
        super().__init__()
        self.pos = pos
        self.pscreen = None

    async def on_mount(self) -> None:
        self.pscreen = PortfolioScreen(
            0.0,
            0.0,
            0.0,
            [self.pos],
            [],
            lambda *a, **k: [],
            lambda *a, **k: None,
            False,
            balance_callback=lambda: {
                "cash": 0.0,
                "buying_power": 0.0,
                "portfolio_value": 0.0,
            },
            positions_callback=lambda: [self.pos],
        )
        await self.push_screen(self.pscreen)


def test_holdings_table_bid_and_ask_value(monkeypatch):
    class DummyBroker:
        def fetch_quote(self, symbol: str):
            return {"ask": 11.0, "bid": 9.0}

    monkeypatch.setattr(appmod, "BROKER_API", DummyBroker())

    pos = SimpleNamespace(symbol="AAA", qty=2, market_value=20.0, avg_entry_price=10.0)

    async def run() -> None:
        async with DummyApp(pos).run_test() as pilot:
            screen = pilot.app.pscreen
            await screen._reload_account_data()
            table = screen.query_one("#holdings-table", DataTable)
            ask_val = float(table.get_cell_at((0, 3)))
            bid_val = float(table.get_cell_at((0, 4)))
            assert ask_val == 22.0
            assert bid_val == 18.0

    asyncio.run(run())
