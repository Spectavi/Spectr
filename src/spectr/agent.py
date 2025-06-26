import logging
import os
import tempfile
import json
import threading
import queue
import time
from typing import Callable, Optional

from openai import OpenAI
import pygame
try:  # optional voice dependencies
    import sounddevice as sd
    import soundfile as sf
except Exception:  # pragma: no cover - missing portaudio
    sd = None
    sf = None
import requests

import pandas as pd
import numpy as np


from .news import get_latest_news, get_recent_news
from . import cache
from .fetch.broker_interface import BrokerInterface, OrderSide, OrderType

log = logging.getLogger(__name__)


class VoiceAgent:
    """Simple wrapper around OpenAI's voice features."""

    def __init__(
        self,
        broker_api: BrokerInterface | None = None,
        data_api: object | None = None,
        chat_model: str = "o3-mini",
        tts_model: str = "gpt-4o-mini-tts",
        voice: str = "sage",
        get_cached_orders: Optional[Callable[[], list]] | None = None,
        add_symbol: Optional[Callable[[str], list]] | None = None,
        remove_symbol: Optional[Callable[[str], list]] | None = None,
        get_strategy_code: Optional[Callable[[], str]] | None = None,
        on_speech_start: Optional[Callable[[], None]] | None = None,
        on_speech_end: Optional[Callable[[], None]] | None = None,
        stream_voice: bool = False,
    ) -> None:
        """Initialize the voice agent and OpenAI client."""
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.chat_model = chat_model
        self.tts_model = tts_model
        self.voice = voice
        self.broker = broker_api
        self.data_api = data_api
        self._get_cached_orders = get_cached_orders
        self._add_symbol = add_symbol
        self._remove_symbol = remove_symbol
        self._get_strategy_code = get_strategy_code
        self._on_speech_start = on_speech_start
        self._on_speech_end = on_speech_end
        self.stream_voice = stream_voice
        pygame.mixer.init()
        self._stop_event = threading.Event()
        self._current_channel: pygame.mixer.Channel | None = None
        self._queue: queue.Queue[tuple[str, threading.Event | None]] = queue.Queue()
        self._worker = threading.Thread(target=self._speech_worker, daemon=True)
        self._worker.start()

        self.system_prompt = ("""
            You are a helpful trading assistant who talks like a British Financial News anchor.
            Use the provided tools to fetch market data such as a symbols float, quotes or chart data.
            Use that data to answer questions about stocks, ETFs, and other financial instruments.
            Do NOT ever claim that you lack real-time data if you have a tool that gets you that data; instead call the tools and respond concisely.
            You should always be friendly and helpful, but also sound like a professional financial news anchor.
            Spectr should be pronounced like "Specter".
        """
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
                    "description": "Fetch only the most recent news article for a stock symbol",
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
                    "description": "Fetch all recent news articles for a stock symbol",
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
            {
                "type": "function",
                "function": {
                    "name": "get_scanner_cache",
                    "description": "Return cached scanner results",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_gainers_cache",
                    "description": "Return cached top gainers data",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
        ]

        if self._add_symbol:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "add_symbol",
                        "description": "Add a ticker to the watch list and return the updated list",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "symbol": {"type": "string", "description": "Ticker symbol"}
                            },
                            "required": ["symbol"],
                        },
                    },
                }
            )

        if self._remove_symbol:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "remove_symbol",
                        "description": "Remove a ticker from the watch list and return the updated list",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "symbol": {"type": "string", "description": "Ticker symbol"}
                            },
                            "required": ["symbol"],
                        },
                    },
                }
            )

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

        if self._get_cached_orders:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "get_cached_orders",
                        "description": "Return cached portfolio orders if available",
                        "parameters": {"type": "object", "properties": {}, "required": []},
                    },
                }
            )

        if self._get_strategy_code:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "get_strategy_code",
                        "description": "Return the source code of the active trading strategy",
                        "parameters": {"type": "object", "properties": {}, "required": []},
                    },
                }
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
                        "description": "Fetch pending orders for a specific symbol",
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
                        "description": "Fetch all orders for a specific symbol",
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
                        "description": "Check if a position exists for a specific symbol",
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
                        "description": "Fetch position details for a specific symbol",
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
            "get_scanner_cache": lambda: json.dumps(
                self._serialize(cache.load_scanner_cache())
            ),
            "get_gainers_cache": lambda: json.dumps(
                self._serialize(cache.load_gainers_cache())
            ),
        }

        if self._add_symbol:
            funcs["add_symbol"] = lambda symbol: json.dumps(
                self._serialize(self._add_symbol(symbol))
            )

        if self._remove_symbol:
            funcs["remove_symbol"] = lambda symbol: json.dumps(
                self._serialize(self._remove_symbol(symbol))
            )

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

        if self._get_cached_orders:
            funcs["get_cached_orders"] = lambda: json.dumps(
                self._serialize(self._get_cached_orders() or [])
            )

        if self._get_strategy_code:
            funcs["get_strategy_code"] = lambda: json.dumps(
                self._get_strategy_code()
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
        if self._queue.qsize() == 1 and self._on_speech_start:
            try:
                self._on_speech_start()
            except Exception:
                pass
        if wait:
            done.wait()

    def stop(self) -> None:
        """Immediately stop speaking and clear any queued speech."""
        self._stop_event.set()
        if self._current_channel is not None:
            try:
                self._current_channel.stop()
            except Exception:
                pass
        while not self._queue.empty():
            try:
                _, done = self._queue.get_nowait()
                if done is not None:
                    done.set()
                self._queue.task_done()
            except Exception:
                break
        if self._on_speech_end:
            try:
                self._on_speech_end()
            except Exception:
                pass

    def _speech_worker(self) -> None:
        while True:
            text, done = self._queue.get()
            if self._stop_event.is_set():
                if done is not None:
                    done.set()
                self._queue.task_done()
                self._stop_event.clear()
                continue
            self._speak(text)
            if done is not None:
                done.set()
            self._queue.task_done()
            if self._queue.empty() and self._on_speech_end:
                try:
                    self._on_speech_end()
                except Exception:
                    pass

    def _speak(self, text: str) -> None:
        """Speak *text* using OpenAI text-to-speech."""
        params = dict(
            model=self.tts_model,
            voice=self.voice,
            input=text,
            speed=0.95,
            instructions="""
            Voice: Warm, upbeat, and reassuring, with a steady and confident cadence that keeps the conversation calm and productive.

Tone: Positive and solution-oriented, always focusing on the next steps rather than dwelling on the problem.

Dialect: Neutral and professional, avoiding overly casual speech but maintaining a friendly and approachable style.

Pronunciation: Clear and precise, with a natural rhythm that emphasizes key words to instill confidence and keep the customer engaged.

Features: Uses empathetic phrasing, gentle reassurance, and proactive language to shift the focus from frustration to resolution.
            """,
        )
        audio_bytes = b""
        try:
            if self.stream_voice:
                # Newer openai clients use ``with_streaming_response``
                if hasattr(self.client.audio.speech, "with_streaming_response"):
                    resp = self.client.audio.speech.with_streaming_response.create(
                        **params,
                        stream_format="audio",
                    )
                    audio_bytes = b"".join(resp.iter_bytes())
                else:
                    resp = self.client.audio.speech.create(
                        **params,
                        stream=True,
                    )
                    audio_bytes = b"".join(chunk.content for chunk in resp)
            else:
                resp = self.client.audio.speech.create(**params)
                audio_bytes = resp.content
        except TypeError:
            # Fallback for older openai clients expecting ``stream`` parameter
            resp = self.client.audio.speech.create(
                **params,
                stream=self.stream_voice,
            )
            if self.stream_voice:
                audio_bytes = b"".join(chunk.content for chunk in resp)
            else:
                audio_bytes = resp.content
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            f.write(audio_bytes)
            fname = f.name
        sound = pygame.mixer.Sound(fname)
        channel = sound.play()
        self._current_channel = channel
        while channel.get_busy():
            if self._stop_event.is_set():
                channel.stop()
                break
            time.sleep(0.5)
        self._current_channel = None
        self._stop_event.clear()

    def listen_and_answer(self, cancel_event: threading.Event | None = None) -> str:
        """Record a short audio question and reply with a spoken answer.

        If ``cancel_event`` is set while recording or generating a response the
        method will abort early.
        """
        if cancel_event is None:
            cancel_event = self._stop_event
        if sd is None or sf is None:
            raise RuntimeError(
                "sounddevice and soundfile are required for voice features"
            )
        sample_rate = 16_000
        max_duration = 60  # safety valve to avoid runaway recording
        silence_threshold = 0.01
        silence_secs = 1.5
        buffers: list[np.ndarray] = []
        silence_start: float | None = None
        start_time = time.time()
        with sd.InputStream(samplerate=sample_rate, channels=1) as stream:
            while True:
                if cancel_event.is_set():
                    return ""
                data, _ = stream.read(int(sample_rate * 0.1))
                buffers.append(data.copy())
                # compute RMS amplitude to detect silence
                amp = float(np.sqrt(np.mean(data ** 2)))
                if amp < silence_threshold:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start >= silence_secs:
                        break
                else:
                    silence_start = None

                if cancel_event.is_set():
                    return ""
                if time.time() - start_time > max_duration:
                    break

        rec = np.concatenate(buffers, axis=0)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            sf.write(f.name, rec, sample_rate)
            wav_path = f.name
        if cancel_event.is_set():
            return ""
        with open(wav_path, "rb") as audio_file:
            transcription = self.client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=audio_file,
            )
            user_text = transcription.text

        # Append the user's question so future calls retain context
        self.chat_history.append({"role": "user", "content": user_text})
        log.info(f"User asked: {user_text}")
        tools = self.tools

        if cancel_event.is_set():
            return ""
        completion = self.client.chat.completions.create(
            model=self.chat_model,
            messages=self.chat_history,
            tools=tools,
        )

        if cancel_event.is_set():
            return ""
        message = completion.choices[0].message
        if message.tool_calls:
            self.chat_history.append(message.model_dump())
            for call in message.tool_calls:
                func = self.tool_funcs.get(call.function.name)
                if func:
                    args = json.loads(call.function.arguments)
                    try:
                        result = func(**args)
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
            if cancel_event.is_set():
                return ""
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

        if cancel_event.is_set():
            return ""
        self.say(reply)
        return reply

    # ------------------------------------------------------------------
    # Real-time listening for a wake word
    # ------------------------------------------------------------------
    def start_wake_word_listener(self, wake_word: str = "spectr") -> None:
        """Begin a background thread listening for *wake_word*."""
        if sd is None or sf is None:
            raise RuntimeError(
                "sounddevice and soundfile are required for voice features"
            )
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
        if sd is None or sf is None:
            return
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
                    #self.say("Yes?")
                    self.listen_and_answer()
            except Exception:
                pass

