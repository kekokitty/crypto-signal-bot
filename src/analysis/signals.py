"""Enhanced signal generation with EMA stack, MACD, Volume, and ATR analysis."""

import asyncio
import pandas as pd
from typing import Optional
from datetime import datetime

import sys
from pathlib import Path

# Handle both direct execution and module execution
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from src.trading import BinanceClient
    from src.config import config
    from src.logger import logger
else:
    from ..trading import BinanceClient
    from ..config import config
    from ..logger import logger

from .indicators import (
    calculate_ema, 
    calculate_rsi, 
    calculate_atr, 
    calculate_macd,
    calculate_ema_trend,
    calculate_volume_status
)
from .support_resistance import find_sr_levels, detect_sr_flip, get_nearest_sr


async def get_candles(
    symbol: str,
    timeframe: str = "1h",
    limit: int = 250
) -> pd.DataFrame:
    """
    Fetch OHLCV candles from Binance.
    
    Args:
        symbol: Trading pair (e.g., 'BTCUSDT').
        timeframe: Candle timeframe (e.g., '1m', '5m', '15m', '1h', '4h', '1d').
        limit: Number of candles to fetch (max 1000).
    
    Returns:
        DataFrame with columns: open, high, low, close, volume, timestamp.
    """
    async with BinanceClient(testnet=config.BINANCE_TESTNET) as client:
        # Access the underlying binance client after connection
        assert client.client is not None, "Client not connected"
        klines = await client.client.get_klines(
            symbol=symbol.upper(),
            interval=timeframe,
            limit=limit
        )
    
    df = pd.DataFrame(klines, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore"
    ])
    
    # Convert types
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    
    # Keep only OHLCV columns
    df = df[["open", "high", "low", "close", "volume"]]
    
    return df


def calculate_sr_distance_atr(
    current_price: float,
    level: Optional[float],
    atr: float
) -> Optional[dict]:
    """
    Calculate distance to S/R level in ATR units.
    
    Args:
        current_price: Current price.
        level: S/R level price.
        atr: Current ATR value.
    
    Returns:
        Dict with level, distance in ATR, and proximity status.
    """
    if level is None or atr == 0:
        return None
    
    distance = abs(current_price - level)
    distance_atr = distance / atr
    
    if distance_atr <= 0.5:
        proximity = "very_close"
    elif distance_atr <= 1.0:
        proximity = "close"
    else:
        proximity = "far"
    
    return {
        "level": round(level, 8),
        "distance": round(distance, 8),
        "distance_atr": round(distance_atr, 2),
        "proximity": proximity
    }


