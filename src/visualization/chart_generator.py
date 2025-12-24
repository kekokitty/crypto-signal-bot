"""Chart generator for technical analysis visualization."""

import tempfile
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd
import mplfinance as mpf  # type: ignore
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import numpy as np

import sys

# Handle imports
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from src.logger import logger
else:
    from ..logger import logger


def clean_outliers(df: pd.DataFrame, std_threshold: float = 2.0) -> pd.DataFrame:
    """
    Remove candles where high/low deviate too much from mean.
    Also cleans individual wick anomalies within candles.
    
    Args:
        df: DataFrame with OHLCV data.
        std_threshold: Number of standard deviations for outlier threshold.
    
    Returns:
        Cleaned DataFrame.
    """
    df_clean = df.copy()
    
    # Use IQR method for more robust outlier detection
    Q1 = df_clean["close"].quantile(0.25)
    Q3 = df_clean["close"].quantile(0.75)
    IQR = Q3 - Q1
    lower_bound = Q1 - 2 * IQR
    upper_bound = Q3 + 2 * IQR
    
    # Replace extreme highs and lows with capped values
    # Instead of removing entire candles, just fix the bad wicks
    df_clean["high"] = df_clean["high"].clip(upper=upper_bound * 1.05)  # 5% margin
    df_clean["low"] = df_clean["low"].clip(lower=lower_bound * 0.95)   # 5% margin
    
    # Ensure OHLC consistency: high >= max(open, close), low <= min(open, close)
    body_high = df_clean[["open", "close"]].max(axis=1)
    body_low = df_clean[["open", "close"]].min(axis=1)
    
    # High must be at least body_high
    df_clean["high"] = df_clean[["high"]].join(body_high.rename("body_high")).max(axis=1)
    # Low must be at most body_low  
    df_clean["low"] = df_clean[["low"]].join(body_low.rename("body_low")).min(axis=1)
    
    # Cap wicks to reasonable proportions (max 2x the average body range or 1% of price)
    avg_body = (body_high - body_low).mean()
    max_wick_size = max(avg_body * 2, body_high.mean() * 0.01)  # 2x avg body or 1% of price
    
    # Apply wick caps
    df_clean["high"] = np.minimum(df_clean["high"], body_high + max_wick_size)
    df_clean["low"] = np.maximum(df_clean["low"], body_low - max_wick_size)
    
    return df_clean


# Dark theme colors
COLORS = {
    "background": "#1a1a2e",
    "panel_bg": "#16213e",
    "grid": "#2d2d44",
    "text": "#e0e0e0",
    "text_muted": "#888888",
    "candle_up": "#00d26a",
    "candle_down": "#ff4757",
    "ema20": "#3498db",
    "ema50": "#f39c12",
    "ema200": "#9b59b6",
    "support": "#00d26a",
    "resistance": "#ff4757",
    "sr_flip": "#f1c40f",
    "volume_up": "#00d26a80",
    "volume_down": "#ff475780",
    "volume_high": "#f1c40f",
    "rsi_line": "#3498db",
    "rsi_overbought": "#ff4757",
    "rsi_oversold": "#00d26a",
}

# Signal colors and markers
SIGNAL_STYLES = {
    "STRONG_BUY": {"color": "#00ff88", "marker": "^", "size": 200},
    "BUY": {"color": "#00d26a", "marker": "^", "size": 150},
    "WEAK_BUY": {"color": "#7bed9f", "marker": "^", "size": 100},
    "HOLD": {"color": "#888888", "marker": "o", "size": 80},
    "WEAK_SELL": {"color": "#ff7675", "marker": "v", "size": 100},
    "SELL": {"color": "#ff4757", "marker": "v", "size": 150},
    "STRONG_SELL": {"color": "#ff0040", "marker": "v", "size": 200},
}


