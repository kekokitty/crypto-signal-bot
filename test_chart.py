"""Test chart generation and Telegram sending."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.analysis import analyze, get_candles
from src.visualization import generate_analysis_chart
from src.notifications import TelegramNotifier


async def test_chart_generation():
    """Test generating chart and sending to Telegram."""
    
    symbol = "BTCUSDT"
    timeframe = "1h"
    
    print(f"\n🔍 Analyzing {symbol}...")
    
    # Get analysis result
    result = await analyze(symbol, timeframe)
    
    print(f"📊 Signal: {result['signal']} ({result['confidence']}%)")
    print(f"📈 Trend: {result['trend']}")
    
    # Get candles for chart
    print("\n📉 Fetching candles for chart...")
    df = await get_candles(symbol, timeframe, 250)
    
    # Print data stats to check for outliers
    print("\n📊 OHLCV Data Statistics (last 50 candles):")
    df_last = df.tail(50)
    print(df_last[['open', 'high', 'low', 'close']].describe())
    
    # Check for extreme wick ratios
    print("\n🔍 Checking for extreme wicks:")
    body_high = df_last[['open', 'close']].max(axis=1)
    body_low = df_last[['open', 'close']].min(axis=1)
    upper_wick = df_last['high'] - body_high
    lower_wick = body_low - df_last['low']
    body_size = body_high - body_low
    
    # Find candles with wicks > 5x body
    extreme_upper = (upper_wick > body_size.clip(lower=1) * 5).sum()
    extreme_lower = (lower_wick > body_size.clip(lower=1) * 5).sum()
    print(f"  Candles with upper wick > 5x body: {extreme_upper}")
    print(f"  Candles with lower wick > 5x body: {extreme_lower}")
    
    # Generate chart
    print("\n🎨 Generating chart...")
    chart_path = generate_analysis_chart(symbol, df, result, candles_to_show=50)
    print(f"✅ Chart saved to: {chart_path}")
    
    # Send to Telegram
    print("\n📤 Sending chart to Telegram...")
    async with TelegramNotifier() as notifier:
        success = await notifier.send_chart(chart_path, result, delete_after=True)
        if success:
            print("✅ Chart sent to Telegram!")
        else:
            print("❌ Failed to send chart")
    
    return result


if __name__ == "__main__":
    asyncio.run(test_chart_generation())
