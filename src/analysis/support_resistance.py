"""Support and Resistance level detection with S/R flip strategy."""

import pandas as pd
from typing import Optional
from collections import defaultdict


def find_pivot_points(
    df: pd.DataFrame,
    left: int = 5,
    right: int = 5
) -> list[dict]:
    """
    Find swing highs and swing lows (pivot points).
    
    A swing high is a candle where the high is greater than
    the highs of 'left' candles before and 'right' candles after.
    
    A swing low is a candle where the low is lower than
    the lows of 'left' candles before and 'right' candles after.
    
    Args:
        df: DataFrame with OHLCV data.
        left: Number of candles to check on the left.
        right: Number of candles to check on the right.
    
    Returns:
        List of pivot points: [{"index": idx, "price": price, "type": "high"|"low"}]
    """
    pivots = []
    
    if len(df) < left + right + 1:
        return pivots
    
    highs = df["high"].values
    lows = df["low"].values
    
    for i in range(left, len(df) - right):
        # Check for swing high
        is_swing_high = True
        current_high = highs[i]
        
        for j in range(1, left + 1):
            if highs[i - j] >= current_high:
                is_swing_high = False
                break
        
        if is_swing_high:
            for j in range(1, right + 1):
                if highs[i + j] >= current_high:
                    is_swing_high = False
                    break
        
        if is_swing_high:
            pivots.append({
                "index": i,
                "price": current_high,
                "type": "high",
                "timestamp": df.index[i] if isinstance(df.index, pd.DatetimeIndex) else i
            })
        
        # Check for swing low
        is_swing_low = True
        current_low = lows[i]
        
        for j in range(1, left + 1):
            if lows[i - j] <= current_low:
                is_swing_low = False
                break
        
        if is_swing_low:
            for j in range(1, right + 1):
                if lows[i + j] <= current_low:
                    is_swing_low = False
                    break
        
        if is_swing_low:
            pivots.append({
                "index": i,
                "price": current_low,
                "type": "low",
                "timestamp": df.index[i] if isinstance(df.index, pd.DatetimeIndex) else i
            })
    
    return pivots


def find_sr_levels(
    df: pd.DataFrame,
    lookback: int = 100,
    cluster_threshold: float = 0.005,  # 0.5%
    min_touches: int = 2
) -> list[dict]:
    """
    Find Support and Resistance levels by clustering pivot points.
    
    Args:
        df: DataFrame with OHLCV data.
        lookback: Number of candles to analyze.
        cluster_threshold: Price difference threshold for clustering (0.5% = 0.005).
        min_touches: Minimum touches to consider a valid S/R level.
    
    Returns:
        List of S/R levels sorted by strength:
        [{"level": price, "strength": touch_count, "type": "support"|"resistance", "pivots": [...]}]
    """
    # Get recent candles
    df_lookback = df.tail(lookback).copy()
    
    # Find pivot points
    pivots = find_pivot_points(df_lookback, left=5, right=5)
    
    if not pivots:
        return []
    
    # Cluster nearby levels
    clusters = []
    used = set()
    
    for i, pivot in enumerate(pivots):
        if i in used:
            continue
        
        cluster = [pivot]
        used.add(i)
        
        for j, other_pivot in enumerate(pivots):
            if j in used:
                continue
            
            # Check if within threshold
            price_diff = abs(pivot["price"] - other_pivot["price"]) / pivot["price"]
            if price_diff <= cluster_threshold:
                cluster.append(other_pivot)
                used.add(j)
        
        clusters.append(cluster)
    
    # Calculate S/R levels from clusters
    sr_levels = []
    current_price = df["close"].iloc[-1]
    
    for cluster in clusters:
        if len(cluster) < min_touches:
            continue
        
        # Average price of cluster
        avg_price = sum(p["price"] for p in cluster) / len(cluster)
        
        # Count highs and lows
        high_count = sum(1 for p in cluster if p["type"] == "high")
        low_count = sum(1 for p in cluster if p["type"] == "low")
        
        # Determine if support or resistance based on current price
        if avg_price < current_price:
            sr_type = "support"
        else:
            sr_type = "resistance"
        
        sr_levels.append({
            "level": round(avg_price, 8),
            "strength": len(cluster),
            "type": sr_type,
            "high_touches": high_count,
            "low_touches": low_count,
            "pivots": cluster
        })
    
    # Sort by strength (touch count)
    sr_levels.sort(key=lambda x: x["strength"], reverse=True)
    
    return sr_levels


