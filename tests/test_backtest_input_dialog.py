import asyncio
from textual.app import App

from spectr.views.backtest_input_dialog import BacktestInputDialog


class DialogApp(App):
    async def on_mount(self) -> None:
        self.dlg = BacktestInputDialog(
            lambda *a, **k: None,
            default_symbol="TEST",
            strategies=["S"],
            current_strategy="S",
        )
        await self.push_screen(self.dlg)


def test_backtest_dialog_escape_dismisses():
    async def run() -> None:
        async with DialogApp().run_test() as pilot:
            await pilot.press("escape")
            assert not isinstance(pilot.app.screen, BacktestInputDialog)

    asyncio.run(run())
