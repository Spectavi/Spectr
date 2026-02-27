import logging
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AppConfig:
    """Configuration values for indicator analysis and trading."""

    macd_thresh: float = 0.002
    bb_period: int = 200
    bb_dev: float = 2.0
    stop_loss_pct: float = 0.01
    take_profit_pct: float = 0.05
    lookback_period: int = 1000
    interval: str = "1min"
    scale: float = 0.2

    @classmethod
    def load(cls) -> "AppConfig":
        """Load configuration with validation."""
        config = cls()
        return config


REFRESH_INTERVAL = 60
SCANNER_INTERVAL = REFRESH_INTERVAL
EQUITY_INTERVAL = 60
ORDER_STATUS_INTERVAL = 60

SOUND_PATHS = {
    "buy": "res/buy.mp3",
    "sell": "res/sell.mp3",
    "intro": "res/intro.mp3",
    "order_success": "res/order_success.mp3",
}

LOG_PATH = "debug.log"

BUY_SOUND_PATH = SOUND_PATHS["buy"]
SELL_SOUND_PATH = SOUND_PATHS["sell"]
INTRO_SOUND_PATH = SOUND_PATHS["intro"]
ORDER_SUCCESS_SOUND_PATH = SOUND_PATHS["order_success"]


def setup_logging():
    """Configure logging to file."""
    logging.basicConfig(
        filename=LOG_PATH,
        filemode="w",
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


log = logging.getLogger(__name__)


class VoiceConfig:
    """Configuration for the voice agent."""

    WAKE_WORD: str = "spectr"
    DEFAULT_TTS_VOLUME: float = 1.0
    DEFAULT_MIC_GAIN: float = 1.0
    DEFAULT_MIC_DEVICE: int | None = None

    @classmethod
    def get_tts_volume(cls) -> float:
        """Get TTS volume from environment or use default."""
        try:
            return float(os.getenv("TTS_VOLUME", ""))
        except (ValueError, TypeError):
            return cls.DEFAULT_TTS_VOLUME

    @classmethod
    def get_mic_gain(cls) -> float:
        """Get mic gain from environment or use default."""
        try:
            return float(os.getenv("MIC_GAIN", ""))
        except (ValueError, TypeError):
            return cls.DEFAULT_MIC_GAIN

    @classmethod
    def get_mic_device(cls) -> int | None:
        """Get mic device from environment or use default."""
        try:
            return int(os.getenv("MIC_DEVICE", ""))
        except (ValueError, TypeError):
            return cls.DEFAULT_MIC_DEVICE


class MarketConfig:
    """Market-related configuration."""

    TRADING_HOURS_BUFFER_SECONDS: int = 300
    EQUITY_CUTOFF_HOURS: int = 4
    MIN_PRICE_THRESHOLD: float = 1.0
    MAX_PRICE_THRESHOLD: float = 50.0
    MIN_VOLUME_THRESHOLD: int = 50000
    MIN_FLOAT_THRESHOLD: int = 10000000


class SoundPaths:
    """Sound file paths for various actions."""

    BUY = SOUND_PATHS["buy"]
    SELL = SOUND_PATHS["sell"]
    INTRO = SOUND_PATHS["intro"]
    ORDER_SUCCESS = SOUND_PATHS["order_success"]


class OrderIntervals:
    """Order status update intervals."""

    REFRESH = ORDER_STATUS_INTERVAL


class ScanIntervals:
    """Scanner update intervals."""

    REFRESH = SCANNER_INTERVAL


class EquityIntervals:
    """Portfolio equity update intervals."""

    REFRESH = EQUITY_INTERVAL
