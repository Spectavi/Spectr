import os
import tempfile

import openai
import pygame
import sounddevice as sd
import soundfile as sf


class VoiceAgent:
    """Simple wrapper around OpenAI's voice features."""

    def __init__(self, chat_model: str = "gpt-3.5-turbo", tts_model: str = "tts-1", voice: str = "nova") -> None:
        openai.api_key = os.getenv("OPENAI_API_KEY")
        self.chat_model = chat_model
        self.tts_model = tts_model
        self.voice = voice
        pygame.mixer.init()

    def say(self, text: str) -> None:
        """Speak *text* using OpenAI text-to-speech."""
        response = openai.audio.speech.create(
            model=self.tts_model,
            voice=self.voice,
            input=text,
        )
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            f.write(response.content)
            fname = f.name
        pygame.mixer.Sound(fname).play()

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
            user_text = openai.Audio.transcribe("whisper-1", audio_file)["text"]
        completion = openai.chat.completions.create(
            model=self.chat_model,
            messages=[{"role": "user", "content": user_text}],
        )
        reply = completion.choices[0].message.content
        self.say(reply)
        return reply

