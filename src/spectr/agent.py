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
import requests

import pandas as pd

from news import get_latest_news, get_recent_news
from fetch.broker_interface import BrokerInterface, OrderSide, OrderType
from spectr.exceptions import DataApiRateLimitError


class VoiceAgent:
    """Simple wrapper around OpenAI's voice features."""

    def __init__(
        self,
        broker_api: BrokerInterface | None = None,
        data_api: object | None = None,
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
        self.data_api = data_api
        pygame.mixer.init()
        self._queue: queue.Queue[tuple[str, threading.Event | None]] = queue.Queue()
        self._worker = threading.Thread(target=self._speech_worker, daemon=True)
        self._worker.start()

        self.system_prompt = (
            "You are a helpful trading assistant. "
            "Use the provided tools to fetch market data such as float, quotes or charts. "
            "Do not claim you lack real-time data; instead call the tools when needed and respond concisely."
        )
        # Keep track of the full chat history so conversations persist between
        # invocations of ``listen_and_answer``.
        self.chat_history: list[dict] = [
            {"role": "system", "content": self.system_prompt}
        ]

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
        # Represent datetime objects in ISO format so json.dumps works
        try:
            from datetime import datetime, date, time as dt_time
            if isinstance(obj, (datetime, date, dt_time)):
                return obj.isoformat()
        except Exception:
            pass
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
            {
                "type": "function",
                "function": {
                    "name": "get_recent_news",
                    "description": "Fetch recent news articles for a stock symbol",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "Stock ticker"},
                            "days": {"type": "integer", "description": "Days of history", "default": 30},
                        },
                        "required": ["symbol"],
                    },
                },
            },
        ]

        if self.data_api:
            tools.extend(
                [
                    {
                        "type": "function",
                        "function": {
                            "name": "get_company_profile",
                            "description": "Fetch company profile information",
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
                            "name": "get_quote",
                            "description": "Return only the latest price for a symbol",
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
                            "name": "get_bid_ask",
                            "description": "Return current bid and ask prices",
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
                            "name": "get_float",
                            "description": "Return float shares for a symbol",
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
                            "name": "get_volume",
                            "description": "Return current volume for a symbol",
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
                            "name": "get_chart_data",
                            "description": "Fetch recent chart data for a symbol",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "symbol": {"type": "string", "description": "Ticker symbol"},
                                    "from_date": {"type": "string", "description": "YYYY-MM-DD"},
                                    "to_date": {"type": "string", "description": "YYYY-MM-DD"},
                                },
                                "required": ["symbol", "from_date", "to_date"],
                            },
                        },
                    },
                ]
            )

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
            "get_recent_news": lambda symbol, days=30: json.dumps(
                get_recent_news(symbol, days)
            ),
        }

        if self.data_api:
            funcs.update(
                {
                    "get_company_profile": lambda symbol: json.dumps(
                        self._serialize(self.data_api.fetch_company_profile(symbol))
                    ),
                    "get_quote": lambda symbol: json.dumps(
                        (lambda q: q.get("price")
                        or q.get("last_trade_price")
                        or q.get("lastTradePrice")
                        or q.get("close"))(self.data_api.fetch_quote(symbol))
                    ),
                    "get_bid_ask": lambda symbol: json.dumps(
                        {
                            "bid": (
                                self.data_api.fetch_quote(symbol).get("bid")
                                or self.data_api.fetch_quote(symbol).get("bidPrice")
                                or self.data_api.fetch_quote(symbol).get("bid_price")
                            ),
                            "ask": (
                                self.data_api.fetch_quote(symbol).get("ask")
                                or self.data_api.fetch_quote(symbol).get("askPrice")
                                or self.data_api.fetch_quote(symbol).get("ask_price")
                            ),
                        }
                    ),
                    "get_float": lambda symbol: json.dumps(
                        (
                            self.data_api.fetch_company_profile(symbol).get("float")
                            or self.data_api.fetch_company_profile(symbol).get("floatShares")
                            or self.data_api.fetch_company_profile(symbol).get("sharesOutstanding")
                        )
                    ),
                    "get_volume": lambda symbol: json.dumps(
                        self.data_api.fetch_quote(symbol).get("volume")
                    ),
                    "get_chart_data": lambda symbol, from_date, to_date: json.dumps(
                        self._serialize(
                            self.data_api.fetch_chart_data(symbol, from_date, to_date)
                        )
                    ),
                }
            )

        if self.broker:
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

    def say(self, text: str, wait: bool = False) -> None:
        """Queue *text* to be spoken using OpenAI text-to-speech.

        If ``wait`` is ``True`` this method will block until the speech has
        finished playing.  This is useful for cases like the application start
        up splash screen where we don't want to proceed until the welcome
        message is complete.
        """
        done = threading.Event() if wait else None
        self._queue.put((text, done))
        if wait:
            done.wait()

    def _speech_worker(self) -> None:
        while True:
            text, done = self._queue.get()
            self._speak(text)
            if done is not None:
                done.set()
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

        # Append the user's question so future calls retain context
        self.chat_history.append({"role": "user", "content": user_text})
        tools = self.tools

        completion = self.client.chat.completions.create(
            model=self.chat_model,
            messages=self.chat_history,
            tools=tools,
        )

        message = completion.choices[0].message
        if message.tool_calls:
            self.chat_history.append(message.model_dump())
            for call in message.tool_calls:
                func = self.tool_funcs.get(call.function.name)
                if func:
                    args = json.loads(call.function.arguments)
                    try:
                        result = func(**args)
                    except DataApiRateLimitError:
                        self.say(
                            "The data provider is rate limiting us. Please try again shortly."
                        )
                        return ""
                    except requests.HTTPError as exc:
                        if exc.response is not None and exc.response.status_code == 429:
                            self.say(
                                "The data provider is rate limiting us. Please try again shortly."
                            )
                            return ""
                        raise
                    self.chat_history.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": result,
                        }
                    )
            completion = self.client.chat.completions.create(
                model=self.chat_model,
                messages=self.chat_history,
            )
            reply_message = completion.choices[0].message
            reply = reply_message.content
            self.chat_history.append(reply_message.model_dump())
        else:
            reply = message.content
            self.chat_history.append({"role": "assistant", "content": reply})

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