def detect_sr_flip(
    df: pd.DataFrame,
    sr_levels: list[dict],
    flip_threshold: float = 0.015,  # 1.5% proximity
    confirmation_candles: int = 3
) -> dict:
    """
    Detect Support/Resistance flip.
    
    Bullish flip: Previous resistance becomes new support
    - Price was below level, broke above, came back to test, and bounced
    
    Bearish flip: Previous support becomes new resistance
    - Price was above level, broke below, came back to test, and rejected
    
    Args:
        df: DataFrame with OHLCV data.
        sr_levels: List of S/R levels from find_sr_levels().
        flip_threshold: Price proximity threshold for flip detection (1.5%).
        confirmation_candles: Number of candles to confirm the flip.
    
    Returns:
        {
            "flip_detected": bool,
            "flip_type": "bullish"|"bearish"|None,
            "level": price,
            "confidence": 0-100
        }
    """
    result = {
        "flip_detected": False,
        "flip_type": None,
        "level": None,
        "confidence": 0
    }
    
    if len(df) < confirmation_candles + 10 or not sr_levels:
        return result
    
    current_price = df["close"].iloc[-1]
    recent_low = df["low"].iloc[-confirmation_candles:].min()
    recent_high = df["high"].iloc[-confirmation_candles:].max()
    
    # Check previous candles for breakout
    lookback_start = -confirmation_candles - 10
    lookback_end = -confirmation_candles
    previous_prices = df["close"].iloc[lookback_start:lookback_end]
    
    for sr in sr_levels:
        level = sr["level"]
        price_distance = abs(current_price - level) / level
        
        # Skip if too far from level
        if price_distance > flip_threshold:
            continue
        
        # Check for bullish flip (resistance → support)
        if sr["high_touches"] >= 2:  # Was resistance (had high touches)
            # Price was below, now above
            was_below = (previous_prices < level).any()
            now_above = current_price > level
            
            # Price came back to test and bounced
            tested_level = recent_low <= level * (1 + flip_threshold)
            bounced = current_price > recent_low
            
            if was_below and now_above and tested_level and bounced:
                confidence = min(100, sr["strength"] * 20 + 40)
                if confidence > result["confidence"]:
                    result = {
                        "flip_detected": True,
                        "flip_type": "bullish",
                        "level": level,
                        "confidence": confidence
                    }
        
        # Check for bearish flip (support → resistance)
        if sr["low_touches"] >= 2:  # Was support (had low touches)
            # Price was above, now below
            was_above = (previous_prices > level).any()
            now_below = current_price < level
            
            # Price came back to test and rejected
            tested_level = recent_high >= level * (1 - flip_threshold)
            rejected = current_price < recent_high
            
            if was_above and now_below and tested_level and rejected:
                confidence = min(100, sr["strength"] * 20 + 40)
                if confidence > result["confidence"]:
                    result = {
                        "flip_detected": True,
                        "flip_type": "bearish",
                        "level": level,
                        "confidence": confidence
                    }
    
    return result


def get_nearest_sr(
    current_price: float,
    sr_levels: list[dict]
) -> tuple[Optional[dict], Optional[dict]]:
    """
    Get nearest support and resistance levels.
    
    Args:
        current_price: Current price.
        sr_levels: List of S/R levels.
    
    Returns:
        Tuple of (nearest_support, nearest_resistance).
    """
    supports = [sr for sr in sr_levels if sr["level"] < current_price]
    resistances = [sr for sr in sr_levels if sr["level"] > current_price]
    
    nearest_support = None
    nearest_resistance = None
    
    if supports:
        nearest_support = max(supports, key=lambda x: x["level"])
    
    if resistances:
        nearest_resistance = min(resistances, key=lambda x: x["level"])
    
    return nearest_support, nearest_resistance
