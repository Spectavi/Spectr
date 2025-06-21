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

import pandas as pd

from news import get_latest_news
from fetch.broker_interface import BrokerInterface, OrderSide, OrderType


class VoiceAgent:
    """Simple wrapper around OpenAI's voice features."""

    def __init__(
        self,
        broker_api: BrokerInterface | None = None,
        chat_model: str = "gpt-3.5-turbo",
        tts_model: str = "tts-1-hd",
        voice: str = "sage",
    ) -> None:
        """Initialize the voice agent and OpenAI client."""
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.chat_model = chat_model
        self.tts_model = tts_model
        self.voice = voice
        self.broker = broker_api
        pygame.mixer.init()
        self._queue: queue.Queue[str] = queue.Queue()
        self._worker = threading.Thread(target=self._speech_worker, daemon=True)
        self._worker.start()

        self.tools = self._build_tools()
        self.tool_funcs = self._build_tool_funcs()

        self.wake_word = "spectr"
        self._wake_event: threading.Event | None = None
        self._listen_thread: threading.Thread | None = None

    def _serialize(self, obj):
        """Recursively convert *obj* into JSON serialisable primitives."""
        if obj is None:
            return None
        if isinstance(obj, pd.DataFrame):
            return obj.to_dict(orient="records")
        if isinstance(obj, (list, tuple, set)):
            return [self._serialize(o) for o in obj]
        if isinstance(obj, dict):
            return {k: self._serialize(v) for k, v in obj.items()}
        # UUIDs appear in objects returned by broker APIs
        try:
            import uuid
            if isinstance(obj, uuid.UUID):
                return str(obj)
        except Exception:
            pass
        if hasattr(obj, "model_dump"):
            try:
                return self._serialize(obj.model_dump())
            except Exception:
                pass
        if hasattr(obj, "__dict__"):
            return {
                k: self._serialize(v)
                for k, v in vars(obj).items()
                if not k.startswith("_")
            }
        return obj

    def _build_tools(self) -> list:
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
            },
        ]

        if self.broker:
            tools.extend([
                {
                    "type": "function",
                    "function": {
                        "name": "get_balance",
                        "description": "Return account balance information",
                        "parameters": {"type": "object", "properties": {}, "required": []},
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "has_pending_order",
                        "description": "Check if there is a pending order for a symbol",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "symbol": {"type": "string", "description": "Ticker symbol"}
                            },
                            "required": ["symbol"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "get_pending_orders",
                        "description": "Fetch pending orders for a symbol",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "symbol": {"type": "string", "description": "Ticker symbol"}
                            },
                            "required": ["symbol"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "get_closed_orders",
                        "description": "Fetch all closed orders",
                        "parameters": {"type": "object", "properties": {}, "required": []},
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "get_all_orders",
                        "description": "Fetch all orders on the account",
                        "parameters": {"type": "object", "properties": {}, "required": []},
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "get_orders_for_symbol",
                        "description": "Fetch all orders for a symbol",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "symbol": {"type": "string", "description": "Ticker symbol"}
                            },
                            "required": ["symbol"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "has_position",
                        "description": "Check if a position exists for a symbol",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "symbol": {"type": "string", "description": "Ticker symbol"}
                            },
                            "required": ["symbol"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "get_position",
                        "description": "Fetch position details for a symbol",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "symbol": {"type": "string", "description": "Ticker symbol"}
                            },
                            "required": ["symbol"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "get_positions",
                        "description": "Fetch all open positions",
                        "parameters": {"type": "object", "properties": {}, "required": []},
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "submit_order",
                        "description": "Submit an order",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "symbol": {"type": "string"},
                                "side": {"type": "string", "description": "BUY or SELL"},
                                "type": {"type": "string", "description": "MARKET or LIMIT"},
                                "quantity": {"type": "number"},
                                "limit_price": {"type": "number"},
                                "market_price": {"type": "number"},
                            },
                            "required": ["symbol", "side", "type"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "cancel_order",
                        "description": "Cancel an existing order",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "order_id": {"type": "string"}
                            },
                            "required": ["order_id"],
                        },
                    },
                },
            ])

        return tools

    def _build_tool_funcs(self) -> dict:
        funcs = {
            "get_latest_news": get_latest_news,
        }

        if not self.broker:
            return funcs

        funcs.update(
            {
                "get_balance": lambda: json.dumps(self._serialize(self.broker.get_balance())),
                "has_pending_order": lambda symbol: json.dumps(self.broker.has_pending_order(symbol)),
                "get_pending_orders": lambda symbol: json.dumps(self._serialize(self.broker.get_pending_orders(symbol))),
                "get_closed_orders": lambda: json.dumps(self._serialize(self.broker.get_closed_orders())),
                "get_all_orders": lambda: json.dumps(self._serialize(self.broker.get_all_orders())),
                "get_orders_for_symbol": lambda symbol: json.dumps(self._serialize(self.broker.get_orders_for_symbol(symbol))),
                "has_position": lambda symbol: json.dumps(self.broker.has_position(symbol)),
                "get_position": lambda symbol: json.dumps(self._serialize(self.broker.get_position(symbol))),
                "get_positions": lambda: json.dumps(self._serialize(self.broker.get_positions())),
                "submit_order": lambda symbol, side, type, quantity=None, limit_price=None, market_price=None: json.dumps(
                    self._serialize(
                        self.broker.submit_order(
                            symbol=symbol,
                            side=OrderSide[side.upper()],
                            type=OrderType[type.upper()],
                            quantity=quantity,
                            limit_price=limit_price,
                            market_price=market_price,
                            real_trades=self.broker.real_trades,
                        )
                    )
                ),
                "cancel_order": lambda order_id: json.dumps(self._serialize(self.broker.cancel_order(order_id))),
            }
        )

        return funcs

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
        tools = self.tools

        completion = self.client.chat.completions.create(
            model=self.chat_model,
            messages=messages,
            tools=tools,
        )

        message = completion.choices[0].message
        if message.tool_calls:
            messages.append(message.model_dump())
            for call in message.tool_calls:
                func = self.tool_funcs.get(call.function.name)
                if func:
                    args = json.loads(call.function.arguments)
                    result = func(**args)
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

    # ------------------------------------------------------------------
    # Real-time listening for a wake word
    # ------------------------------------------------------------------
    def start_wake_word_listener(self, wake_word: str = "spectr") -> None:
        """Begin a background thread listening for *wake_word*."""
        if self._listen_thread and self._listen_thread.is_alive():
            return

        self.wake_word = wake_word.lower()
        self._wake_event = threading.Event()
        self._listen_thread = threading.Thread(
            target=self._wake_word_loop, daemon=True
        )
        self._listen_thread.start()

    def stop_wake_word_listener(self) -> None:
        """Stop the background wake word listener."""
        if self._wake_event:
            self._wake_event.set()
        if self._listen_thread and self._listen_thread.is_alive():
            self._listen_thread.join(timeout=1.0)

    def _wake_word_loop(self) -> None:
        sample_rate = 16_000
        duration = 2
        while not self._wake_event.is_set():
            rec = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1)
            sd.wait()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                sf.write(f.name, rec, sample_rate)
                wav_path = f.name
            try:
                with open(wav_path, "rb") as audio_file:
                    transcription = self.client.audio.transcriptions.create(
                        model="whisper-1", file=audio_file
                    )
                text = transcription.text.lower()
                if self.wake_word in text:
                    self.say("Yes?")
                    self.listen_and_answer()
            except Exception:
                pass

