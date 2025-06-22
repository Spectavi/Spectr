from pathlib import Path
from textual.app import App

from .onboarding_dialog import OnboardingDialog

class OnboardingApp(App):
    """Temporary app to collect onboarding information."""
    CSS_PATH = Path(__file__).resolve().parent.parent / "default.tcss"

    def __init__(self) -> None:
        super().__init__()
        self.result = None

    async def on_mount(self) -> None:
        await self.push_screen(OnboardingDialog(self._on_submit), wait_for_dismiss=False)

    def _on_submit(self, broker: str, data: str, broker_key: str, data_key: str) -> None:
        self.result = {
            "broker": broker,
            "data_api": data,
            "broker_key": broker_key,
            "data_key": data_key,
        }
        self.exit()
