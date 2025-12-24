"""Telegram notification system with async support."""

import asyncio
import os
from typing import Optional, Any
from datetime import datetime
from functools import wraps

from telegram import Bot, InputFile
from telegram.error import TelegramError, RetryAfter
from telegram.constants import ParseMode

import sys
from pathlib import Path

# Handle both direct execution and module execution
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from src.config import config
    from src.logger import logger
else:
    from ..config import config
    from ..logger import logger


from datetime import timedelta


def handle_rate_limit(max_retries: int = 3):
    """Decorator to handle Telegram rate limits."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except RetryAfter as e:
                    # Handle both int and timedelta for retry_after
                    retry_after = e.retry_after
                    if isinstance(retry_after, timedelta):
                        wait_time = int(retry_after.total_seconds()) + 1
                    else:
                        wait_time = int(retry_after) + 1
                    logger.warning(f"Rate limited. Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                except TelegramError as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"Telegram error (attempt {attempt + 1}): {e}")
                        await asyncio.sleep(2 ** attempt)
                    else:
                        logger.error(f"Telegram error after {max_retries} attempts: {e}")
                        raise
            return None
        return wrapper
    return decorator


class TelegramNotifier:
    """Async Telegram notification handler."""

    # Emoji constants
    EMOJI = {
        "rocket": "🚀",
        "chart_up": "📈",
        "chart_down": "📉",
        "money": "💰",
        "warning": "⚠️",
        "error": "🚨",
        "success": "✅",
        "info": "ℹ️",
        "bell": "🔔",
        "time": "🕐",
        "target": "🎯",
        "fire": "🔥",
        "stop": "🛑",
        "buy": "🟢",
        "sell": "🔴",
        "balance": "💼",
        "profit": "💹",
        "loss": "📉",
    }

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        """
        Initialize Telegram notifier.
        
        Args:
            bot_token: Telegram bot token. Uses config if not provided.
            chat_id: Telegram chat ID. Uses config if not provided.
        """
        self.bot_token = bot_token or config.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or config.TELEGRAM_CHAT_ID
        self.bot: Optional[Bot] = None
        self._enabled = bool(self.bot_token and self.chat_id)

        if not self._enabled:
            logger.warning("Telegram notifications disabled: missing bot token or chat ID")

    async def initialize(self) -> bool:
        """Initialize the Telegram bot."""
        if not self._enabled:
            return False

        try:
            self.bot = Bot(token=self.bot_token)
            # Test connection
            me = await self.bot.get_me()
            logger.info(f"Telegram bot initialized: @{me.username}")
            return True
        except TelegramError as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
            self._enabled = False
            return False

    async def close(self) -> None:
        """Close the bot session."""
        if self.bot:
            try:
                await self.bot.shutdown()
            except Exception:
                pass  # Ignore close errors
            self.bot = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    @handle_rate_limit(max_retries=3)
    async def send_message(
        self,
        text: str,
        parse_mode: str = ParseMode.HTML,
        disable_notification: bool = False
    ) -> bool:
        """
        Send a text message.
        
        Args:
            text: Message text (supports HTML formatting).
            parse_mode: Message parse mode (HTML or Markdown).
            disable_notification: Send silently.
        
        Returns:
            True if sent successfully.
        """
        if not self._enabled or not self.bot:
            logger.debug("Telegram not enabled, skipping message")
            return False

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode,
                disable_notification=disable_notification
            )
            logger.debug("Telegram message sent successfully")
            return True
        except TelegramError as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    @handle_rate_limit(max_retries=3)
    async def send_photo(
        self,
        photo_path: str,
        caption: Optional[str] = None,
        parse_mode: str = ParseMode.HTML,
        delete_after: bool = True
    ) -> bool:
        """
        Send a photo/image file.
        
        Args:
            photo_path: Path to the image file.
            caption: Optional caption for the image.
            parse_mode: Caption parse mode.
            delete_after: Delete the file after sending.
        
        Returns:
            True if sent successfully.
        """
        if not self._enabled or not self.bot:
            logger.debug("Telegram not enabled, skipping photo")
            return False
        
        if not os.path.exists(photo_path):
            logger.error(f"Photo file not found: {photo_path}")
            return False

        try:
            with open(photo_path, "rb") as photo_file:
                await self.bot.send_photo(
                    chat_id=self.chat_id,
                    photo=InputFile(photo_file),
                    caption=caption,
                    parse_mode=parse_mode if caption else None
                )
            logger.debug("Telegram photo sent successfully")
            
            # Delete temp file after sending
            if delete_after:
                try:
                    os.remove(photo_path)
                    logger.debug(f"Deleted temp file: {photo_path}")
                except Exception as e:
                    logger.warning(f"Could not delete temp file: {e}")
            
            return True
        except TelegramError as e:
            logger.error(f"Failed to send Telegram photo: {e}")
            return False

    @handle_rate_limit(max_retries=3)
    async def send_chart(
        self,
        chart_path: str,
        analysis_result: dict,
        delete_after: bool = True
    ) -> bool:
        """
        Send analysis chart with formatted caption.
        
        Args:
            chart_path: Path to the chart image.
            analysis_result: Analysis result dict for caption.
            delete_after: Delete chart file after sending.
        
        Returns:
            True if sent successfully.
        """
        caption = self._build_chart_caption(analysis_result)
        return await self.send_photo(chart_path, caption, delete_after=delete_after)

    def _build_chart_caption(self, result: dict) -> str:
        """Build caption for chart image."""
        if "error" in result:
            return f"❌ {result.get('symbol', 'Unknown')}: {result['error']}"
        
        e = self.EMOJI
        signal = result.get("signal", "HOLD")
        
        signal_emoji = {
            "STRONG_BUY": "🚀🚀",
            "BUY": "🟢",
            "WEAK_BUY": "🟡",
            "HOLD": "⏸️",
            "WEAK_SELL": "🟠",
            "SELL": "🔴",
            "STRONG_SELL": "💥💥"
        }.get(signal, "❓")
        
        trend = result.get("trend", "unknown").replace("_", " ").title()
        
        caption = f"""
{signal_emoji} <b>{result.get('symbol', 'N/A')} - {signal}</b> ({result.get('confidence', 0)}%)

