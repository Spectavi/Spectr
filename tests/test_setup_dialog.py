import asyncio
from textual.app import App
from textual.widgets import Input, Select

from spectr.views.setup_dialog import SetupDialog

CFG = {
    "broker": "alpaca",
    "paper": "alpaca",
    "data_api": "fmp",
    "broker_key": "b",
    "broker_secret": "bs",
    "paper_key": "p",
    "paper_secret": "ps",
    "data_key": "d",
    "data_secret": "ds",
    "openai_key": "o",
}


class DialogApp(App):
    async def on_mount(self) -> None:
        self.dlg = SetupDialog(lambda *a: None, CFG)
        await self.push_screen(self.dlg)


def test_setup_dialog_defaults():
    async def run() -> None:
        async with DialogApp().run_test() as pilot:
            dlg = pilot.app.dlg
            assert dlg.query_one("#broker-key", Input).value == CFG["broker_key"]
            assert dlg.query_one("#paper-key", Input).value == CFG["paper_key"]
            assert dlg.query_one("#data-select", Select).value == CFG["data_api"]

    asyncio.run(run())
