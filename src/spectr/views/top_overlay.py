from textual.widgets import Static
from textual.reactive import reactive


VOICE_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class TopOverlay(Static):
    symbol: reactive[str] = reactive("")
    status_text: reactive[str] = reactive("")  # The main persistent text
    alert_text: reactive[str] = reactive("")  # Temporary alerts (flash)
    live_icon: reactive[str] = reactive("🧪")  # Icon for live/paper trading
    voice_frame: reactive[str] = reactive("")  # Spinner frames while speaking
    _timer = None
    _voice_timer = None
    _frame_index = 0

    def update_symbol(self, symbol):
        self.symbol = symbol
        self.set_auto_trading_mode(False)

    def update_status(self, value: str):
        self.status_text = value

    def set_auto_trading_mode(self, enabled: bool):
        self.live_icon = "🤖" if enabled else "🚫"
        if enabled:
            self.update_status(f"Auto-Trades: ENABLED {self.live_icon}")
        else:
            self.update_status(f"Auto-Trades: DISABLED {self.live_icon}")

    def flash_message(self, msg: str, duration: float = 10.0, style: str = "bold red"):
        self.alert_text = f"[{style}]{msg}[/{style}]"
        if self._timer:
            self._timer.stop()
        self._timer = self.set_timer(duration, self._clear_flash)

    def start_voice_animation(self) -> None:
        """Begin spinner animation indicating the voice agent is speaking."""
        if self._voice_timer:
            self._voice_timer.stop()
        self.voice_frame = VOICE_FRAMES[0]
        self._frame_index = 0
        self._voice_timer = self.set_interval(0.1, self._spin)

    def stop_voice_animation(self) -> None:
        """Stop the spinner animation."""
        if self._voice_timer:
            self._voice_timer.stop()
            self._voice_timer = None
        self.voice_frame = ""

    def _spin(self) -> None:
        self._frame_index = (self._frame_index + 1) % len(VOICE_FRAMES)
        self.voice_frame = VOICE_FRAMES[self._frame_index]

    def show_prompt(self, msg: str, style: str = "bold yellow"):
        """Display *msg* without auto clearing."""
        if self._timer:
            self._timer.stop()
            self._timer = None
        self.alert_text = f"[{style}]{msg}[/{style}]"

    def clear_prompt(self) -> None:
        """Remove any prompt text immediately."""
        if self._timer:
            self._timer.stop()
            self._timer = None
        self.alert_text = ""

    def _clear_flash(self):
        self.alert_text = ""

    def render(self):
        if self.alert_text:
            return f"{self.live_icon} {self.voice_frame} {self.alert_text}"
        return f"{self.live_icon} {self.voice_frame} {self.status_text}"

    # Watchers to force redraw when reactive attributes change

    def watch_voice_frame(self, old: str, new: str) -> None:  # type: ignore[override]
        self.refresh()

    def watch_alert_text(self, old: str, new: str) -> None:  # type: ignore[override]
        self.refresh()

    def watch_status_text(self, old: str, new: str) -> None:  # type: ignore[override]
        self.refresh()

    def watch_live_icon(self, old: str, new: str) -> None:  # type: ignore[override]
        self.refresh()
