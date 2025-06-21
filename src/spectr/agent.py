import os
import tempfile
import json
import threading
import queue
import time

from openai import OpenAI
import pygame
import sounddevice as sd
import soundfile as sf

from news import get_latest_news


class VoiceAgent:
    """Simple wrapper around OpenAI's voice features."""

    def __init__(self, chat_model: str = "gpt-3.5-turbo", tts_model: str = "tts-1-hd", voice: str = "sage") -> None:
        """Initialize the voice agent and OpenAI client."""
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.chat_model = chat_model
        self.tts_model = tts_model
        self.voice = voice
        pygame.mixer.init()
        self._queue: queue.Queue[str] = queue.Queue()
        self._worker = threading.Thread(target=self._speech_worker, daemon=True)
        self._worker.start()

    def say(self, text: str) -> None:
        """Queue *text* to be spoken using OpenAI text-to-speech."""
        self._queue.put(text)

    def _speech_worker(self) -> None:
        while True:
            text = self._queue.get()
            self._speak(text)
            self._queue.task_done()

    def _speak(self, text: str) -> None:
        """Speak *text* using OpenAI text-to-speech."""
        response = self.client.audio.speech.create(
            model=self.tts_model,
            voice=self.voice,
            input=text,
            speed=0.85,
            instructions="""
            Tone: Exciting, high-energy, and persuasive, creating urgency and anticipation.

            Delivery: Rapid-fire yet clear, with dynamic inflections to keep engagement high and momentum strong.

            Pronunciation: Crisp and precise, with emphasis on key action words like bid, buy, checkout, and sold to drive urgency.
            """
        )
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            f.write(response.content)
            fname = f.name
        sound = pygame.mixer.Sound(fname)
        channel = sound.play()
        while channel.get_busy():
            time.sleep(0.5)

    def listen_and_answer(self) -> str:
        """Record a short audio question and reply with a spoken answer."""
        duration = 5
        sample_rate = 16_000
        rec = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1)
        sd.wait()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            sf.write(f.name, rec, sample_rate)
            wav_path = f.name
        with open(wav_path, "rb") as audio_file:
            transcription = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
            user_text = transcription.text

        messages = [{"role": "user", "content": user_text}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_latest_news",
                    "description": "Fetch the most recent news article for a stock symbol",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "Stock ticker"}
                        },
                        "required": ["symbol"],
                    },
                },
            }
        ]

        completion = self.client.chat.completions.create(
            model=self.chat_model,
            messages=messages,
            tools=tools,
        )

        message = completion.choices[0].message
        if message.tool_calls:
            for call in message.tool_calls:
                if call.function.name == "get_latest_news":
                    args = json.loads(call.function.arguments)
                    result = get_latest_news(**args)
                    messages.append({
                        "role": "assistant",
                        "content": "Here is the latest news article for your query.",
                        "tool_call_id": call.id,
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result,
                    })
            completion = self.client.chat.completions.create(
                model=self.chat_model,
                messages=messages,
            )
            reply = completion.choices[0].message.content
        else:
            reply = message.content

        self.say(reply)
        return reply

