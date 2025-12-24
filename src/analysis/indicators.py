"""Technical indicators using pandas-ta."""

import pandas as pd
import pandas_ta as ta  # type: ignore
from typing import Optional


def calculate_ema(df: pd.DataFrame, period: int = 50, column: str = "close") -> pd.Series:
    """
    Calculate Exponential Moving Average.
    
    Args:
        df: DataFrame with OHLCV data.
        period: EMA period (default: 50).
        column: Column to calculate EMA on (default: 'close').
    
    Returns:
        Series with EMA values.
    """
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found in DataFrame")
    
    ema = ta.ema(df[column], length=period)
    return ema


def calculate_rsi(df: pd.DataFrame, period: int = 14, column: str = "close") -> pd.Series:
    """
    Calculate Relative Strength Index.
    
    Args:
        df: DataFrame with OHLCV data.
        period: RSI period (default: 14).
        column: Column to calculate RSI on (default: 'close').
    
    Returns:
        Series with RSI values (0-100).
    """
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found in DataFrame")
    
    rsi = ta.rsi(df[column], length=period)
    return rsi


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate Average True Range (volatility indicator).
    
    Args:
        df: DataFrame with OHLCV data (needs high, low, close).
        period: ATR period (default: 14).
    
    Returns:
        Series with ATR values.
    """
    required = ["high", "low", "close"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Column '{col}' not found in DataFrame")
    
    atr = ta.atr(df["high"], df["low"], df["close"], length=period)
    return atr


def calculate_volume_sma(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    Calculate Volume Simple Moving Average.
    
    Args:
        df: DataFrame with OHLCV data.
        period: SMA period (default: 20).
    
    Returns:
        Series with Volume SMA values.
    """
    if "volume" not in df.columns:
        raise ValueError("Column 'volume' not found in DataFrame")
    
    volume_sma = ta.sma(df["volume"], length=period)
    return volume_sma


def calculate_macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    column: str = "close"
) -> dict:
    """
    Calculate MACD (Moving Average Convergence Divergence).
    
    Args:
        df: DataFrame with OHLCV data.
        fast: Fast EMA period (default: 12).
        slow: Slow EMA period (default: 26).
        signal: Signal line period (default: 9).
        column: Column to calculate MACD on (default: 'close').
    
    Returns:
        Dict with MACD line, signal line, histogram values and status.
    """
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found in DataFrame")
    
    macd_df = ta.macd(df[column], fast=fast, slow=slow, signal=signal)
    
    # Get column names (pandas-ta naming convention)
    macd_col = f"MACD_{fast}_{slow}_{signal}"
    signal_col = f"MACDs_{fast}_{slow}_{signal}"
    hist_col = f"MACDh_{fast}_{slow}_{signal}"
    
    macd_line = macd_df[macd_col].iloc[-1] if macd_col in macd_df.columns else 0
    signal_line = macd_df[signal_col].iloc[-1] if signal_col in macd_df.columns else 0
    histogram = macd_df[hist_col].iloc[-1] if hist_col in macd_df.columns else 0
    
    # Previous histogram for trend
    prev_histogram = macd_df[hist_col].iloc[-2] if hist_col in macd_df.columns and len(macd_df) > 1 else 0
    
    # Determine status
    if macd_line > signal_line and histogram > prev_histogram:
        status = "bullish"
    elif macd_line < signal_line and histogram < prev_histogram:
        status = "bearish"
    else:
        status = "neutral"
    
    return {
        "line": round(macd_line, 8),
        "signal": round(signal_line, 8),
        "histogram": round(histogram, 8),
        "prev_histogram": round(prev_histogram, 8),
        "status": status,
        "crossover": "bullish" if macd_line > signal_line and macd_df[macd_col].iloc[-2] <= macd_df[signal_col].iloc[-2] else (
            "bearish" if macd_line < signal_line and macd_df[macd_col].iloc[-2] >= macd_df[signal_col].iloc[-2] else None
        )
    }