💰 Price: <code>${result.get('price', 0):,.2f}</code>
📊 Trend: {trend}
⚡ RSI: {result.get('rsi', 0):.1f}
📉 MACD: {result.get('macd', {}).get('status', 'N/A').title()}

"""
        
        # Add key reasons (first 3)
        reasons = result.get("reasons", [])[:3]
        if reasons:
            caption += "<b>📋 Analysis:</b>\n"
            for reason in reasons:
                caption += f"• {reason}\n"
        
        # Add warnings
        warnings = result.get("warnings", [])[:2]
        if warnings:
            caption += "\n<b>⚠️ Warnings:</b>\n"
            for warning in warnings:
                caption += f"• {warning}\n"
        
        # Add scores
        scores = result.get("scores", {})
        if scores:
            caption += f"\n🔢 Score: Bull {scores.get('bullish', 0)} | Bear {scores.get('bearish', 0)} | Net {scores.get('net', 0):+d}"
        
        caption += f"\n\n{e['time']} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return caption.strip()

    async def send_signal_alert(self, signal_data: dict) -> bool:
        """
        Send a trading signal alert.
        
        Args:
            signal_data: Dict with keys:
                - symbol: Trading pair (e.g., 'BTCUSDT')
                - side: 'BUY' or 'SELL'
                - price: Current/entry price
                - target: Target price (optional)
                - stop_loss: Stop loss price (optional)
                - reason: Signal reason (optional)
                - confidence: Signal confidence % (optional)
        
        Returns:
            True if sent successfully.
        """
        e = self.EMOJI
        side = signal_data.get("side", "").upper()
        side_emoji = e["buy"] if side == "BUY" else e["sell"]
        
        message = f"""
{e['bell']} <b>TRADING SIGNAL</b> {e['bell']}

{side_emoji} <b>{side}</b> {signal_data.get('symbol', 'N/A')}

{e['money']} <b>Entry Price:</b> <code>{signal_data.get('price', 'N/A')}</code>
"""

        if signal_data.get('target'):
            message += f"{e['target']} <b>Target:</b> <code>{signal_data['target']}</code>\n"
        
        if signal_data.get('stop_loss'):
            message += f"{e['stop']} <b>Stop Loss:</b> <code>{signal_data['stop_loss']}</code>\n"

        if signal_data.get('confidence'):
            message += f"{e['chart_up']} <b>Confidence:</b> {signal_data['confidence']}%\n"

        if signal_data.get('reason'):
            message += f"\n{e['info']} <b>Reason:</b> {signal_data['reason']}\n"

        message += f"\n{e['time']} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        return await self.send_message(message.strip())

    async def send_trade_alert(self, trade_data: dict) -> bool:
        """
        Send a trade execution alert.
        
        Args:
            trade_data: Dict with keys:
                - symbol: Trading pair
                - side: 'BUY' or 'SELL'
                - quantity: Trade quantity
                - price: Execution price
                - total: Total value
                - order_id: Order ID (optional)
                - pnl: Profit/loss (optional)
                - pnl_percent: PnL percentage (optional)
        
        Returns:
            True if sent successfully.
        """
        e = self.EMOJI
        side = trade_data.get("side", "").upper()
        side_emoji = e["buy"] if side == "BUY" else e["sell"]
        
        message = f"""
{e['rocket']} <b>TRADE EXECUTED</b> {e['rocket']}

