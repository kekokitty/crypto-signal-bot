"""Portfolio tracking and position management."""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any

import sys
from pathlib import Path

# Handle imports
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from src.config import config
    from src.logger import logger
    from src.database import db
    from src.trading.binance_client import BinanceClient
else:
    from ..config import config
    from ..logger import logger
    from ..database import db
    from .binance_client import BinanceClient


class PortfolioManager:
    """Portfolio and position tracking."""

    def __init__(self, binance_client: Optional[BinanceClient] = None):
        """
        Initialize portfolio manager.
        
        Args:
            binance_client: Optional BinanceClient instance. Creates new one if not provided.
        """
        self._client = binance_client
        self._own_client = binance_client is None

    async def _get_client(self) -> BinanceClient:
        """Get or create Binance client."""
        if self._client is None:
            self._client = BinanceClient(testnet=config.BINANCE_TESTNET)
            await self._client.connect()
        return self._client

    async def close(self) -> None:
        """Close client if we own it."""
        if self._own_client and self._client is not None:
            await self._client.disconnect()
            self._client = None

    # =========================================================================
    # ACCOUNT BALANCE
    # =========================================================================

    async def get_account_balance(self) -> Dict[str, Dict[str, Decimal]]:
        """
        Get all non-zero balances from Binance.
        
        Returns:
            Dict with asset balances: {"BTC": {"free": 0.05, "locked": 0, "total": 0.05}, ...}
        """
        client = await self._get_client()
        return await client.get_account_balance()

    async def get_usdt_balance(self) -> Decimal:
        """
        Get available USDT balance.
        
        Returns:
            Free USDT balance as Decimal.
        """
        client = await self._get_client()
        balance = await client.get_account_balance("USDT")
        return balance.get("free", Decimal("0"))

    async def get_total_balance_in_usdt(self) -> Dict[str, Any]:
        """
        Convert all assets to USDT value.
        
        Returns:
            Dict with total value and breakdown by asset.
        """
        client = await self._get_client()
        balances = await client.get_account_balance()
        
        total_usdt = Decimal("0")
        breakdown = {}
        
        # Valid trading pairs on testnet
        valid_assets = {"BTC", "ETH", "BNB", "XRP", "LTC", "ADA", "SOL", "USDT", "USDC", "BUSD"}
        
        for asset, balance in balances.items():
            if balance["total"] <= Decimal("0.00000001"):
                continue
            
            # Skip unknown assets on testnet
            if config.BINANCE_TESTNET and asset not in valid_assets:
                continue
                
            if asset == "USDT":
                usdt_value = balance["total"]
            else:
                try:
                    # Get price in USDT
                    price = await client.get_price(f"{asset}USDT")
                    usdt_value = balance["total"] * price
                except Exception:
                    # Try reverse pair or skip
                    try:
                        price = await client.get_price(f"USDT{asset}")
                        usdt_value = balance["total"] / price if price > 0 else Decimal("0")
                    except Exception:
                        usdt_value = Decimal("0")
            
            if usdt_value > Decimal("0.01"):  # Skip dust
                breakdown[asset] = {
                    "amount": balance["total"],
                    "free": balance["free"],
                    "locked": balance["locked"],
                    "usdt_value": usdt_value,
                }
                total_usdt += usdt_value
        
        return {
            "total_usdt": total_usdt,
            "breakdown": breakdown,
            "timestamp": datetime.now(),
        }

    # =========================================================================
    # OPEN POSITIONS (Spot - non-USDT holdings)
    # =========================================================================

    async def get_open_positions(self) -> List[Dict[str, Any]]:
        """
        Get all open positions (non-USDT holdings with value).
        For spot trading, "positions" are non-stablecoin holdings.
        
        Returns:
            List of position dicts.
        """
        client = await self._get_client()
        balances = await client.get_account_balance()
        
        positions = []
        stablecoins = {"USDT", "USDC", "BUSD", "TUSD", "DAI"}
        
        # Valid trading pairs on testnet
        valid_symbols = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "LTCUSDT", "ADAUSDT", "SOLUSDT"}
        
        for asset, balance in balances.items():
            if asset in stablecoins:
                continue
            if balance["total"] <= Decimal("0.00000001"):
                continue
            
            try:
                symbol = f"{asset}USDT"
                
                # Skip if not a valid symbol on this network
                if config.BINANCE_TESTNET and symbol not in valid_symbols:
                    logger.debug(f"Skipping {symbol} - not valid on testnet")
                    continue
                
                current_price = await client.get_price(symbol)
                usdt_value = balance["total"] * current_price
                
                if usdt_value < Decimal("1"):  # Skip if less than $1
                    continue
                
                # Get average entry price from trade history (if available)
                entry_price = await self._get_average_entry_price(symbol)
                
                # Calculate PnL only if we have a real entry price
                if entry_price and entry_price > 0:
                    pnl = (current_price - entry_price) * balance["total"]
                    pnl_pct = ((current_price / entry_price) - 1) * 100
                    has_entry = True
                else:
                    # No trade history - mark as unknown
                    pnl = None
                    pnl_pct = None
                    entry_price = None
                    has_entry = False
                
                positions.append({
                    "symbol": symbol,
                    "asset": asset,
                    "side": "LONG",  # Spot is always long
                    "size": float(balance["total"]),
                    "entry_price": float(entry_price) if entry_price else None,
                    "current_price": float(current_price),
                    "usdt_value": float(usdt_value),
                    "pnl": float(pnl) if pnl is not None else None,
                    "pnl_pct": float(pnl_pct) if pnl_pct is not None else None,
                    "has_entry": has_entry,
                })
                
            except Exception as e:
                logger.debug(f"Could not get position for {asset}: {e}")
                continue
        
        return positions

    async def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get position for a specific symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT').
        
        Returns:
            Position dict or None if no position.
        """
        positions = await self.get_open_positions()
        for pos in positions:
            if pos["symbol"] == symbol.upper():
                return pos
        return None

    async def _get_average_entry_price(self, symbol: str) -> Optional[Decimal]:
        """
        Get average entry price from Binance trade history or local database.
        
        First tries Binance API for actual trade history,
        then falls back to local database.
        """
        client = await self._get_client()
        
        # Try to get from Binance trade history first
        try:
            trades = await client.get_my_trades(symbol, limit=50)
            if trades:
                # Calculate weighted average price of BUY trades
                total_qty = Decimal("0")
                total_cost = Decimal("0")
                
                for trade in trades:
                    if trade["is_buyer"]:  # Only BUY trades
                        qty = trade["qty"]
                        price = trade["price"]
                        total_qty += qty
                        total_cost += qty * price
                
                if total_qty > 0:
                    avg_price = total_cost / total_qty
                    logger.debug(f"Entry price for {symbol} from Binance: {avg_price}")
                    return avg_price
        except Exception as e:
            logger.debug(f"Could not get trades from Binance for {symbol}: {e}")
        
        # Fallback to local database
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT AVG(price) as avg_price
                    FROM trades
                    WHERE symbol = ? AND side = 'BUY'
                    ORDER BY timestamp DESC
                    LIMIT 10
                """, (symbol,))
                row = cursor.fetchone()
                if row and row["avg_price"]:
                    return Decimal(str(row["avg_price"]))
        except Exception:
            pass
        
        return None

    # =========================================================================
    # TRADE HISTORY
    # =========================================================================

    async def get_recent_trades(
        self,
        symbol: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get recent trade history from database.
        
        Args:
            symbol: Filter by symbol (optional).
            limit: Maximum number of trades to return.
        
        Returns:
            List of trade dicts.
        """
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                
                if symbol:
                    cursor.execute("""
                        SELECT * FROM trades
                        WHERE symbol = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """, (symbol.upper(), limit))
                else:
                    cursor.execute("""
                        SELECT * FROM trades
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """, (limit,))
                
                rows = cursor.fetchall()
                
                trades = []
                for row in rows:
                    trades.append({
                        "id": row["id"],
                        "symbol": row["symbol"],
                        "side": row["side"],
                        "price": row["price"],
                        "quantity": row["quantity"],
                        "timestamp": row["timestamp"],
                    })
                
                return trades
                
        except Exception as e:
            logger.error(f"Failed to get trade history: {e}")
            return []

    async def get_paper_trades(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent paper trades from database.
        
        Args:
            limit: Maximum number of trades to return.
        
        Returns:
            List of paper trade dicts.
        """
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM paper_trades
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,))
                
                rows = cursor.fetchall()
                
                trades = []
                for row in rows:
                    trades.append({
                        "id": row["id"],
                        "symbol": row["symbol"],
                        "side": row["side"],
                        "price": row["price"],
                        "quantity": row["quantity"],
                        "signal": row["signal"],
                        "confidence": row["confidence"],
                        "simulated_value": row["simulated_value"],
                        "timestamp": row["timestamp"],
                    })
                
                return trades
                
        except Exception as e:
            logger.error(f"Failed to get paper trades: {e}")
            return []

    # =========================================================================
    # P&L TRACKING
    # =========================================================================

    async def get_daily_pnl(self) -> Dict[str, Any]:
        """
        Calculate today's profit/loss from paper trades.
        
        Returns:
            Dict with PnL info.
        """
        return await self._get_pnl_for_period(days=1)

    async def get_weekly_pnl(self) -> Dict[str, Any]:
        """
        Calculate this week's profit/loss.
        
        Returns:
            Dict with PnL info.
        """
        return await self._get_pnl_for_period(days=7)

    async def get_monthly_pnl(self) -> Dict[str, Any]:
        """
        Calculate this month's profit/loss.
        
        Returns:
            Dict with PnL info.
        """
        return await self._get_pnl_for_period(days=30)

    async def _get_pnl_for_period(self, days: int) -> Dict[str, Any]:
        """Calculate PnL for a given period."""
        try:
            start_date = datetime.now() - timedelta(days=days)
            
            with db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get trades from period
                cursor.execute("""
                    SELECT side, price, quantity, simulated_value
                    FROM paper_trades
                    WHERE timestamp >= ?
                """, (start_date.isoformat(),))
                
                rows = cursor.fetchall()
                
                total_buy = Decimal("0")
                total_sell = Decimal("0")
                trade_count = len(rows)
                wins = 0
                losses = 0
                
                for row in rows:
                    value = Decimal(str(row["simulated_value"] or 0))
                    if row["side"] == "BUY":
                        total_buy += value
                    else:
                        total_sell += value
                        # Simplified win/loss tracking
                        wins += 1  # Assumes all sells are winning
                
                # For paper trading, estimate PnL based on simulated values
                pnl = total_sell - total_buy
                pnl_pct = (pnl / total_buy * 100) if total_buy > 0 else Decimal("0")
                
                win_rate = (wins / trade_count * 100) if trade_count > 0 else 0
                
                return {
                    "pnl": float(pnl),
                    "pnl_pct": float(pnl_pct),
                    "trade_count": trade_count,
                    "wins": wins,
                    "losses": losses,
                    "win_rate": win_rate,
                    "period_days": days,
                    "start_date": start_date,
                }
                
        except Exception as e:
            logger.error(f"Failed to calculate PnL: {e}")
            return {
                "pnl": 0,
                "pnl_pct": 0,
                "trade_count": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0,
                "period_days": days,
                "error": str(e),
            }

    # =========================================================================
    # BOT STATISTICS
    # =========================================================================

    async def get_bot_stats(self, start_time: datetime) -> Dict[str, Any]:
        """
        Get bot statistics.
        
        Args:
            start_time: When the bot started running.
        
        Returns:
            Dict with bot statistics.
        """
        try:
            uptime = datetime.now() - start_time
            
            with db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Count signals
                cursor.execute("SELECT COUNT(*) as count FROM signals")
                signal_count = cursor.fetchone()["count"]
                
                # Count paper trades
                cursor.execute("SELECT COUNT(*) as count FROM paper_trades")
                trade_count = cursor.fetchone()["count"]
                
                # Get trade stats
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total,
                        AVG(simulated_value) as avg_value,
                        SUM(CASE WHEN side = 'BUY' THEN simulated_value ELSE 0 END) as total_buy,
                        SUM(CASE WHEN side = 'SELL' THEN simulated_value ELSE 0 END) as total_sell
                    FROM paper_trades
                """)
                stats = cursor.fetchone()
                
                # Calculate simplified metrics
                total_buy = float(stats["total_buy"] or 0)
                total_sell = float(stats["total_sell"] or 0)
                avg_trade = float(stats["avg_value"] or 0)
                
                # Estimate win rate (simplified for paper trading)
                cursor.execute("""
                    SELECT COUNT(*) as wins FROM paper_trades
                    WHERE side = 'SELL' AND confidence >= 60
                """)
                wins = cursor.fetchone()["wins"]
                
                win_rate = (wins / trade_count * 100) if trade_count > 0 else 0
                
                return {
                    "uptime": uptime,
                    "uptime_str": self._format_timedelta(uptime),
                    "signals_generated": signal_count,
                    "trades_executed": trade_count,
                    "win_rate": win_rate,
                    "avg_trade_value": avg_trade,
                    "total_volume": total_buy + total_sell,
                }
                
        except Exception as e:
            logger.error(f"Failed to get bot stats: {e}")
            return {
                "uptime": datetime.now() - start_time,
                "uptime_str": "N/A",
                "signals_generated": 0,
                "trades_executed": 0,
                "win_rate": 0,
                "error": str(e),
            }

    @staticmethod
    def _format_timedelta(td: timedelta) -> str:
        """Format timedelta as human-readable string."""
        total_seconds = int(td.total_seconds())
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        
        return " ".join(parts) if parts else "0m"


# Global portfolio manager instance
portfolio_manager: Optional[PortfolioManager] = None


async def get_portfolio_manager(client: Optional[BinanceClient] = None) -> PortfolioManager:
    """Get or create portfolio manager."""
    global portfolio_manager
    if portfolio_manager is None:
        portfolio_manager = PortfolioManager(client)
    return portfolio_manager


# Test function
async def test_portfolio():
    """Test portfolio functions."""
    pm = PortfolioManager()
    
    try:
        print("Testing portfolio manager...")
        
        # Get balance
        balance = await pm.get_total_balance_in_usdt()
        print(f"\nTotal Balance: ${balance['total_usdt']:,.2f}")
        for asset, info in balance["breakdown"].items():
            print(f"  {asset}: {info['amount']} (${info['usdt_value']:,.2f})")
        
        # Get positions
        positions = await pm.get_open_positions()
        print(f"\nOpen Positions: {len(positions)}")
        for pos in positions:
            print(f"  {pos['symbol']}: {pos['side']} {pos['size']} @ ${pos['entry_price']:,.2f}")
        
        # Get paper trades
        trades = await pm.get_paper_trades()
        print(f"\nPaper Trades: {len(trades)}")
        for trade in trades[:3]:
            print(f"  {trade['symbol']} {trade['side']} @ ${trade['price']:,.2f}")
        
    finally:
        await pm.close()


if __name__ == "__main__":
    asyncio.run(test_portfolio())
