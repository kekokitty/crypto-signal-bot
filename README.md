# 🤖 Crypto Signal Bot

Advanced cryptocurrency trading bot with technical analysis, Support/Resistance detection, and Telegram integration.

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)
![Binance](https://img.shields.io/badge/Binance-API-F0B90B.svg)

## ✨ Features

### 📊 Technical Analysis
- **EMA Stack**: 20/50/200 period moving averages
- **RSI**: Relative Strength Index with overbought/oversold detection
- **MACD**: Moving Average Convergence Divergence with crossover signals
- **ATR**: Average True Range for volatility measurement
- **Volume Analysis**: Volume confirmation with ratio analysis

### 🎯 Support/Resistance Detection
- Automatic S/R level detection using pivot points
- **S/R Flip Detection**: Identify when support becomes resistance (and vice versa)
- Price distance calculations from key levels

### 📈 Smart Signal Generation
| Signal | Confidence | Description |
|--------|------------|-------------|
| 🚀 STRONG_BUY | 80-100% | Multiple bullish confirmations + S/R flip |
| 🟢 BUY | 60-79% | Bullish trend with good momentum |
| 🟡 WEAK_BUY | 40-59% | Mild bullish signals |
| ⏸️ HOLD | 0-39% | No clear direction |
| 🟠 WEAK_SELL | 40-59% | Mild bearish signals |
| 🔴 SELL | 60-79% | Bearish trend with momentum |
| 💥 STRONG_SELL | 80-100% | Multiple bearish confirmations |

### 📱 Telegram Integration
- Real-time signal notifications
- Professional candlestick charts
- Interactive command interface
- Portfolio tracking

### 🐳 Docker Ready
- One-command deployment
- Persistent data storage
- Auto-restart on failure

## 📸 Screenshots

### Signal Chart
```
📊 Professional candlestick charts with:
- EMA 20/50/200 overlays
- RSI indicator panel
- Volume bars
- S/R level lines
- Signal annotations
```

### Telegram Notifications
```
🚀 BTCUSDT - STRONG_BUY (85%)

💰 Price: $94,500.00
📊 Trend: Strong Up
⚡ RSI: 45.2
📉 MACD: Bullish

📋 Analysis:
• Strong uptrend with EMA stack bullish
• Price bounced from support at $93,800
• MACD bullish crossover
• Volume confirmation (1.5x average)

🔢 Score: Bull 85 | Bear 15 | Net +70
```

## 🚀 Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone repository
git clone https://github.com/yourusername/crypto-signal-bot.git
cd crypto-signal-bot

# Configure environment
cp .env.example .env
nano .env  # Edit with your API keys

# Start bot
docker-compose up -d

# View logs
docker-compose logs -f
```

### Option 2: Local Installation

```bash
# Clone repository
git clone https://github.com/yourusername/crypto-signal-bot.git
cd crypto-signal-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env  # Edit with your API keys

# Run bot
python -m src.main --commands --interval 15
```

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `BINANCE_API_KEY` | Binance API key | ✅ Yes | - |
| `BINANCE_SECRET` | Binance API secret | ✅ Yes | - |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather | ✅ Yes | - |
| `TELEGRAM_CHAT_ID` | Your Telegram chat/group ID | ✅ Yes | - |
| `BINANCE_TESTNET` | Use Binance testnet | No | `True` |
| `LOG_LEVEL` | Logging level | No | `INFO` |

### CLI Arguments

```bash
python -m src.main [OPTIONS]

Options:
  --once              Run analysis once and exit
  --interval MINUTES  Minutes between analysis runs (default: 15)
  --symbols SYMBOL    Trading pairs to analyze (default: BTCUSDT ETHUSDT)
  --timeframe TF      Candle timeframe: 1m,5m,15m,30m,1h,4h,1d (default: 1h)
  --commands          Enable Telegram command handlers
  --no-notify         Disable Telegram notifications
  --auto-trade        Enable auto-trading (use with caution!)
  --live              Disable paper trading (REAL MONEY!)
```

### Example Usage

```bash
# Single analysis run
python -m src.main --once --symbols BTCUSDT ETHUSDT SOLUSDT

# Continuous monitoring with commands
python -m src.main --commands --interval 15 --symbols BTCUSDT ETHUSDT

# 4-hour timeframe analysis
python -m src.main --once --timeframe 4h --symbols BTCUSDT
```

## 📈 Trading Strategy

### Buy Conditions (Bullish Score)
| Condition | Points |
|-----------|--------|
| Price > EMA50 (uptrend) | +15 |
| EMA20 > EMA50 > EMA200 (bullish stack) | +20 |
| Price near support level (within 1.5%) | +15 |
| RSI 30-50 (oversold recovery) | +10 |
| RSI < 30 (extremely oversold) | +15 |
| MACD bullish crossover | +15 |
| High volume (>1.2x average) | +10 |
| **S/R Bullish Flip** | +25 |

### Sell Conditions (Bearish Score)
| Condition | Points |
|-----------|--------|
| Price < EMA50 (downtrend) | +15 |
| EMA20 < EMA50 < EMA200 (bearish stack) | +20 |
| Price near resistance level (within 1.5%) | +15 |
| RSI 50-70 (overbought warning) | +10 |
| RSI > 70 (extremely overbought) | +15 |
| MACD bearish crossover | +15 |
| Low volume (<0.8x average) | +5 |
| **S/R Bearish Flip** | +25 |

### S/R Flip Explained
- **Bullish Flip**: Previous resistance level now acts as support → Strong buy signal
- **Bearish Flip**: Previous support level now acts as resistance → Strong sell signal

## 🤖 Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and bot info |
| `/help` | Show all available commands |
| `/balance` | Display account balances |
| `/positions` | Show open positions with P&L |
| `/trades` | Recent trade history |
| `/pnl` | Profit/Loss summary (daily/weekly/monthly) |
| `/analyze BTCUSDT` | Analyze specific trading pair |
| `/stats` | Bot statistics and performance |
| `/status` | Bot uptime and connection status |

## 📁 Project Structure

```
crypto-signal-bot/
├── src/
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── indicators.py      # Technical indicators (EMA, RSI, MACD)
│   │   ├── signals.py         # Signal generation logic
│   │   └── support_resistance.py  # S/R detection
│   ├── trading/
│   │   ├── __init__.py
│   │   ├── binance_client.py  # Binance API wrapper
│   │   └── portfolio.py       # Portfolio tracking
│   ├── notifications/
│   │   ├── __init__.py
│   │   └── telegram_bot.py    # Telegram notifications
│   ├── visualization/
│   │   ├── __init__.py
│   │   └── chart_generator.py # Chart generation
│   ├── commands/
│   │   ├── __init__.py
│   │   └── telegram_commands.py  # Command handlers
│   ├── __init__.py
│   ├── config.py              # Configuration management
│   ├── database.py            # SQLite database
│   ├── logger.py              # Logging setup
│   └── main.py                # Entry point
├── data/                      # Database files
├── charts/                    # Generated charts
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .env.example
├── requirements.txt
├── LICENSE
└── README.md
```

## 🔧 Development

### Running Tests
```bash
# Install dev dependencies
pip install pytest pytest-asyncio

# Run tests
pytest tests/
```

### Code Quality
```bash
# Install linting tools
pip install flake8 black isort

# Format code
black src/
isort src/

# Check code quality
flake8 src/
```

## ⚠️ Disclaimer

**USE AT YOUR OWN RISK!**

This bot is for educational purposes only. Cryptocurrency trading involves substantial risk of loss. The developers are not responsible for any financial losses incurred while using this software.

- Always start with **paper trading** (`PAPER_TRADING=True`)
- Never invest more than you can afford to lose
- Past performance does not guarantee future results
- Test thoroughly on testnet before using real funds

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

Made with ❤️ for the crypto community
