"""Trading module for exchange integrations."""

from .binance_client import BinanceClient
from .portfolio import PortfolioManager, get_portfolio_manager

__all__ = ["BinanceClient", "PortfolioManager", "get_portfolio_manager"]
