import asyncio
from textual.app import App

from spectr.views.strategy_screen import StrategyScreen
from spectr.views.portfolio_screen import PortfolioScreen
from spectr.views.ticker_input_dialog import TickerInputDialog
from spectr.views.top_overlay import TopOverlay


class StrategyApp(App):
    def compose(self):
        self.overlay = TopOverlay(id="overlay-text")
        yield self.overlay

    async def on_mount(self) -> None:
        self.scr = StrategyScreen([], ["A"], "A")
        await self.push_screen(self.scr)


def test_strategy_screen_has_overlay():
    async def run():
        async with StrategyApp().run_test() as pilot:
            assert isinstance(pilot.app.overlay, TopOverlay)

    asyncio.run(run())


class PortfolioApp(App):
    def compose(self):
        self.overlay = TopOverlay(id="overlay-text")
        yield self.overlay

    async def on_mount(self) -> None:
        self.scr = PortfolioScreen(
            0.0,
            0.0,
            0.0,
            [],
            [],
            lambda *a, **k: [],
            lambda *a, **k: None,
            False,
        )
        await self.push_screen(self.scr)


def test_portfolio_screen_has_overlay():
    async def run():
        async with PortfolioApp().run_test() as pilot:
            assert isinstance(pilot.app.overlay, TopOverlay)

    asyncio.run(run())


class TickerApp(App):
    def compose(self):
        self.overlay = TopOverlay(id="overlay-text")
        yield self.overlay

    async def on_mount(self) -> None:
        self.scr = TickerInputDialog(
            lambda *a, **k: None,
            lambda *a, **k: [],
            scanner_names=["TEST"],
            current_scanner="TEST",
        )
        await self.push_screen(self.scr)


def test_ticker_dialog_has_overlay():
    async def run():
        async with TickerApp().run_test() as pilot:
            assert isinstance(pilot.app.overlay, TopOverlay)

    asyncio.run(run())