async def analyze(
    symbol: str,
    timeframe: str = "1h",
    candle_limit: int = 250
) -> dict:
    """
    Enhanced analysis with EMA stack, MACD, Volume, and ATR.
    
    Signal Types:
    - STRONG_BUY (80-100): Strong uptrend + S/R flip or near support + MACD bullish + High volume + RSI 40-60
    - BUY (60-79): Uptrend + Near support + MACD or RSI favorable + Normal/high volume
    - WEAK_BUY (40-59): Price > EMA50 + One bullish factor
    - HOLD (0-39): Conflicting signals or ranging
    - WEAK_SELL (40-59): Price < EMA50 + One bearish factor
    - SELL (60-79): Downtrend + Near resistance + MACD or RSI unfavorable
    - STRONG_SELL (80-100): Strong downtrend + S/R flip or near resistance + MACD bearish + High volume
    
    Args:
        symbol: Trading pair (e.g., 'BTCUSDT').
        timeframe: Candle timeframe.
        candle_limit: Number of candles to analyze.
    
    Returns:
        Comprehensive signal analysis with all indicators.
    """
    logger.info(f"Analyzing {symbol} on {timeframe} timeframe...")
    
    # Fetch candles
    df = await get_candles(symbol, timeframe, candle_limit)
    
    if len(df) < 200:
        return {
            "signal": "HOLD",
            "confidence": 0,
            "error": "Insufficient data (need 200+ candles)",
            "timestamp": datetime.now().isoformat()
        }
    
    # Current price
    current_price = df["close"].iloc[-1]
    
    # Calculate all indicators
    rsi = calculate_rsi(df, period=14).iloc[-1]
    atr = calculate_atr(df, period=14).iloc[-1]
    ema_data = calculate_ema_trend(df)
    macd_data = calculate_macd(df)
    volume_data = calculate_volume_status(df, period=20)
    
    # Find S/R levels
    sr_levels = find_sr_levels(df, lookback=100)
    sr_flip = detect_sr_flip(df, sr_levels)
    
    # Get nearest support/resistance
    nearest_support, nearest_resistance = get_nearest_sr(current_price, sr_levels)
    
    # Calculate S/R distances in ATR
    support_info = calculate_sr_distance_atr(
        current_price,
        nearest_support["level"] if nearest_support else None,
        atr
    )
    resistance_info = calculate_sr_distance_atr(
        current_price,
        nearest_resistance["level"] if nearest_resistance else None,
        atr
    )
    
    # Initialize scoring
    bullish_score = 0
    bearish_score = 0
    reasons = []
    warnings = []
    
    # 1. TREND ANALYSIS (max 30 points)
    trend = ema_data["trend"]
    if trend == "strong_up":
        bullish_score += 30
        reasons.append("Strong uptrend (EMA stack aligned)")
    elif trend == "weak_up":
        bullish_score += 15
        reasons.append("Weak uptrend")
    elif trend == "strong_down":
        bearish_score += 30
        reasons.append("Strong downtrend (EMA stack aligned)")
    elif trend == "weak_down":
        bearish_score += 15
        reasons.append("Weak downtrend")
    else:
        reasons.append("Ranging/Sideways market")
    
    # 2. S/R FLIP DETECTION (max 25 points)
    if sr_flip["flip_detected"]:
        if sr_flip["flip_type"] == "bullish":
            bullish_score += 25
            reasons.append(f"Bullish S/R flip at ${sr_flip['level']:,.2f}")
        else:
            bearish_score += 25
            reasons.append(f"Bearish S/R flip at ${sr_flip['level']:,.2f}")
    
    # 3. S/R PROXIMITY (max 20 points)
    if support_info and support_info["proximity"] in ["very_close", "close"]:
        points = 20 if support_info["proximity"] == "very_close" else 12
        bullish_score += points
        reasons.append(f"Near support at ${support_info['level']:,.2f} ({support_info['distance_atr']:.1f} ATR)")
    
    if resistance_info and resistance_info["proximity"] in ["very_close", "close"]:
        points = 20 if resistance_info["proximity"] == "very_close" else 12
        bearish_score += points
        reasons.append(f"Near resistance at ${resistance_info['level']:,.2f} ({resistance_info['distance_atr']:.1f} ATR)")
    
    # 4. MACD ANALYSIS (max 15 points)
    if macd_data["status"] == "bullish":
        bullish_score += 10
        reasons.append("MACD bullish")
        if macd_data["crossover"] == "bullish":
            bullish_score += 5
            reasons.append("MACD bullish crossover!")
    elif macd_data["status"] == "bearish":
        bearish_score += 10
        reasons.append("MACD bearish")
        if macd_data["crossover"] == "bearish":
            bearish_score += 5
            reasons.append("MACD bearish crossover!")
    
    # 5. VOLUME CONFIRMATION (max 10 points)
    if volume_data["status"] == "high":
        # High volume amplifies existing signals
        if bullish_score > bearish_score:
            bullish_score += 10
        elif bearish_score > bullish_score:
            bearish_score += 10
        reasons.append(f"High volume ({volume_data['ratio']:.1f}x avg)")
    elif volume_data["status"] == "low":
        warnings.append(f"Low volume ({volume_data['ratio']:.1f}x avg) - weak conviction")
    
    # 6. RSI ANALYSIS (max 10 points + warnings)
    if 40 <= rsi <= 60:
        reasons.append(f"RSI neutral ({rsi:.1f}) - room to move")
    elif rsi < 30:
        bullish_score += 10
        reasons.append(f"RSI oversold ({rsi:.1f})")
    elif rsi < 40:
        bullish_score += 5
        reasons.append(f"RSI approaching oversold ({rsi:.1f})")
    elif rsi > 70:
        bearish_score += 10
        reasons.append(f"RSI overbought ({rsi:.1f})")
        warnings.append("RSI overbought - potential reversal")
    elif rsi > 60:
        bearish_score += 5
        reasons.append(f"RSI approaching overbought ({rsi:.1f})")
        if bullish_score > bearish_score:
            warnings.append("RSI getting high - watch for pullback")
    
    # DETERMINE SIGNAL
    net_score = bullish_score - bearish_score
    total_score = max(bullish_score, bearish_score)
    
    # Normalize confidence to 0-100
    confidence = min(100, total_score)
    
    # Determine signal based on net score and confidence
    if net_score >= 40 and confidence >= 80:
        signal = "STRONG_BUY"
    elif net_score >= 20 and confidence >= 60:
        signal = "BUY"
    elif net_score > 0 and confidence >= 40:
        signal = "WEAK_BUY"
    elif net_score <= -40 and confidence >= 80:
        signal = "STRONG_SELL"
    elif net_score <= -20 and confidence >= 60:
        signal = "SELL"
    elif net_score < 0 and confidence >= 40:
        signal = "WEAK_SELL"
    else:
        signal = "HOLD"
        confidence = min(39, confidence)
    
    # Add final confidence adjustment based on conflicting signals
    if bullish_score > 20 and bearish_score > 20:
        warnings.append("Mixed signals - reduced confidence")
        confidence = int(confidence * 0.8)
    
    # Build result
    result = {
        "symbol": symbol,
        "timeframe": timeframe,
        "signal": signal,
        "confidence": confidence,
        "trend": trend,
        "volume_status": volume_data["status"],
        "price": current_price,
        "ema20": ema_data["ema20"],
        "ema50": ema_data["ema50"],
        "ema200": ema_data["ema200"],
        "rsi": round(rsi, 2),
        "macd": macd_data,
        "atr": round(atr, 8),
        "support": support_info,
        "resistance": resistance_info,
        "sr_flip": sr_flip,
        "volume": volume_data,
        "scores": {
            "bullish": bullish_score,
            "bearish": bearish_score,
            "net": net_score
        },
        "reasons": reasons,
        "warnings": warnings,
        "timestamp": datetime.now().isoformat()
    }
    
    logger.info(f"Analysis complete: {signal} (confidence: {confidence}%)")
    
    return result


