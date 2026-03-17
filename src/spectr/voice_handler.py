"""Voice agent handling for SpectrApp."""
import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .spectr import SpectrApp

log = logging.getLogger(__name__)


class VoiceHandler:
    """Handles voice agent operations and interactions."""

    def __init__(self, app: "SpectrApp"):
        self.app = app

    def action_ask_agent(self) -> None:
        if not self.app.voice_agent or self._is_splash_active():
            return
        if self.app._voice_worker and self.app._voice_worker.is_running:
            if self.app._voice_is_recording and self.app._voice_stop_event:
                self.app._voice_stop_event.set()
            else:
                if self.app.voice_agent:
                    self.app.voice_agent.stop()
                self.app._voice_worker.cancel()
                self.app.overlay.clear_prompt()
                self.update_status_bar()
            return
        if self.app._voice_is_recording and not self.app._voice_stop_event:
            if self.app.voice_agent:
                self.app.voice_agent.stop()
            self.app._voice_worker = None
            self.app.overlay.clear_prompt()
            self.update_status_bar()
            return
        self.app._voice_stop_event = threading.Event()
        self.app._voice_is_recording = True
        self.app._voice_worker = self.app.run_worker(
            lambda: self._ask_agent(self.app._voice_stop_event),
            thread=True,
        )

    def _ask_agent(self, stop_event: threading.Event | None = None) -> None:
        if not self.app.voice_agent:
            return
        overlay = self.app.overlay
        self.call_from_thread(overlay.show_prompt, "Recording... press V to stop")

        def _status(ev: str) -> None:
            try:
                if ev == "processing":
                    self.app._voice_is_recording = False
                    self.call_from_thread(overlay.show_prompt, "Processing...")
                elif ev == "speaking":
                    self.app._voice_is_recording = False
                    self.call_from_thread(overlay.show_prompt, "Speaking...")
                elif ev == "listening":
                    self.app._voice_is_recording = True
                    self.call_from_thread(
                        overlay.show_prompt, "Recording... press V to stop"
                    )
            except Exception:
                pass

        try:
            self.app.voice_agent.listen_and_answer(
                status_cb=_status,
                stop_record_event=stop_event,
                use_silence_detection=False,
            )
        except Exception as exc:
            log.error("Voice agent error: %s", exc)
            self.call_from_thread(overlay.clear_prompt)
            self.call_from_thread(
                overlay.flash_message,
                f"Voice error: {exc}",
            )
        else:
            self.call_from_thread(overlay.clear_prompt)
        finally:
            self.app._voice_stop_event = None
            self.app._voice_is_recording = False
            self.call_from_thread(self.update_status_bar)
            self.app._voice_worker = None

    def _is_splash_active(self) -> bool:
        from .views.splash_screen import SplashScreen
        return bool(
            self.app.screen_stack and isinstance(self.app.screen_stack[-1], SplashScreen)
        )

    def call_from_thread(self, func, *args, **kwargs):
        if hasattr(self.app, "call_from_thread"):
            return self.app.call_from_thread(func, *args, **kwargs)
        return func(*args, **kwargs)

    def update_status_bar(self) -> None:
        self.app.update_status_bar()
