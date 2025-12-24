"""SQLite database connection and initialization."""

import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Generator, Optional

from .config import config
from .logger import logger


class Database:
    """SQLite database manager."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize database connection."""
        self.db_path = db_path or config.DATABASE_PATH
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """Ensure the database directory exists."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        """Initialize database with required tables."""
        logger.info("Initializing database...")

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Example: Trades table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Example: Bot state table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            logger.info("Database initialized successfully.")

    def health_check(self) -> bool:
        """Check if database is accessible."""
        try:
            with self.get_connection() as conn:
                conn.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False


# Global database instance
db = Database()
