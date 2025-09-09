import asyncio
from types import SimpleNamespace

import pandas as pd
from textual.app import App

from spectr.views.backtest_input_dialog import BacktestInputDialog
from spectr.views.backtest_result_screen import BacktestResultScreen
from spectr.views.graph_view import GraphView
from spectr.views.strategy_screen import StrategyScreen
from spectr.views.portfolio_screen import PortfolioScreen
from spectr.views.ticker_input_dialog import TickerInputDialog
from spectr.views.top_overlay import TopOverlay


class StrategyApp(App):
    CSS_PATH = "../src/spectr/default.tcss"

    def compose(self):
        self.overlay = TopOverlay(id="overlay-text")
        yield self.overlay

    async def on_mount(self) -> None:
        self.scr = StrategyScreen([], ["A"], "A")
        await self.push_screen(self.scr)


def test_strategy_screen_has_overlay():
    async def run():
        async with StrategyApp().run_test() as pilot:
            await pilot.pause()
            assert isinstance(pilot.app.overlay, TopOverlay)
            assert pilot.app.scr.styles.background.a == 0

    asyncio.run(run())


class PortfolioApp(App):
    CSS_PATH = "../src/spectr/default.tcss"

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
            await pilot.pause()
            assert isinstance(pilot.app.overlay, TopOverlay)
            assert pilot.app.scr.styles.background.a == 0

    asyncio.run(run())


class TickerApp(App):
    CSS_PATH = "../src/spectr/default.tcss"

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
            await pilot.pause()
            assert isinstance(pilot.app.overlay, TopOverlay)
            assert pilot.app.scr.styles.background.a == 0

    asyncio.run(run())


class BacktestInputApp(App):
    CSS_PATH = "../src/spectr/default.tcss"

    def compose(self):
        self.overlay = TopOverlay(id="overlay-text")
        yield self.overlay

    async def on_mount(self) -> None:
        self.scr = BacktestInputDialog(
            lambda *a, **k: None, strategies=["S"], current_strategy="S"
        )
        await self.push_screen(self.scr)


def test_backtest_input_dialog_transparent():
    async def run():
        async with BacktestInputApp().run_test() as pilot:
            await pilot.pause()
            assert pilot.app.scr.styles.background.a == 0

    asyncio.run(run())


class BacktestResultApp(App):
    CSS_PATH = "../src/spectr/default.tcss"

    def compose(self):
        self.overlay = TopOverlay(id="overlay-text")
        yield self.overlay

    async def on_mount(self) -> None:
        df = pd.DataFrame()
        args = SimpleNamespace(scale=1)
        graph = GraphView(df, args, pre_rendered="")
        self.scr = BacktestResultScreen(
            graph,
            symbol="A",
            start_date="2024-01-01",
            end_date="2024-01-02",
            start_value=0.0,
            end_value=0.0,
            num_buys=0,
            num_sells=0,
            trades=[],
        )
        await self.push_screen(self.scr)


def test_backtest_result_screen_transparent():
    async def run():
        async with BacktestResultApp().run_test() as pilot:
            await pilot.pause()
            assert pilot.app.scr.styles.background.a == 0

    asyncio.run(run())