{side_emoji} <b>{side}</b> {trade_data.get('symbol', 'N/A')}

{e['money']} <b>Price:</b> <code>{trade_data.get('price', 'N/A')}</code>
📊 <b>Quantity:</b> <code>{trade_data.get('quantity', 'N/A')}</code>
💵 <b>Total:</b> <code>{trade_data.get('total', 'N/A')}</code>
"""

        if trade_data.get('order_id'):
            message += f"🆔 <b>Order ID:</b> <code>{trade_data['order_id']}</code>\n"

        if trade_data.get('pnl') is not None:
            pnl = trade_data['pnl']
            pnl_emoji = e['profit'] if pnl >= 0 else e['loss']
            pnl_sign = "+" if pnl >= 0 else ""
            message += f"\n{pnl_emoji} <b>P&L:</b> <code>{pnl_sign}{pnl}</code>"
            
            if trade_data.get('pnl_percent') is not None:
                message += f" ({pnl_sign}{trade_data['pnl_percent']}%)"
            message += "\n"

        message += f"\n{e['time']} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        return await self.send_message(message.strip())

    async def send_error_alert(self, error: Any, context: Optional[str] = None) -> bool:
        """
        Send an error alert.
        
        Args:
            error: Error message or exception.
            context: Additional context about where the error occurred.
        
        Returns:
            True if sent successfully.
        """
        e = self.EMOJI
        error_str = str(error)
        
        message = f"""
{e['error']} <b>ERROR ALERT</b> {e['error']}

{e['warning']} <b>Error:</b>
<code>{error_str[:500]}</code>
"""

        if context:
            message += f"\n📍 <b>Context:</b> {context}\n"

        message += f"\n{e['time']} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        return await self.send_message(message.strip())

    async def send_status_update(self, status_data: dict) -> bool:
        """
        Send a bot status update.
        
        Args:
            status_data: Dict with keys:
                - status: 'online', 'offline', 'warning'
                - balance: Current balance (optional)
                - open_positions: Number of open positions (optional)
                - daily_pnl: Daily P&L (optional)
                - message: Additional message (optional)
        
        Returns:
            True if sent successfully.
        """
        e = self.EMOJI
        status = status_data.get("status", "info").lower()
        
        status_emoji = {
            "online": e["success"],
            "offline": e["stop"],
            "warning": e["warning"],
        }.get(status, e["info"])

        message = f"""
{status_emoji} <b>BOT STATUS: {status.upper()}</b>

"""

        if status_data.get('balance') is not None:
            message += f"{e['balance']} <b>Balance:</b> <code>{status_data['balance']}</code>\n"

        if status_data.get('open_positions') is not None:
            message += f"📊 <b>Open Positions:</b> {status_data['open_positions']}\n"

        if status_data.get('daily_pnl') is not None:
            pnl = status_data['daily_pnl']
            pnl_emoji = e['profit'] if pnl >= 0 else e['loss']
            pnl_sign = "+" if pnl >= 0 else ""
            message += f"{pnl_emoji} <b>Daily P&L:</b> <code>{pnl_sign}{pnl}</code>\n"

        if status_data.get('message'):
            message += f"\n{e['info']} {status_data['message']}\n"

        message += f"\n{e['time']} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        return await self.send_message(message.strip())


# Example usage
async def main():
    """Example usage of TelegramNotifier."""
    async with TelegramNotifier() as notifier:
        # Simple message
        await notifier.send_message("🤖 Bot started successfully!")

        # Signal alert
        await notifier.send_signal_alert({
            "symbol": "BTCUSDT",
            "side": "BUY",
            "price": 42500.00,
            "target": 45000.00,
            "stop_loss": 41000.00,
            "confidence": 85,
            "reason": "RSI oversold + support level"
        })

        # Trade alert
        await notifier.send_trade_alert({
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": 0.001,
            "price": 42500.00,
            "total": 42.50,
            "order_id": "12345678"
        })


if __name__ == "__main__":
    asyncio.run(main())
