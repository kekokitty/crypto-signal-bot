"""Telegram command handlers for the crypto bot."""

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes  # type: ignore

import sys
from pathlib import Path

# Handle imports
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from src.config import config
    from src.logger import logger
    from src.trading.portfolio import PortfolioManager
else:
    from ..config import config
    from ..logger import logger
    from ..trading.portfolio import PortfolioManager

if TYPE_CHECKING:
    from ..trading.binance_client import BinanceClient


# Bot start time for uptime tracking
BOT_START_TIME: Optional[datetime] = None

# Portfolio manager instance
_portfolio_manager: Optional[PortfolioManager] = None


def set_bot_start_time(start_time: datetime) -> None:
    """Set the bot start time for uptime tracking."""
    global BOT_START_TIME
    BOT_START_TIME = start_time


def set_portfolio_manager(pm: PortfolioManager) -> None:
    """Set the portfolio manager instance."""
    global _portfolio_manager
    _portfolio_manager = pm


async def get_pm() -> PortfolioManager:
    """Get or create portfolio manager."""
    global _portfolio_manager
    if _portfolio_manager is None:
        logger.warning("Portfolio manager not set, creating new instance")
        _portfolio_manager = PortfolioManager()
    return _portfolio_manager


# ============================================================================
# COMMAND HANDLERS
# ============================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    welcome_message = """
🤖 <b>CryptoBot - Trading Assistant</b>

Welcome! I'm your crypto trading assistant.

<b>Available Commands:</b>
/balance - Show account balance
/positions - Show open positions
/trades - Show recent trades
/pnl - Show profit/loss summary
/stats - Show bot statistics
/analyze &lt;symbol&gt; - Analyze a trading pair
/help - Show this help message

<b>Auto Analysis:</b>
I automatically analyze configured symbols and send alerts when trading signals are detected.

<i>Use /help for more details.</i>
"""
    if update.message:
        await update.message.reply_text(welcome_message, parse_mode="HTML")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    help_message = """
🤖 <b>CryptoBot Commands</b>

<b>📊 Portfolio:</b>
/balance - Show all asset balances
/positions - Show open positions with P&L
/trades - Show recent trade history
/pnl - Show profit/loss summary

<b>📈 Analysis:</b>
/analyze BTCUSDT - Analyze specific pair
/stats - Show bot statistics

<b>⚙️ Settings:</b>
/status - Show bot status

<b>Tips:</b>
• Balances are fetched from Binance
• P&L is tracked from paper trades
• Analysis uses EMA + RSI + S/R strategy
"""
    if update.message:
        await update.message.reply_text(help_message, parse_mode="HTML")


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /balance command - Show account balance."""
    if not update.message:
        return
    
    await update.message.reply_text("💰 Fetching balance...")
    
    try:
        pm = await get_pm()
        balance_info = await pm.get_total_balance_in_usdt()
        
        # Build message
        lines = ["💰 <b>Account Balance</b>\n"]
        
        breakdown = balance_info.get("breakdown", {})
        total = balance_info.get("total_usdt", 0)
        
        if not breakdown:
            lines.append("├─ No assets found")
        else:
            items = list(breakdown.items())
            for i, (asset, info) in enumerate(items):
                is_last = (i == len(items) - 1)
                prefix = "└─" if is_last else "├─"
                
                amount = info["amount"]
                usdt_value = info["usdt_value"]
                
                if asset == "USDT":
                    lines.append(f"{prefix} USDT: <code>${float(amount):,.2f}</code>")
                else:
                    lines.append(
                        f"{prefix} {asset}: <code>{float(amount):.6f}</code> "
                        f"(${float(usdt_value):,.2f})"
                    )
        
        lines.append(f"\n💵 <b>Total:</b> <code>${float(total):,.2f}</code>")
        
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Balance command error: {e}")
        await update.message.reply_text(f"❌ Error fetching balance: {str(e)[:100]}")


