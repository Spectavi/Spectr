import asyncio
from textual.app import App

from spectr.views.portfolio_screen import PortfolioScreen


class PortfolioApp(App):
    def __init__(self):
        super().__init__()
        self.auto_trading_enabled = False
        self.scr = None

    def set_auto_trading(self, enabled: bool):
        self.auto_trading_enabled = enabled
        if self.scr is not None:
            self.scr.auto_trading_enabled = enabled
            self.scr.auto_switch.value = enabled

    def action_arm_auto_trading(self):
        self.set_auto_trading(not self.auto_trading_enabled)

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
            set_auto_trading_cb=self.set_auto_trading,
        )
        await self.push_screen(self.scr)


def test_ctrl_a_toggles_auto_trading():
    async def run() -> None:
        async with PortfolioApp().run_test() as pilot:
            pilot.app.scr.holdings_table.focus()
            await pilot.press("ctrl+a")
            assert pilot.app.auto_trading_enabled
            assert pilot.app.scr.auto_switch.value

    asyncio.run(run())