async def analyze_multiple(
    symbols: list[str],
    timeframe: str = "1h"
) -> list[dict]:
    """
    Analyze multiple symbols.
    
    Args:
        symbols: List of trading pairs.
        timeframe: Candle timeframe.
    
    Returns:
        List of analysis results sorted by signal strength.
    """
    results = []
    
    for symbol in symbols:
        try:
            result = await analyze(symbol, timeframe)
            results.append(result)
        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")
            results.append({
                "symbol": symbol,
                "signal": "ERROR",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
        
        # Small delay to avoid rate limits
        await asyncio.sleep(0.5)
    
    # Sort by signal strength
    signal_order = {
        "STRONG_BUY": 0, "BUY": 1, "WEAK_BUY": 2,
        "HOLD": 3,
        "WEAK_SELL": 4, "SELL": 5, "STRONG_SELL": 6,
        "ERROR": 7
    }
    results.sort(key=lambda x: (signal_order.get(x.get("signal", "ERROR"), 7), -x.get("confidence", 0)))
    
    return results


def format_analysis_report(result: dict) -> str:
    """
    Format analysis result as readable text report.
    
    Args:
        result: Analysis result dict.
    
    Returns:
        Formatted string report.
    """
    if "error" in result:
        return f"❌ {result['symbol']}: {result['error']}"
    
    signal_emoji = {
        "STRONG_BUY": "🚀",
        "BUY": "🟢",
        "WEAK_BUY": "🟡",
        "HOLD": "⏸️",
        "WEAK_SELL": "🟠",
        "SELL": "🔴",
        "STRONG_SELL": "💥"
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
    
    report = f"""
{'='*50}
{emoji} {result['symbol']} - {result['signal']} ({result['confidence']}%)
{'='*50}

💰 Price: ${result['price']:,.2f}
{trend_e} Trend: {result['trend'].replace('_', ' ').title()}
📊 Volume: {result['volume_status'].title()} ({result['volume']['ratio']:.1f}x avg)

📉 EMA20: ${result['ema20']:,.2f}
📉 EMA50: ${result['ema50']:,.2f}
📉 EMA200: ${result['ema200']:,.2f}

⚡ RSI: {result['rsi']:.1f}
📊 MACD: {result['macd']['status'].title()} (H: {result['macd']['histogram']:.4f})
📏 ATR: ${result['atr']:,.2f}
"""

    if result['support']:
        report += f"\n🟢 Support: ${result['support']['level']:,.2f} ({result['support']['distance_atr']:.1f} ATR - {result['support']['proximity']})"
    
    if result['resistance']:
        report += f"\n🔴 Resistance: ${result['resistance']['level']:,.2f} ({result['resistance']['distance_atr']:.1f} ATR - {result['resistance']['proximity']})"
    
    if result['sr_flip']['flip_detected']:
        flip_emoji = "🔄🟢" if result['sr_flip']['flip_type'] == "bullish" else "🔄🔴"
        report += f"\n{flip_emoji} S/R Flip: {result['sr_flip']['flip_type'].title()} at ${result['sr_flip']['level']:,.2f}"
    
    report += f"\n\n📋 Reasons:"
    for reason in result['reasons']:
        report += f"\n  ✓ {reason}"
    
    if result['warnings']:
        report += f"\n\n⚠️ Warnings:"
        for warning in result['warnings']:
            report += f"\n  ⚠ {warning}"
    
    report += f"\n\n🔢 Scores: Bull {result['scores']['bullish']} | Bear {result['scores']['bearish']} | Net {result['scores']['net']:+d}"
    report += f"\n{'='*50}"
    
    return report


# Example usage
async def main():
    """Test the enhanced analysis module."""
    result = await analyze("BTCUSDT", "1h")
    print(format_analysis_report(result))


if __name__ == "__main__":
    asyncio.run(main())