def generate_analysis_chart(
    symbol: str,
    df: pd.DataFrame,
    analysis_result: dict,
    candles_to_show: int = 50,
    save_path: Optional[str] = None
) -> str:
    """
    Generate a candlestick chart with technical analysis overlays.
    
    Args:
        symbol: Trading pair symbol.
        df: DataFrame with OHLCV data and indicators.
        analysis_result: Analysis result dict from signals.analyze().
        candles_to_show: Number of candles to display.
        save_path: Optional path to save chart. If None, uses temp file.
    
    Returns:
        Path to the saved PNG file.
    """
    logger.info(f"Generating chart for {symbol}...")
    
    # Get last N candles
    df_chart = df.tail(candles_to_show).copy()
    
    # Ensure index is DatetimeIndex
    if not isinstance(df_chart.index, pd.DatetimeIndex):
        df_chart.index = pd.to_datetime(df_chart.index)
    
    # Log data stats before cleaning (for debugging)
    logger.debug(f"Data before cleaning - High range: {df_chart['high'].min():.2f} - {df_chart['high'].max():.2f}")
    logger.debug(f"Data before cleaning - Low range: {df_chart['low'].min():.2f} - {df_chart['low'].max():.2f}")
    
    # Clean outliers using the comprehensive cleaning function
    df_chart = clean_outliers(df_chart, std_threshold=3.0)
    
    # Log data stats after cleaning
    logger.debug(f"Data after cleaning - High range: {df_chart['high'].min():.2f} - {df_chart['high'].max():.2f}")
    logger.debug(f"Data after cleaning - Low range: {df_chart['low'].min():.2f} - {df_chart['low'].max():.2f}")
    
    # Calculate price range for Y-axis limits
    price_min = df_chart["low"].min()
    price_max = df_chart["high"].max()
    price_range = price_max - price_min
    padding = price_range * 0.1  # 10% padding
    ylim_min = price_min - padding
    ylim_max = price_max + padding
    
    # Calculate indicators if not present
    import pandas_ta as ta  # type: ignore
    
    if "ema20" not in df_chart.columns:
        df_full = df.copy()
        df_full["ema20"] = ta.ema(df_full["close"], length=20)
        df_full["ema50"] = ta.ema(df_full["close"], length=50)
        df_full["ema200"] = ta.ema(df_full["close"], length=200)
        df_full["rsi"] = ta.rsi(df_full["close"], length=14)
        df_full["volume_sma"] = ta.sma(df_full["volume"], length=20)
        df_chart = df_full.tail(candles_to_show).copy()
    
    # Create custom market colors with explicit wick colors
    mc = mpf.make_marketcolors(
        up=COLORS["candle_up"],
        down=COLORS["candle_down"],
        edge="inherit",
        wick={"up": COLORS["candle_up"], "down": COLORS["candle_down"]},  # Color wicks same as candles
        volume={"up": COLORS["volume_up"], "down": COLORS["volume_down"]},
    )
    
    # Create custom style
    style = mpf.make_mpf_style(
        base_mpf_style="nightclouds",
        marketcolors=mc,
        facecolor=COLORS["background"],
        edgecolor=COLORS["grid"],
        gridcolor=COLORS["grid"],
        gridstyle="--",
        gridaxis="both",
        y_on_right=True,
        rc={
            "axes.labelcolor": COLORS["text"],
            "axes.edgecolor": COLORS["grid"],
            "xtick.color": COLORS["text"],
            "ytick.color": COLORS["text"],
            "text.color": COLORS["text"],
            "figure.facecolor": COLORS["background"],
            "axes.facecolor": COLORS["panel_bg"],
        }
    )
    
    # Prepare additional plots
    add_plots = []
    
    # EMA lines
    if "ema20" in df_chart.columns and not df_chart["ema20"].isna().all():
        add_plots.append(mpf.make_addplot(
            df_chart["ema20"], color=COLORS["ema20"], width=1.2, label="EMA20"
        ))
    
    if "ema50" in df_chart.columns and not df_chart["ema50"].isna().all():
        add_plots.append(mpf.make_addplot(
            df_chart["ema50"], color=COLORS["ema50"], width=1.5, label="EMA50"
        ))
    
    if "ema200" in df_chart.columns and not df_chart["ema200"].isna().all():
        add_plots.append(mpf.make_addplot(
            df_chart["ema200"], color=COLORS["ema200"], width=1.8, label="EMA200"
        ))
    
    # RSI panel
    if "rsi" in df_chart.columns and not df_chart["rsi"].isna().all():
        add_plots.append(mpf.make_addplot(
            df_chart["rsi"], panel=2, color=COLORS["rsi_line"], width=1.2,
            ylabel="RSI", y_on_right=True
        ))
        # RSI overbought/oversold lines
        add_plots.append(mpf.make_addplot(
            [70] * len(df_chart), panel=2, color=COLORS["rsi_overbought"],
            linestyle="--", width=0.8
        ))
        add_plots.append(mpf.make_addplot(
            [30] * len(df_chart), panel=2, color=COLORS["rsi_oversold"],
            linestyle="--", width=0.8
        ))
        add_plots.append(mpf.make_addplot(
            [50] * len(df_chart), panel=2, color=COLORS["text_muted"],
            linestyle=":", width=0.5
        ))
    
    # Volume SMA
    if "volume_sma" in df_chart.columns and not df_chart["volume_sma"].isna().all():
        add_plots.append(mpf.make_addplot(
            df_chart["volume_sma"], panel=1, color=COLORS["ema50"],
            width=1, linestyle="-"
        ))
    
    # Create figure with adjusted candle width for better wick proportions
    fig, axes = mpf.plot(
        df_chart,
        type="candle",
        style=style,
        addplot=add_plots if add_plots else None,
        volume=True,
        volume_panel=1,
        panel_ratios=(6, 2, 2) if "rsi" in df_chart.columns else (7, 3),
        figsize=(12, 8),
        tight_layout=False,
        returnfig=True,
        datetime_format="%m-%d %H:%M",
        xrotation=0,
        ylim=(ylim_min, ylim_max),  # Set Y-axis limits for price chart
        scale_width_adjustment=dict(candle=0.8, volume=0.7),  # Make candles wider
    )
    
    # Get main axis
    ax_main = axes[0]
    ax_volume = axes[2] if len(axes) > 2 else axes[1]
    ax_rsi = axes[4] if len(axes) > 4 else None
    
    # Ensure Y-axis limits are set correctly (backup)
    ax_main.set_ylim(ylim_min, ylim_max)
    
    # Add support/resistance lines
    support_level = analysis_result.get("support", {})
    resistance_level = analysis_result.get("resistance", {})
    
    if support_level and support_level.get("level"):
        ax_main.axhline(
            y=support_level["level"],
            color=COLORS["support"],
            linestyle="--",
            linewidth=1.5,
            alpha=0.8
        )
        ax_main.text(
            0.02, support_level["level"],
            f' S: ${support_level["level"]:,.0f}',
            transform=ax_main.get_yaxis_transform(),
            color=COLORS["support"],
            fontsize=8,
            va="center",
            fontweight="bold"
        )
    
    if resistance_level and resistance_level.get("level"):
        ax_main.axhline(
            y=resistance_level["level"],
            color=COLORS["resistance"],
            linestyle="--",
            linewidth=1.5,
            alpha=0.8
        )
        ax_main.text(
            0.02, resistance_level["level"],
            f' R: ${resistance_level["level"]:,.0f}',
            transform=ax_main.get_yaxis_transform(),
            color=COLORS["resistance"],
            fontsize=8,
            va="center",
            fontweight="bold"
        )
    
    # Add S/R flip highlight
    sr_flip = analysis_result.get("sr_flip", {})
    if sr_flip.get("flip_detected") and sr_flip.get("level"):
        flip_color = COLORS["sr_flip"]
        ax_main.axhline(
            y=sr_flip["level"],
            color=flip_color,
            linestyle="-",
            linewidth=2,
            alpha=0.9
        )
        flip_text = f' FLIP: ${sr_flip["level"]:,.0f}'
        ax_main.text(
            0.02, sr_flip["level"],
            flip_text,
            transform=ax_main.get_yaxis_transform(),
            color=flip_color,
            fontsize=9,
            va="center",
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", facecolor=COLORS["background"], alpha=0.8)
        )
    
    # Add signal marker on current price
    signal = analysis_result.get("signal", "HOLD")
    signal_style = SIGNAL_STYLES.get(signal, SIGNAL_STYLES["HOLD"])
    current_price = analysis_result.get("price", df_chart["close"].iloc[-1])
    
    # Plot signal marker at the last candle
    last_idx = len(df_chart) - 1
    ax_main.scatter(
        [last_idx], [current_price],
        marker=signal_style["marker"],
        s=signal_style["size"],
        c=signal_style["color"],
        zorder=10,
        edgecolors="white",
        linewidths=1
    )
    
    # Add info box
    info_text = create_info_box(analysis_result)
    fig.text(
        0.98, 0.98,
        info_text,
        transform=fig.transFigure,
        fontsize=9,
        verticalalignment="top",
        horizontalalignment="right",
        fontfamily="monospace",
        color=COLORS["text"],
        bbox=dict(
            boxstyle="round,pad=0.5",
            facecolor=COLORS["panel_bg"],
            edgecolor=COLORS["grid"],
            alpha=0.95
        )
    )
    
    # Add title
    timeframe = analysis_result.get("timeframe", "1h")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = f"{symbol} | {timeframe.upper()} | {timestamp}"
    fig.suptitle(
        title,
        fontsize=14,
        fontweight="bold",
        color=COLORS["text"],
        y=0.995
    )
    
    # Add legend for EMAs
    legend_elements = [
        Line2D([0], [0], color=COLORS["ema20"], linewidth=1.2, label="EMA 20"),
        Line2D([0], [0], color=COLORS["ema50"], linewidth=1.5, label="EMA 50"),
        Line2D([0], [0], color=COLORS["ema200"], linewidth=1.8, label="EMA 200"),
        Line2D([0], [0], color=COLORS["support"], linewidth=1.5, linestyle="--", label="Support"),
        Line2D([0], [0], color=COLORS["resistance"], linewidth=1.5, linestyle="--", label="Resistance"),
    ]
    ax_main.legend(
        handles=legend_elements,
        loc="upper left",
        fontsize=7,
        facecolor=COLORS["panel_bg"],
        edgecolor=COLORS["grid"],
        labelcolor=COLORS["text"]
    )
    
    # Adjust layout
    plt.subplots_adjust(top=0.95, bottom=0.05, left=0.05, right=0.92, hspace=0.1)
    
    # Save chart
    if save_path is None:
        temp_dir = tempfile.gettempdir()
        save_path = os.path.join(temp_dir, f"chart_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    
    fig.savefig(
        save_path,
        dpi=150,
        facecolor=COLORS["background"],
        edgecolor="none",
        bbox_inches="tight",
        pad_inches=0.2
    )
    plt.close(fig)
    
    logger.info(f"Chart saved to {save_path}")
    return save_path


def create_info_box(analysis_result: dict) -> str:
    """Create formatted info box text."""
    signal = analysis_result.get("signal", "HOLD")
    confidence = analysis_result.get("confidence", 0)
    trend = analysis_result.get("trend", "unknown").replace("_", " ").title()
    price = analysis_result.get("price", 0)
    rsi = analysis_result.get("rsi", 0)
    volume_status = analysis_result.get("volume_status", "normal").title()
    
    # Signal indicator (text only, no emoji for font compatibility)
    signal_indicator = {
        "STRONG_BUY": "[++]",
        "BUY": "[+]",
        "WEAK_BUY": "[~+]",
        "HOLD": "[=]",
        "WEAK_SELL": "[~-]",
        "SELL": "[-]",
        "STRONG_SELL": "[--]"
    }.get(signal, "[?]")
    
    info = f"""
{signal_indicator} {signal}
--------------
Confidence: {confidence}%
Trend: {trend}
Price: ${price:,.2f}
RSI: {rsi:.1f}
Volume: {volume_status}
"""
    
    # Add scores
    scores = analysis_result.get("scores", {})
    if scores:
        info += f"""--------------
Bull: {scores.get('bullish', 0)}
Bear: {scores.get('bearish', 0)}
Net: {scores.get('net', 0):+d}
"""
    
    return info.strip()


# Test function
async def test_chart():
    """Test chart generation."""
    from src.analysis import analyze, get_candles
    
    # Get analysis
    result = await analyze("BTCUSDT", "1h")
    
    # Get candles
    df = await get_candles("BTCUSDT", "1h", 250)
    
    # Generate chart
    chart_path = generate_analysis_chart("BTCUSDT", df, result)
    print(f"Chart saved to: {chart_path}")
    
    return chart_path


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_chart())
