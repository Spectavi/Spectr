from pathlib import Path
from textual.app import App

from .. import cache
from .setup_dialog import SetupDialog


class SetupApp(App):
    """Temporary app to collect setup information."""

    CSS_PATH = Path(__file__).resolve().parent.parent / "default.tcss"

    def __init__(self) -> None:
        super().__init__()
        self.result = None

    async def on_mount(self) -> None:
        cfg = cache.load_onboarding_config()
        if cfg:
            self.result = cfg
            self.exit()
            return
        await self.push_screen(SetupDialog(self._on_submit), wait_for_dismiss=False)

    def _on_submit(
        self,
        broker: str,
        paper: str,
        data: str,
        broker_key: str,
        broker_secret: str,
        paper_key: str,
        paper_secret: str,
        data_key: str,
        data_secret: str,
        openai_key: str,
    ) -> None:
        self.result = {
            "broker": broker,
            "paper": paper,
            "data_api": data,
            "broker_key": broker_key,
            "broker_secret": broker_secret,
            "paper_key": paper_key,
            "paper_secret": paper_secret,
            "data_key": data_key,
            "data_secret": data_secret,
            "openai_key": openai_key,
        }
        self.exit()
