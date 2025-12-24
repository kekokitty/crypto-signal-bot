"""Quick Telegram test script."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.notifications import TelegramNotifier


async def test():
    async with TelegramNotifier() as notifier:
        # Test mesajı
        await notifier.send_message("🤖 <b>CryptoBot</b> başarıyla bağlandı!")
        
        # Örnek sinyal
        await notifier.send_signal_alert({
            "symbol": "BTCUSDT",
            "side": "BUY",
            "price": 95000.00,
            "target": 100000.00,
            "stop_loss": 92000.00,
            "confidence": 75,
            "reason": "Test sinyali"
        })
        
        print("✅ Telegram mesajları gönderildi!")


if __name__ == "__main__":
    asyncio.run(test())
