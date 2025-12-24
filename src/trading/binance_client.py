"""Binance API client with async support."""

import asyncio
from decimal import Decimal
from typing import Optional
from functools import wraps

from binance import AsyncClient, BinanceSocketManager  # type: ignore
from binance.exceptions import BinanceAPIException, BinanceRequestException  # type: ignore

import sys
from pathlib import Path

# Handle both direct execution and module execution
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from src.config import config
    from src.logger import logger
else:
    from ..config import config
    from ..logger import logger


def retry_on_error(max_retries: int = 3, delay: float = 1.0):
    """Decorator for retrying failed API calls."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception: Exception | None = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)  
                except Exception as e:
                    # Only catch Binance exceptions if they exist
                    if BinanceAPIException is not None and isinstance(e, (BinanceAPIException, BinanceRequestException)):
                        last_exception = e
                        if attempt < max_retries - 1:
                            wait_time = delay * (2 ** attempt)  # Exponential backoff
                            logger.warning(
                                f"API call failed (attempt {attempt + 1}/{max_retries}): {e}. "
                                f"Retrying in {wait_time}s..."
                            )
                            await asyncio.sleep(wait_time)
                        else:
                            logger.error(f"API call failed after {max_retries} attempts: {e}")
                    else:
                        raise
            if last_exception is not None:
                raise last_exception
            raise RuntimeError("Unexpected error in retry decorator")
        return wrapper
    return decorator


class BinanceClient:
    """Async Binance API client."""

    def __init__(self, testnet: bool = False):
        """
        Initialize Binance client.
        
        Args:
            testnet: If True, use Binance testnet instead of mainnet.
        """
        self.testnet = testnet
        self.client: Optional[AsyncClient] = None
        self._api_key = config.BINANCE_API_KEY
        self._api_secret = config.BINANCE_SECRET

    async def connect(self) -> None:
        """Establish connection to Binance API."""
        if self.client is not None:
            return

        logger.info(f"Connecting to Binance {'testnet' if self.testnet else 'mainnet'}...")

        try:
            self.client = await AsyncClient.create(
                api_key=self._api_key,
                api_secret=self._api_secret,
                testnet=self.testnet
            )
            logger.info("Successfully connected to Binance API.")
        except Exception as e:
            logger.error(f"Failed to connect to Binance: {e}")
            raise

    async def disconnect(self) -> None:
        """Close the Binance API connection."""
        if self.client:
            await self.client.close_connection()
            self.client = None
            logger.info("Disconnected from Binance API.")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()

    def _ensure_connected(self) -> None:
        """Ensure client is connected."""
        if self.client is None:
            raise RuntimeError("Client not connected. Call connect() first or use async context manager.")

    @retry_on_error(max_retries=3, delay=1.0)
    async def get_account_balance(self, asset: Optional[str] = None) -> dict:
        """
        Get account balance(s).
        
        Args:
            asset: Specific asset to get balance for (e.g., 'BTC', 'USDT').
                   If None, returns all non-zero balances.
        
        Returns:
            Dict with asset balances containing 'free' and 'locked' amounts.
        """
        self._ensure_connected()
        assert self.client is not None  # Type narrowing for Pylance

        account = await self.client.get_account()
        balances = account.get("balances", [])

        if asset:
            for balance in balances:
                if balance["asset"] == asset.upper():
                    return {
                        "asset": balance["asset"],
                        "free": Decimal(balance["free"]),
                        "locked": Decimal(balance["locked"]),
                        "total": Decimal(balance["free"]) + Decimal(balance["locked"])
                    }
            return {"asset": asset.upper(), "free": Decimal("0"), "locked": Decimal("0"), "total": Decimal("0")}

        # Return all non-zero balances
        result = {}
        for balance in balances:
            free = Decimal(balance["free"])
            locked = Decimal(balance["locked"])
            if free > 0 or locked > 0:
                result[balance["asset"]] = {
                    "free": free,
                    "locked": locked,
                    "total": free + locked
                }
        return result

    @retry_on_error(max_retries=3, delay=0.5)
    async def get_price(self, symbol: str) -> Decimal:
        """
        Get current price for a trading pair.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT').
        
        Returns:
            Current price as Decimal.
        """
        self._ensure_connected()
        assert self.client is not None  # Type narrowing for Pylance

        ticker = await self.client.get_symbol_ticker(symbol=symbol.upper())
        price = Decimal(ticker["price"])
        logger.debug(f"Price for {symbol}: {price}")
        return price

    @retry_on_error(max_retries=3, delay=1.0)
    async def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        quote_order_qty: Optional[float] = None
    ) -> dict:
        """
        Place a market order.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT').
            side: Order side - 'BUY' or 'SELL'.
            quantity: Amount of base asset to buy/sell.
            quote_order_qty: Alternative to quantity - amount in quote currency.
        
        Returns:
            Order response from Binance.
        """
        self._ensure_connected()
        assert self.client is not None  # Type narrowing for Pylance

        side = side.upper()
        if side not in ("BUY", "SELL"):
            raise ValueError("Side must be 'BUY' or 'SELL'")

        order_params = {
            "symbol": symbol.upper(),
            "side": side,
            "type": "MARKET",
        }

        if quote_order_qty is not None:
            order_params["quoteOrderQty"] = str(quote_order_qty)
        else:
            order_params["quantity"] = str(quantity)

        logger.info(f"Placing market {side} order for {symbol}: {order_params}")

        try:
            order = await self.client.create_order(**order_params)
            logger.info(f"Order placed successfully: {order['orderId']}")
            return {
                "order_id": order["orderId"],
                "symbol": order["symbol"],
                "side": order["side"],
                "status": order["status"],
                "executed_qty": Decimal(order["executedQty"]),
                "cummulative_quote_qty": Decimal(order["cummulativeQuoteQty"]),
                "fills": order.get("fills", [])
            }
        except BinanceAPIException as e:
            logger.error(f"Failed to place order: {e.message}")
            raise

    @retry_on_error(max_retries=3, delay=1.0)
    async def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """
        Get open orders.
        
        Args:
            symbol: Trading pair symbol. If None, returns all open orders.
        
        Returns:
            List of open orders.
        """
        self._ensure_connected()
        assert self.client is not None  # Type narrowing for Pylance

        if symbol:
            orders = await self.client.get_open_orders(symbol=symbol.upper())
        else:
            orders = await self.client.get_open_orders()

        return [
            {
                "order_id": order["orderId"],
                "symbol": order["symbol"],
                "side": order["side"],
                "type": order["type"],
                "price": Decimal(order["price"]),
                "quantity": Decimal(order["origQty"]),
                "executed_qty": Decimal(order["executedQty"]),
                "status": order["status"],
                "time": order["time"]
            }
            for order in orders
        ]

    @retry_on_error(max_retries=3, delay=1.0)
    async def get_open_positions(self) -> dict:
        """
        Get open positions (non-zero balances that could be traded).
        
        Returns:
            Dict of assets with non-zero free balance.
        """
        self._ensure_connected()

        balances = await self.get_account_balance()
        
        # Filter to only assets with tradeable amounts
        positions = {}
        for asset, balance in balances.items():
            if balance["free"] > Decimal("0.00000001"):  # Filter dust
                positions[asset] = {
                    "free": balance["free"],
                    "locked": balance["locked"],
                    "total": balance["total"]
                }
        
        return positions

    @retry_on_error(max_retries=3, delay=1.0)
    async def get_my_trades(self, symbol: str, limit: int = 50) -> list:
        """
        Get trade history for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT').
            limit: Maximum number of trades to return.
        
        Returns:
            List of trade dicts.
        """
        self._ensure_connected()
        assert self.client is not None

        try:
            trades = await self.client.get_my_trades(symbol=symbol.upper(), limit=limit)
            return [
                {
                    "id": trade["id"],
                    "symbol": trade["symbol"],
                    "price": Decimal(trade["price"]),
                    "qty": Decimal(trade["qty"]),
                    "quote_qty": Decimal(trade["quoteQty"]),
                    "time": trade["time"],
                    "is_buyer": trade["isBuyer"],
                    "is_maker": trade["isMaker"],
                }
                for trade in trades
            ]
        except Exception as e:
            logger.debug(f"Could not get trades for {symbol}: {e}")
            return []

    @retry_on_error(max_retries=3, delay=0.5)
    async def get_exchange_info(self, symbol: Optional[str] = None) -> dict:
        """
        Get exchange trading rules and symbol info.
        
        Args:
            symbol: Specific symbol to get info for.
        
        Returns:
            Exchange info dict.
        """
        self._ensure_connected()
        assert self.client is not None  # Type narrowing for Pylance

        info = await self.client.get_exchange_info()
        
        if symbol:
            for s in info["symbols"]:
                if s["symbol"] == symbol.upper():
                    return s
            raise ValueError(f"Symbol {symbol} not found")
        
        return info

    async def ping(self) -> bool:
        """Test connectivity to Binance API."""
        self._ensure_connected()
        assert self.client is not None  # Type narrowing for Pylance
        try:
            await self.client.ping()
            return True
        except Exception as e:
            logger.error(f"Ping failed: {e}")
            return False


# Example usage
async def main():
    """Example usage of BinanceClient."""
    async with BinanceClient(testnet=True) as client:
        # Test connection
        if await client.ping():
            print("Connected to Binance!")

        # Get BTC price
        price = await client.get_price("BTCUSDT")
        print(f"BTC/USDT Price: {price}")

        # Get account balances
        balances = await client.get_account_balance()
        print(f"Balances: {balances}")


if __name__ == "__main__":
    asyncio.run(main())
