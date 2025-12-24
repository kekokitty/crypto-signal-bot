"""Configuration management using environment variables."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    """Application configuration."""

    # Application settings
    APP_NAME: str = os.getenv("APP_NAME", "CryptoBot")
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"

    # Database settings
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "crypto_bot.db"))

    # Logging settings
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", str(BASE_DIR / "logs" / "crypto_bot.log"))

    # Binance API settings
    BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
    BINANCE_SECRET: str = os.getenv("BINANCE_SECRET", "")
    BINANCE_TESTNET: bool = os.getenv("BINANCE_TESTNET", "True").lower() == "true"

    # Telegram settings
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration."""
        if not cls.BINANCE_API_KEY or not cls.BINANCE_SECRET:
            return False
        return True


config = Config()
