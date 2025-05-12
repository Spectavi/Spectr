from textual.widgets import Static
from textual.reactive import reactive

class TopOverlay(Static):
    symbol: reactive[str] = reactive("")
    status_text: reactive[str] = reactive("")        # The main persistent text
    alert_text: reactive[str] = reactive("")         # Temporary alerts (flash)
    live_icon: reactive[str] = reactive("🧪")         # Icon for live/paper trading
    _timer = None

    def update_symbol(self, symbol):
        self.symbol = symbol
        self.set_auto_trading_mode(False)

    def update_status(self, value: str):
        self.status_text = value

    def set_auto_trading_mode(self, enabled: bool):
        self.live_icon = "🤖" if enabled else "🚫"
        if enabled:
            self.update_status(f"Auto-Trades: ENABLED {self.live_icon}", style="BOLD GREEN")
        else:
            self.update_status(f"Auto-Trades: DISABLED {self.live_icon}", style="BOLD RED")

    def flash_message(self, msg: str, duration: float = 3.0, style: str = "bold red"):
        self.alert_text = f"[{style}]{msg}[/{style}]"
        if self._timer:
            self._timer.stop()
        self._timer = self.set_timer(duration, self._clear_flash)

    def _clear_flash(self):
        self.alert_text = ""

    def render(self):
        if self.alert_text:
            return f"{self.live_icon} {self.alert_text}"
        return f"{self.live_icon} {self.status_text}"
