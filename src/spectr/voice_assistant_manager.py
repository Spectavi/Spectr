from .agent import VoiceAgent


class VoiceAssistantManager:
    def __init__(
        self,
        broker_api,
        data_api,
        get_cached_orders,
        add_symbol,
        remove_symbol,
        get_strategy_code,
        show_markdown,
        args,
    ):
        self._voice_worker = None
        self._voice_stop_event = None
        self._voice_is_recording = False
        self.voice_agent = None

        if os.getenv("OPENAI_API_KEY"):
            self.voice_agent = VoiceAgent(
                broker_api=broker_api,
                data_api=data_api,
                get_cached_orders=get_cached_orders,
                add_symbol=add_symbol,
                remove_symbol=remove_symbol,
                get_strategy_code=get_strategy_code,
                show_markdown=show_markdown,
                stream_voice=getattr(args, "voice_streaming", False),
                mic_device=_parse_int("MIC_DEVICE"),
                mic_gain=_parse_float("MIC_GAIN", 1.0),
                tts_volume=_parse_float("TTS_VOLUME", 1.0),
            )
            if getattr(args, "listen", False):
                self.voice_agent.start_wake_word_listener(
                    getattr(args, "wake_word", "spectr")
                )
        else:
            self.voice_agent = None

    def start_wake_word_listener(self, wake_word: str):
        if self.voice_agent:
            self.voice_agent.start_wake_word_listener(wake_word)

    def stop_wake_word_listener(self):
        if self.voice_agent:
            self.voice_agent.stop_wake_word_listener()

    def say(self, message: str, wait: bool = False):
        if self.voice_agent:
            self.voice_agent.say(message, wait=wait)

    def ask_agent(self, overlay, call_from_thread, update_status_bar):
        if not self.voice_agent or self._voice_is_recording:
            return

        self._voice_stop_event = threading.Event()
        self._voice_is_recording = True
        self._voice_worker = self.run_worker(
            lambda: self._ask_agent(self._voice_stop_event),
            thread=True,
        )

    def _ask_agent(self, stop_event):
        if not self.voice_agent:
            return

        overlay = self.overlay
        call_from_thread(overlay.show_prompt, "Recording... press V to stop")

        def _status(ev):
            try:
                if ev == "processing":
                    self._voice_is_recording = False
                    call_from_thread(overlay.show_prompt, "Processing...")
                elif ev == "listening":
                    self._voice_is_recording = True
                    call_from_thread(
                        overlay.show_prompt, "Recording... press V to stop"
                    )
            except Exception:
                pass

        try:
            self.voice_agent.listen_and_answer(
                status_cb=_status,
                stop_record_event=stop_event,
                use_silence_detection=False,
            )
        except Exception as exc:
            log.error("Voice agent error: %s", traceback.format_exc())
            call_from_thread(overlay.clear_prompt)
            call_from_thread(overlay.flash_message, f"Voice error: {exc}")
        else:
            call_from_thread(overlay.clear_prompt)
        finally:
            self._voice_stop_event = None
            self._voice_is_recording = False
            call_from_thread(update_status_bar)
            self._voice_worker = None

    def stop(self):
        if self._voice_worker and self._voice_worker.is_running:
            if self._voice_is_recording and self._voice_stop_event:
                self._voice_stop_event.set()
            else:
                if self.voice_agent:
                    self.voice_agent.stop()
                self._voice_worker.cancel()
                self._voice_worker = None

    def cleanup(self):
        try:
            if self.voice_agent:
                self.voice_agent.stop()
        except Exception as e:
            log.debug(f"Error stopping voice agent: {e}")
        try:
            if self._voice_worker and self._voice_worker.is_running:
                self._voice_worker.cancel()
                self._voice_worker = None
        except Exception as e:
            log.debug(f"Error cancelling voice worker: {e}")

    def __del__(self):
        self.cleanup()


def _parse_float(env, default):
    try:
        return float(os.getenv(env, "")) if os.getenv(env) else default
    except Exception:
        return default


def _parse_int(env):
    try:
        return int(os.getenv(env, "")) if os.getenv(env) else None
    except Exception:
        return None
