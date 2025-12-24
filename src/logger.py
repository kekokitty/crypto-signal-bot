"""Logging configuration for the application."""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

from .config import config


def setup_logger(name: str = "crypto_bot") -> logging.Logger:
    """Set up and configure the application logger."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    # Log format
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler with rotation
    try:
        log_path = Path(config.LOG_FILE)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            filename=config.LOG_FILE,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.warning(f"Could not set up file logging: {e}")

    return logger


# Global logger instance
logger = setup_logger()