async def cmd_positions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /positions command - Show open positions."""
    if not update.message:
        return
    
    await update.message.reply_text("📊 Fetching positions...")
    
    try:
        pm = await get_pm()
        positions = await pm.get_open_positions()
        
        if not positions:
            await update.message.reply_text(
                "📊 <b>Open Positions</b>\n\nNo open positions found.",
                parse_mode="HTML"
            )
            return
        
        lines = ["📊 <b>Open Positions</b>\n"]
        
        for pos in positions:
            symbol = pos["symbol"]
            side = pos["side"]
            size = pos["size"]
            entry = pos.get("entry_price")
            current = pos["current_price"]
            usdt_value = pos.get("usdt_value", current * size)
            pnl = pos.get("pnl")
            pnl_pct = pos.get("pnl_pct")
            has_entry = pos.get("has_entry", False)
            
            lines.append(f"\n<b>{symbol}</b> {side}")
            lines.append(f"├─ Size: <code>{size:.6f}</code>")
            
            if has_entry and entry is not None:
                lines.append(f"├─ Entry: <code>${entry:,.2f}</code>")
            else:
                lines.append(f"├─ Entry: <code>N/A</code> (no trade history)")
            
            lines.append(f"├─ Current: <code>${current:,.2f}</code>")
            lines.append(f"├─ Value: <code>${usdt_value:,.2f}</code>")
            
            if has_entry and pnl is not None and pnl_pct is not None:
                pnl_emoji = "🟢" if pnl >= 0 else "🔴"
                pnl_sign = "+" if pnl >= 0 else ""
                lines.append(
                    f"└─ {pnl_emoji} PnL: <code>{pnl_sign}${pnl:,.2f}</code> "
                    f"({pnl_sign}{pnl_pct:.1f}%)"
                )
            else:
                lines.append(f"└─ ❓ PnL: <code>Unknown</code>")
        
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Positions command error: {e}")
        await update.message.reply_text(f"❌ Error fetching positions: {str(e)[:100]}")


async def cmd_trades(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /trades command - Show recent trades."""
    if not update.message:
        return
    
    try:
        pm = await get_pm()
        
        # Get paper trades (main trading mode)
        trades = await pm.get_paper_trades(limit=10)
        
        if not trades:
            await update.message.reply_text(
                "📜 <b>Recent Trades</b>\n\nNo trades found.",
                parse_mode="HTML"
            )
            return
        
        lines = ["📜 <b>Recent Trades</b> (Last 10)\n"]
        
        for i, trade in enumerate(trades, 1):
            symbol = trade["symbol"]
            side = trade["side"]
            price = trade["price"]
            qty = trade["quantity"]
            timestamp = trade["timestamp"]
            
            # Parse timestamp
            if isinstance(timestamp, str):
                try:
                    dt = datetime.fromisoformat(timestamp)
                    time_str = dt.strftime("%b %d, %H:%M")
                except Exception:
                    time_str = timestamp[:16] if timestamp else "N/A"
            else:
                time_str = "N/A"
            
            side_emoji = "🟢" if side == "BUY" else "🔴"
            
            lines.append(f"\n{i}. {side_emoji} <b>{symbol}</b> {side} @ ${price:,.2f}")
            lines.append(f"   └─ Qty: {qty:.6f} | {time_str}")
        
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Trades command error: {e}")
        await update.message.reply_text(f"❌ Error fetching trades: {str(e)[:100]}")


async def cmd_pnl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /pnl command - Show profit/loss summary."""
    if not update.message:
        return
    
    try:
        pm = await get_pm()
        
        daily = await pm.get_daily_pnl()
        weekly = await pm.get_weekly_pnl()
        monthly = await pm.get_monthly_pnl()
        
        def format_pnl(data: dict, label: str) -> str:
            pnl = data.get("pnl", 0)
            pnl_pct = data.get("pnl_pct", 0)
            sign = "+" if pnl >= 0 else ""
            emoji = "🟢" if pnl >= 0 else "🔴"
            return f"{emoji} {label}: <code>{sign}${pnl:,.2f}</code> ({sign}{pnl_pct:.1f}%)"
        
        trade_count = monthly.get("trade_count", 0)
        wins = monthly.get("wins", 0)
        win_rate = monthly.get("win_rate", 0)
        
        message = f"""
📈 <b>P&amp;L Summary</b>

{format_pnl(daily, "Today")}
{format_pnl(weekly, "This Week")}
{format_pnl(monthly, "This Month")}

