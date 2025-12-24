"""Main entry point for the Crypto Trading Bot."""

import sys
import signal
import argparse
import asyncio
from pathlib import Path
from datetime import datetime
from typing import List, Optional

# Handle both direct execution and module execution
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from src.config import config
    from src.database import db
    from src.logger import logger
    from src.trading import BinanceClient, PortfolioManager, get_portfolio_manager
    from src.notifications import TelegramNotifier
    from src.analysis import analyze, get_candles, format_analysis_report
    from src.visualization import generate_analysis_chart
    from src.commands import register_handlers, setup_bot_commands
else:
    from .config import config
    from .database import db
    from .logger import logger
    from .trading import BinanceClient, PortfolioManager, get_portfolio_manager
    from .notifications import TelegramNotifier
    from .analysis import analyze, get_candles, format_analysis_report
    from .visualization import generate_analysis_chart
    from .commands import register_handlers, setup_bot_commands


# ============================================================================
# CONFIGURATION FLAGS
# ============================================================================

# Trading settings
AUTO_TRADE: bool = False  # Set to True to enable auto trading
PAPER_TRADING: bool = True  # Paper trading mode (simulated trades)
SEND_HOLD_SIGNALS: bool = True  # Send notifications for HOLD signals (set False in production)

# Position sizing settings (percentage of balance)
POSITION_SIZE_HIGH: float = 0.05  # 5% for confidence 80-100
POSITION_SIZE_MEDIUM: float = 0.03  # 3% for confidence 60-79
POSITION_SIZE_LOW: float = 0.01  # 1% for confidence 40-59

# Default symbols to monitor
DEFAULT_SYMBOLS: List[str] = ["BTCUSDT", "ETHUSDT"]
DEFAULT_TIMEFRAME: str = "1h"
DEFAULT_INTERVAL: int = 15  # minutes


# ============================================================================
# GLOBAL INSTANCES
# ============================================================================

binance_client: Optional[BinanceClient] = None
telegram_notifier: Optional[TelegramNotifier] = None
portfolio_manager: Optional[PortfolioManager] = None
shutdown_event = asyncio.Event()


# ============================================================================
# DATABASE FUNCTIONS
# ============================================================================

def save_signal_to_db(result: dict) -> None:
    """Save analysis signal to database."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create signals table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    signal TEXT NOT NULL,
                    confidence INTEGER,
                    price REAL,
                    trend TEXT,
                    rsi REAL,
                    ema_trend TEXT,
                    volume_status TEXT,
                    support_level REAL,
                    resistance_level REAL,
                    bull_score INTEGER,
                    bear_score INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Insert signal
            support = result.get("support") or {}
            resistance = result.get("resistance") or {}
            scores = result.get("scores") or {}
            
            cursor.execute("""
                INSERT INTO signals (
                    symbol, timeframe, signal, confidence, price, trend,
                    rsi, ema_trend, volume_status, support_level, resistance_level,
                    bull_score, bear_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result.get("symbol"),
                result.get("timeframe"),
                result.get("signal"),
                result.get("confidence"),
                result.get("price"),
                result.get("trend"),
                result.get("rsi"),
                result.get("ema_trend"),
                result.get("volume_status"),
                support.get("level"),
                resistance.get("level"),
                scores.get("bullish"),
                scores.get("bearish"),
            ))
            
            logger.debug(f"Signal saved to database: {result.get('symbol')} - {result.get('signal')}")
            
    except Exception as e:
        logger.error(f"Failed to save signal to database: {e}")


def log_paper_trade(symbol: str, result: dict, action: str) -> None:
    """Log a paper (simulated) trade to database."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create paper_trades table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS paper_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    price REAL NOT NULL,
                    quantity REAL,
                    signal TEXT,
                    confidence INTEGER,
                    simulated_value REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Calculate simulated position
            price = result.get("price", 0)
            confidence = result.get("confidence", 0)
            position_size = calculate_position_size(confidence, simulated_balance=10000)
            quantity = position_size / price if price > 0 else 0
            
            cursor.execute("""
                INSERT INTO paper_trades (
                    symbol, side, price, quantity, signal, confidence, simulated_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol,
                action,
                price,
                quantity,
                result.get("signal"),
                confidence,
                position_size,
            ))
            
            logger.info(
                f"📝 PAPER TRADE: {action} {symbol} @ ${price:,.2f} | "
                f"Qty: {quantity:.6f} | Value: ${position_size:,.2f}"
            )
            
    except Exception as e:
        logger.error(f"Failed to log paper trade: {e}")