def calculate_ema_trend(df: pd.DataFrame) -> dict:
    """
    Calculate EMA 20, 50, 200 for trend strength analysis.
    
    Trend definitions:
    - Strong uptrend: Price > EMA20 > EMA50 > EMA200
    - Weak uptrend: Price > EMA50, but EMA20 < EMA50
    - Strong downtrend: Price < EMA20 < EMA50 < EMA200
    - Weak downtrend: Price < EMA50, but EMA20 > EMA50
    - Ranging: EMAs tangled, no clear order
    
    Args:
        df: DataFrame with OHLCV data.
    
    Returns:
        Dict with EMA values and trend classification.
    """
    ema20 = ta.ema(df["close"], length=20)
    ema50 = ta.ema(df["close"], length=50)
    ema200 = ta.ema(df["close"], length=200)
    
    current_price = df["close"].iloc[-1]
    ema20_val = ema20.iloc[-1]
    ema50_val = ema50.iloc[-1]
    ema200_val = ema200.iloc[-1] if not pd.isna(ema200.iloc[-1]) else ema50_val
    
    # Determine trend
    if current_price > ema20_val > ema50_val > ema200_val:
        trend = "strong_up"
        trend_score = 100
    elif current_price > ema50_val and ema20_val < ema50_val:
        trend = "weak_up"
        trend_score = 60
    elif current_price > ema50_val:
        trend = "weak_up"
        trend_score = 70
    elif current_price < ema20_val < ema50_val < ema200_val:
        trend = "strong_down"
        trend_score = 0
    elif current_price < ema50_val and ema20_val > ema50_val:
        trend = "weak_down"
        trend_score = 40
    elif current_price < ema50_val:
        trend = "weak_down"
        trend_score = 30
    else:
        trend = "ranging"
        trend_score = 50
    
    return {
        "ema20": round(ema20_val, 8),
        "ema50": round(ema50_val, 8),
        "ema200": round(ema200_val, 8),
        "trend": trend,
        "trend_score": trend_score,
        "price_vs_ema20": round((current_price - ema20_val) / ema20_val * 100, 2),
        "price_vs_ema50": round((current_price - ema50_val) / ema50_val * 100, 2),
        "price_vs_ema200": round((current_price - ema200_val) / ema200_val * 100, 2)
    }


def calculate_volume_status(df: pd.DataFrame, period: int = 20) -> dict:
    """
    Analyze current volume relative to average.
    
    Volume status:
    - High: > 1.5x SMA(20)
    - Normal: 0.8x - 1.5x SMA(20)
    - Low: < 0.8x SMA(20)
    
    Args:
        df: DataFrame with OHLCV data.
        period: SMA period for volume average.
    
    Returns:
        Dict with volume analysis.
    """
    volume_sma = calculate_volume_sma(df, period)
    current_volume = df["volume"].iloc[-1]
    avg_volume = volume_sma.iloc[-1]
    
    if pd.isna(avg_volume) or avg_volume == 0:
        return {
            "current": current_volume,
            "average": 0,
            "ratio": 1.0,
            "status": "normal"
        }
    
    ratio = current_volume / avg_volume
    
    if ratio > 1.5:
        status = "high"
    elif ratio < 0.8:
        status = "low"
    else:
        status = "normal"
    
    return {
        "current": round(current_volume, 2),
        "average": round(avg_volume, 2),
        "ratio": round(ratio, 2),
        "status": status
    }


def calculate_bollinger_bands(
    df: pd.DataFrame,
    period: int = 20,
    std_dev: float = 2.0,
    column: str = "close"
) -> pd.DataFrame:
    """
    Calculate Bollinger Bands.
    
    Args:
        df: DataFrame with OHLCV data.
        period: Moving average period (default: 20).
        std_dev: Standard deviation multiplier (default: 2.0).
        column: Column to calculate on (default: 'close').
    
    Returns:
        DataFrame with Lower, Mid, Upper bands and Bandwidth.
    """
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found in DataFrame")
    
    bbands = ta.bbands(df[column], length=period, std=std_dev)
    return bbands
