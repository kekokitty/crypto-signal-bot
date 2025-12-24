"""Test enhanced technical analysis module."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.analysis import analyze, format_analysis_report
from src.notifications import TelegramNotifier


def build_telegram_message(result: dict) -> str:
    """Build formatted Telegram message from analysis result."""
    if "error" in result:
        return f"❌ {result['symbol']}: {result['error']}"
    
    signal_emoji = {
        "STRONG_BUY": "🚀🚀",
        "BUY": "🟢",
        "WEAK_BUY": "🟡",
        "HOLD": "⏸️",
        "WEAK_SELL": "🟠",
        "SELL": "🔴",
        "STRONG_SELL": "💥💥"
    }
    
    trend_emoji = {
        "strong_up": "📈📈",
        "weak_up": "📈",
        "ranging": "➡️",
        "weak_down": "📉",
        "strong_down": "📉📉"
    }
    
    emoji = signal_emoji.get(result["signal"], "❓")
    trend_e = trend_emoji.get(result["trend"], "❓")
    
    msg = f"""
{emoji} <b>{result['symbol']} - {result['signal']}</b> ({result['confidence']}%)

💰 <b>Price:</b> <code>${result['price']:,.2f}</code>
{trend_e} <b>Trend:</b> {result['trend'].replace('_', ' ').title()}
📊 <b>Volume:</b> {result['volume_status'].title()} ({result['volume']['ratio']:.1f}x)

📉 EMA20: <code>${result['ema20']:,.2f}</code>
📉 EMA50: <code>${result['ema50']:,.2f}</code>
📉 EMA200: <code>${result['ema200']:,.2f}</code>

⚡ RSI: <code>{result['rsi']:.1f}</code>
📊 MACD: {result['macd']['status'].title()}
📏 ATR: <code>${result['atr']:,.2f}</code>
"""

    if result['support']:
        msg += f"\n🟢 Support: <code>${result['support']['level']:,.2f}</code> ({result['support']['distance_atr']:.1f} ATR)"
    
    if result['resistance']:
        msg += f"\n🔴 Resistance: <code>${result['resistance']['level']:,.2f}</code> ({result['resistance']['distance_atr']:.1f} ATR)"
    
    if result['sr_flip']['flip_detected']:
        flip_emoji = "🔄🟢" if result['sr_flip']['flip_type'] == "bullish" else "🔄🔴"
        msg += f"\n{flip_emoji} S/R Flip: {result['sr_flip']['flip_type'].title()}"
    
    msg += f"\n\n<b>📋 Analysis:</b>"
    for reason in result['reasons'][:5]:  # Limit to 5 reasons
        msg += f"\n• {reason}"
    
    if result['warnings']:
        msg += f"\n\n<b>⚠️ Warnings:</b>"
        for warning in result['warnings'][:3]:  # Limit to 3 warnings
            msg += f"\n• {warning}"
    
    msg += f"\n\n🔢 <b>Score:</b> Bull {result['scores']['bullish']} | Bear {result['scores']['bearish']} | Net {result['scores']['net']:+d}"
    
    return msg.strip()


async def test_analysis():
    """Run enhanced analysis and send to Telegram."""
    
    # Analyze BTCUSDT
    print("\n🔍 Analyzing BTCUSDT with enhanced strategy...")
    result = await analyze("BTCUSDT", "1h")
    
    # Print detailed report
    print(format_analysis_report(result))
    
    # Send to Telegram
    async with TelegramNotifier() as notifier:
        msg = build_telegram_message(result)
        await notifier.send_message(msg)
        print("\n✅ Analysis sent to Telegram!")


async def test_multiple():
    """Test analyzing multiple symbols."""
    from src.analysis import analyze_multiple
    
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
    print(f"\n🔍 Analyzing {len(symbols)} symbols...")
    
    results = await analyze_multiple(symbols, "1h")
    
    for result in results:
        print(format_analysis_report(result))
    
    # Send summary to Telegram
    async with TelegramNotifier() as notifier:
        summary = "📊 <b>MARKET SCAN RESULTS</b>\n\n"
        for r in results:
            if "error" not in r:
                signal_emoji = {"STRONG_BUY": "🚀", "BUY": "🟢", "WEAK_BUY": "🟡", "HOLD": "⏸️", "WEAK_SELL": "🟠", "SELL": "🔴", "STRONG_SELL": "💥"}.get(r["signal"], "❓")
                summary += f"{signal_emoji} <b>{r['symbol']}</b>: {r['signal']} ({r['confidence']}%)\n"
        
        await notifier.send_message(summary)
        print("\n✅ Summary sent to Telegram!")


if __name__ == "__main__":
    asyncio.run(test_analysis())
    # asyncio.run(test_multiple())  # Uncomment to test multiple symbols