📊 <b>Trade Stats (30d)</b>
├─ Total Trades: {trade_count}
├─ Wins: {wins}
└─ Win Rate: {win_rate:.1f}%
"""
        
        await update.message.reply_text(message.strip(), parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"PnL command error: {e}")
        await update.message.reply_text(f"❌ Error calculating P&L: {str(e)[:100]}")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stats command - Show bot statistics."""
    if not update.message:
        return
    
    try:
        pm = await get_pm()
        
        start_time = BOT_START_TIME or datetime.now()
        stats = await pm.get_bot_stats(start_time)
        
        uptime = stats.get("uptime_str", "N/A")
        signals = stats.get("signals_generated", 0)
        trades = stats.get("trades_executed", 0)
        win_rate = stats.get("win_rate", 0)
        avg_value = stats.get("avg_trade_value", 0)
        total_volume = stats.get("total_volume", 0)
        
        message = f"""
🤖 <b>Bot Statistics</b>

⏱️ <b>Uptime:</b> {uptime}

📊 <b>Activity</b>
├─ Signals Generated: {signals}
├─ Trades Executed: {trades}
└─ Win Rate: {win_rate:.1f}%

💰 <b>Volume</b>
├─ Avg Trade: ${avg_value:,.2f}
└─ Total: ${total_volume:,.2f}

🌐 <b>Network:</b> {'Testnet' if config.BINANCE_TESTNET else 'Mainnet'}
"""
        
        await update.message.reply_text(message.strip(), parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Stats command error: {e}")
        await update.message.reply_text(f"❌ Error fetching stats: {str(e)[:100]}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command - Show bot status."""
    if not update.message:
        return
    
    start_time = BOT_START_TIME or datetime.now()
    uptime = datetime.now() - start_time
    
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    days, hours = divmod(hours, 24)
    
    uptime_str = ""
    if days > 0:
        uptime_str += f"{days}d "
    if hours > 0:
        uptime_str += f"{hours}h "
    uptime_str += f"{minutes}m {seconds}s"
    
    status_emoji = "🟢"
    status_text = "Running"
    
    message = f"""
{status_emoji} <b>Bot Status: {status_text}</b>

⏱️ Uptime: {uptime_str}
🌐 Network: {'🧪 Testnet' if config.BINANCE_TESTNET else '🌐 Mainnet'}
📊 Mode: Paper Trading

<i>Last check: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>
"""
    
    await update.message.reply_text(message.strip(), parse_mode="HTML")


async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /analyze command - Analyze a trading pair."""
    if not update.message:
        return
    
    # Get symbol from command args
    if not context.args:
        await update.message.reply_text(
            "❌ Please specify a symbol.\n\nUsage: /analyze BTCUSDT",
            parse_mode="HTML"
        )
        return
    
    symbol = context.args[0].upper()
    
    await update.message.reply_text(f"🔍 Analyzing {symbol}...")
    
    try:
        # Import here to avoid circular imports
        from ..analysis import analyze, get_candles
        from ..visualization import generate_analysis_chart
        
        # Run analysis
        result = await analyze(symbol, "1h")
        
        # Get candles for chart
        df = await get_candles(symbol, "1h", 250)
        
        # Generate chart
        chart_path = generate_analysis_chart(symbol, df, result)
        
        # Build caption
        signal = result.get("signal", "HOLD")
        confidence = result.get("confidence", 0)
        price = result.get("price", 0)
        trend = result.get("trend", "unknown").replace("_", " ").title()
        rsi = result.get("rsi", 0)
        
        signal_emoji = {
            "STRONG_BUY": "🚀🚀",
            "BUY": "🟢",
            "WEAK_BUY": "🟡",
            "HOLD": "⏸️",
            "WEAK_SELL": "🟠",
            "SELL": "🔴",
            "STRONG_SELL": "💥💥"
        }.get(signal, "❓")
        
        caption = f"""
{signal_emoji} <b>{symbol} - {signal}</b> ({confidence}%)

💰 Price: ${price:,.2f}
📊 Trend: {trend}
⚡ RSI: {rsi:.1f}
"""
        
        # Send chart
        with open(chart_path, "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=caption.strip(),
                parse_mode="HTML"
            )
        
        # Clean up
        import os
        try:
            os.remove(chart_path)
        except Exception:
            pass
        
    except Exception as e:
        logger.error(f"Analyze command error: {e}")
        await update.message.reply_text(f"❌ Error analyzing {symbol}: {str(e)[:100]}")


# ============================================================================
# COMMAND REGISTRATION
# ============================================================================

def get_bot_commands() -> list:
    """Get list of bot commands for BotFather."""
    return [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Show help message"),
        BotCommand("balance", "Show account balance"),
        BotCommand("positions", "Show open positions"),
        BotCommand("trades", "Show recent trades"),
        BotCommand("pnl", "Show P&L summary"),
        BotCommand("stats", "Show bot statistics"),
        BotCommand("status", "Show bot status"),
        BotCommand("analyze", "Analyze a trading pair"),
    ]


def register_handlers(application: Application) -> None:
    """Register all command handlers."""
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("balance", cmd_balance))
    application.add_handler(CommandHandler("positions", cmd_positions))
    application.add_handler(CommandHandler("trades", cmd_trades))
    application.add_handler(CommandHandler("pnl", cmd_pnl))
    application.add_handler(CommandHandler("stats", cmd_stats))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("analyze", cmd_analyze))
    
    logger.info("Telegram command handlers registered")


async def setup_bot_commands(application: Application) -> None:
    """Set bot commands in Telegram (visible in menu)."""
    try:
        await application.bot.set_my_commands(get_bot_commands())
        logger.info("Bot commands set successfully")
    except Exception as e:
        logger.warning(f"Failed to set bot commands: {e}")