# ============================================================================
# POSITION SIZING
# ============================================================================

def calculate_position_size(confidence: int, simulated_balance: Optional[float] = None) -> float:
    """
    Calculate position size based on confidence level.
    
    Args:
        confidence: Signal confidence (0-100).
        simulated_balance: Optional simulated balance for paper trading.
    
    Returns:
        Position size in quote currency (e.g., USDT).
    """
    # Use simulated balance for paper trading
    if simulated_balance is not None:
        balance = simulated_balance
    else:
        # Would get real balance from Binance
        balance = 10000  # Default fallback
    
    if confidence >= 80:
        return balance * POSITION_SIZE_HIGH
    elif confidence >= 60:
        return balance * POSITION_SIZE_MEDIUM
    else:
        return balance * POSITION_SIZE_LOW


async def get_available_balance() -> float:
    """Get available USDT balance from Binance."""
    global binance_client
    
    if binance_client is None:
        return 0.0
    
    try:
        balance = await binance_client.get_account_balance("USDT")
        return float(balance.get("free", 0))
    except Exception as e:
        logger.error(f"Failed to get balance: {e}")
        return 0.0


# ============================================================================
# TRADE EXECUTION
# ============================================================================

async def execute_trade(symbol: str, result: dict) -> bool:
    """
    Execute a trade based on signal result.
    
    Args:
        symbol: Trading pair symbol.
        result: Analysis result dict.
    
    Returns:
        True if trade executed successfully.
    """
    global binance_client, telegram_notifier
    
    signal = result.get("signal", "HOLD")
    confidence = result.get("confidence", 0)
    price = result.get("price", 0)
    
    # Determine trade side
    if signal in ["STRONG_BUY", "BUY"]:
        side = "BUY"
    elif signal in ["STRONG_SELL", "SELL"]:
        side = "SELL"
    else:
        logger.info(f"No trade action for signal: {signal}")
        return False
    
    # Paper trading mode
    if PAPER_TRADING:
        log_paper_trade(symbol, result, side)
        
        # Send Telegram notification for paper trade
        if telegram_notifier:
            trade_data = {
                "symbol": symbol,
                "side": side,
                "price": f"${price:,.2f}",
                "quantity": f"{calculate_position_size(confidence, 10000) / price:.6f}",
                "total": f"${calculate_position_size(confidence, 10000):,.2f}",
                "order_id": "PAPER_TRADE",
            }
            await telegram_notifier.send_trade_alert(trade_data)
        return True
    
    # Real trading
    try:
        # Ensure binance client is available
        if binance_client is None:
            logger.error("Binance client not initialized")
            return False
        
        # Get real balance
        balance = await get_available_balance()
        position_value = calculate_position_size(confidence, balance)
        quantity = position_value / price if price > 0 else 0
        
        if quantity <= 0:
            logger.warning(f"Invalid quantity calculated: {quantity}")
            return False
        
        # Place market order
        order = await binance_client.place_market_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
        )
        
        logger.info(f"✅ Order executed: {side} {quantity:.6f} {symbol} @ ~${price:,.2f}")
        
        # Send Telegram notification
        if telegram_notifier:
            trade_data = {
                "symbol": symbol,
                "side": side,
                "price": f"${price:,.2f}",
                "quantity": f"{quantity:.6f}",
                "total": f"${position_value:,.2f}",
                "order_id": str(order.get('orderId', 'N/A')),
            }
            await telegram_notifier.send_trade_alert(trade_data)
        
        # Log to database
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trades (symbol, side, price, quantity)
                VALUES (?, ?, ?, ?)
            """, (symbol, side, price, quantity))
        
        return True
        
    except Exception as e:
        logger.error(f"Trade execution failed: {e}")
        if telegram_notifier:
            await telegram_notifier.send_error_alert(f"Trade failed for {symbol}: {e}")
        return False


# ============================================================================
# ANALYSIS FUNCTION
# ============================================================================

async def run_analysis(
    symbols: List[str],
    timeframe: str = "1h",
    send_notifications: bool = True
) -> List[dict]:
    """
    Run technical analysis for given symbols.
    
    Args:
        symbols: List of trading pair symbols.
        timeframe: Candle timeframe (1m, 5m, 15m, 1h, 4h, 1d).
        send_notifications: Whether to send Telegram notifications.
    
    Returns:
        List of analysis results.
    """
    global binance_client, telegram_notifier
    
    results = []
    
    logger.info(f"🔍 Starting analysis for {len(symbols)} symbols...")
    
    for symbol in symbols:
        try:
            logger.info(f"Analyzing {symbol}...")
            
            # Run technical analysis
            result = await analyze(symbol, timeframe)
            results.append(result)
            
            # Save signal to database
            save_signal_to_db(result)
            
            signal = result.get("signal", "HOLD")
            confidence = result.get("confidence", 0)
            
            logger.info(
                f"📊 {symbol}: {signal} (confidence: {confidence}%) | "
                f"Trend: {result.get('trend')} | RSI: {result.get('rsi', 0):.1f}"
            )
            
            # Generate chart and send notification
            if send_notifications:
                should_send = (signal != "HOLD") or SEND_HOLD_SIGNALS
                
                if should_send and telegram_notifier:
                    try:
                        # Get candles for chart
                        df = await get_candles(symbol, timeframe, 250)
                        
                        # Generate chart
                        chart_path = generate_analysis_chart(symbol, df, result)
                        
                        # Send chart to Telegram
                        await telegram_notifier.send_chart(
                            chart_path=chart_path,
                            analysis_result=result,
                            delete_after=True,
                        )
                        
                        logger.info(f"📤 Chart sent to Telegram for {symbol}")
                        
                    except Exception as e:
                        logger.error(f"Failed to send chart for {symbol}: {e}")
            
            # Execute trade if enabled and strong signal
            if AUTO_TRADE and signal in ["STRONG_BUY", "STRONG_SELL"]:
                logger.info(f"🚀 Auto-trading triggered for {symbol}: {signal}")
                await execute_trade(symbol, result)
            
            # Small delay between symbols to avoid rate limits
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")
            if telegram_notifier:
                await telegram_notifier.send_error_alert(
                    f"Analysis failed for {symbol}: {str(e)[:200]}"
                )
            results.append({
                "symbol": symbol,
                "error": str(e),
                "signal": "ERROR",
            })
    
    logger.info(f"✅ Analysis complete for {len(symbols)} symbols")
    return results


# ============================================================================
# INITIALIZATION
# ============================================================================

async def initialize() -> bool:
    """Initialize all components."""
    global binance_client, telegram_notifier, portfolio_manager
    
    logger.info(f"🚀 Starting {config.APP_NAME}...")
    logger.info(f"Mode: {'PAPER TRADING' if PAPER_TRADING else 'LIVE TRADING'}")
    logger.info(f"Auto-trade: {'ENABLED' if AUTO_TRADE else 'DISABLED'}")
    
    # Validate configuration
    if not config.validate():
        logger.error("❌ Configuration validation failed. Check your .env file.")
        return False
    
    # Initialize database
    try:
        db.initialize()
        if not db.health_check():
            logger.error("❌ Database health check failed.")
            return False
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        return False
    
    # Initialize Binance client
    try:
        binance_client = BinanceClient(testnet=config.BINANCE_TESTNET)
        await binance_client.connect()
        logger.info(f"✅ Binance client connected ({'testnet' if config.BINANCE_TESTNET else 'mainnet'})")
    except Exception as e:
        logger.error(f"❌ Binance connection failed: {e}")
        return False
    
    # Initialize Portfolio Manager
    try:
        portfolio_manager = await get_portfolio_manager(binance_client)
        logger.info("✅ Portfolio manager initialized")
    except Exception as e:
        logger.warning(f"⚠️ Portfolio manager initialization failed: {e}")
        portfolio_manager = None
    
    # Initialize Telegram notifier
    try:
        telegram_notifier = TelegramNotifier()
        await telegram_notifier.initialize()
        logger.info("✅ Telegram notifier initialized")
        
        # Send startup message
        await telegram_notifier.send_message(
            f"🤖 <b>{config.APP_NAME} Started</b>\n\n"
            f"Mode: {'📝 Paper Trading' if PAPER_TRADING else '💰 Live Trading'}\n"
            f"Auto-trade: {'✅ Enabled' if AUTO_TRADE else '❌ Disabled'}\n"
            f"Network: {'🧪 Testnet' if config.BINANCE_TESTNET else '🌐 Mainnet'}"
        )
    except Exception as e:
        logger.warning(f"⚠️ Telegram initialization failed (non-critical): {e}")
        telegram_notifier = None
    
    logger.info("✅ Initialization complete")
    return True


async def cleanup() -> None:
    """Cleanup and shutdown all components."""
    global binance_client, telegram_notifier
    
    logger.info(f"🛑 Shutting down {config.APP_NAME}...")
    
    # Send shutdown message
    if telegram_notifier:
        try:
            await telegram_notifier.send_message(
                f"🛑 <b>{config.APP_NAME} Stopped</b>\n\n"
                f"Shutdown time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await telegram_notifier.close()
        except Exception as e:
            logger.warning(f"Failed to send shutdown message: {e}")
    
    # Disconnect Binance client
    if binance_client:
        try:
            await binance_client.disconnect()
        except Exception as e:
            logger.warning(f"Failed to disconnect Binance: {e}")
    
    logger.info("✅ Shutdown complete")


# ============================================================================
# SIGNAL HANDLERS
# ============================================================================

def handle_shutdown(signum, frame):
    """Handle shutdown signals (SIGINT, SIGTERM)."""
    logger.info(f"Received signal {signum}, initiating shutdown...")
    shutdown_event.set()


# ============================================================================
# MAIN LOOP
# ============================================================================

async def run_continuous(
    symbols: List[str],
    timeframe: str,
    interval_minutes: int
) -> None:
    """
    Run analysis continuously at specified interval.
    
    Args:
        symbols: List of trading pair symbols.
        timeframe: Candle timeframe.
        interval_minutes: Minutes between analysis runs.
    """
    logger.info(f"📡 Starting continuous monitoring (interval: {interval_minutes} min)")
    logger.info(f"📊 Monitoring symbols: {', '.join(symbols)}")
    
    run_count = 0
    
    while not shutdown_event.is_set():
        run_count += 1
        logger.info(f"\n{'='*50}")
        logger.info(f"📈 Analysis Run #{run_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*50}\n")
        
        try:
            await run_analysis(symbols, timeframe)
        except Exception as e:
            logger.error(f"Analysis run failed: {e}")
            if telegram_notifier:
                await telegram_notifier.send_error_alert(f"Analysis run #{run_count} failed: {e}")
        
        # Wait for next interval or shutdown
        logger.info(f"⏰ Next analysis in {interval_minutes} minutes...")
        
        try:
            await asyncio.wait_for(
                shutdown_event.wait(),
                timeout=interval_minutes * 60
            )
            break  # Shutdown requested
        except asyncio.TimeoutError:
            pass  # Continue to next run


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

async def run_with_commands(
    symbols: List[str],
    timeframe: str,
    interval_minutes: int
) -> None:
    """
    Run bot with Telegram command handlers in polling mode.
    Also runs periodic analysis in the background.
    
    Args:
        symbols: List of trading pair symbols.
        timeframe: Candle timeframe.
        interval_minutes: Minutes between analysis runs.
    """
    from telegram.ext import Application  # type: ignore
    
    if not telegram_notifier or not telegram_notifier.bot:
        logger.error("Telegram not initialized, cannot run in commands mode")
        return
    
    logger.info("🤖 Starting Telegram bot with command handlers...")
    
    # Create Application for command handling
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    
    # Set up portfolio manager for command handlers
    from src.commands.telegram_commands import set_portfolio_manager, set_bot_start_time
    assert portfolio_manager is not None
    set_portfolio_manager(portfolio_manager)
    set_bot_start_time(datetime.now())
    
    # Register command handlers
    register_handlers(app)
    
    # Set up bot commands menu
    await setup_bot_commands(app)
    
    logger.info("✅ Command handlers registered")
    logger.info("📡 Bot is now listening for commands...")
    
    # Run the bot with polling
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)  # type: ignore
        
        # Send startup message
        await telegram_notifier.send_message(
            "🤖 <b>Bot Commands Enabled</b>\n\n"
            "<b>Available commands:</b>\n"
            "/balance - Show account balance\n"
            "/positions - Show open positions\n"
            "/trades - Recent trade history\n"
            "/pnl - P&L summary\n"
            "/stats - Bot statistics\n"
            "/status - Bot status\n"
            "/analyze &lt;symbol&gt; - Analyze a pair\n"
            "/help - Show all commands"
        )
        
        run_count = 0
        
        # Run periodic analysis while bot is active
        while not shutdown_event.is_set():
            run_count += 1
            logger.info(f"\n{'='*50}")
            logger.info(f"📈 Analysis Run #{run_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"{'='*50}\n")
            
            try:
                await run_analysis(symbols, timeframe)
            except Exception as e:
                logger.error(f"Analysis run failed: {e}")
                if telegram_notifier:
                    await telegram_notifier.send_error_alert(f"Analysis run #{run_count} failed: {e}")
            
            # Wait for next interval or shutdown
            logger.info(f"⏰ Next analysis in {interval_minutes} minutes...")
            
            try:
                await asyncio.wait_for(
                    shutdown_event.wait(),
                    timeout=interval_minutes * 60
                )
                break  # Shutdown requested
            except asyncio.TimeoutError:
                pass  # Continue to next run
        
        # Stop polling
        await app.updater.stop()  # type: ignore
        await app.stop()


async def main() -> int:
    """Main entry point with CLI argument parsing."""
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Crypto Trading Bot - Technical Analysis & Trading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run once (for cron jobs)
  python -m src.main --once --symbols BTCUSDT ETHUSDT

  # Continuous monitoring every 15 minutes
  python -m src.main --interval 15 --symbols BTCUSDT ETHUSDT SOLUSDT

  # Enable Telegram commands with monitoring
  python -m src.main --commands --symbols BTCUSDT ETHUSDT

  # Custom timeframe
  python -m src.main --once --timeframe 4h --symbols BTCUSDT
        """
    )
    
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run analysis once and exit (useful for cron jobs)"
    )
    
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        metavar="MINUTES",
        help=f"Minutes between analysis runs (default: {DEFAULT_INTERVAL})"
    )
    
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=DEFAULT_SYMBOLS,
        metavar="SYMBOL",
        help=f"Trading pairs to analyze (default: {' '.join(DEFAULT_SYMBOLS)})"
    )
    
    parser.add_argument(
        "--timeframe",
        type=str,
        default=DEFAULT_TIMEFRAME,
        choices=["1m", "5m", "15m", "30m", "1h", "4h", "1d"],
        help=f"Candle timeframe (default: {DEFAULT_TIMEFRAME})"
    )
    
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="Disable Telegram notifications"
    )
    
    parser.add_argument(
        "--auto-trade",
        action="store_true",
        help="Enable auto-trading (use with caution!)"
    )
    
    parser.add_argument(
        "--live",
        action="store_true",
        help="Disable paper trading (REAL MONEY - use with extreme caution!)"
    )
    
    parser.add_argument(
        "--commands",
        action="store_true",
        help="Enable Telegram command handlers (polling mode)"
    )
    
    args = parser.parse_args()
    
    # Override global settings from CLI
    global AUTO_TRADE, PAPER_TRADING
    
    if args.auto_trade:
        AUTO_TRADE = True
        logger.warning("⚠️ AUTO-TRADING ENABLED via CLI")
    
    if args.live:
        PAPER_TRADING = False
        logger.warning("⚠️⚠️⚠️ LIVE TRADING MODE - REAL MONEY AT RISK! ⚠️⚠️⚠️")
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    # Initialize components
    if not await initialize():
        return 1
    
    try:
        if args.once:
            # Run once and exit
            logger.info("Running single analysis...")
            await run_analysis(
                symbols=args.symbols,
                timeframe=args.timeframe,
                send_notifications=not args.no_notify
            )
        elif args.commands:
            # Run with Telegram command handlers
            await run_with_commands(
                symbols=args.symbols,
                timeframe=args.timeframe,
                interval_minutes=args.interval
            )
        else:
            # Run continuous loop
            await run_continuous(
                symbols=args.symbols,
                timeframe=args.timeframe,
                interval_minutes=args.interval
            )
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1
    finally:
        await cleanup()
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
