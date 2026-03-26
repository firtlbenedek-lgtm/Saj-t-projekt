"""
Trading Bot Configuration
Modify these settings to customize the bot's behavior.
"""

# ─── Exchange Settings ────────────────────────────────────────────────────────
EXCHANGE = "binance"          # Supported: binance, bybit, kraken, coinbase
API_KEY = ""                  # Set via .env or environment variable
API_SECRET = ""               # Set via .env or environment variable
TESTNET = True                # ALWAYS start on testnet! Switch to False only when ready.

# ─── Trading Universe ─────────────────────────────────────────────────────────
SYMBOLS = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "BNB/USDT",
]
TIMEFRAME = "1h"              # Candle timeframe: 1m, 5m, 15m, 1h, 4h, 1d

# ─── Capital & Risk Management ───────────────────────────────────────────────
INITIAL_CAPITAL = 1000.0      # Starting capital in USD
RISK_PER_TRADE = 0.015        # Risk 1.5% of portfolio per trade (Kelly-inspired)
MAX_OPEN_POSITIONS = 3        # Maximum simultaneous positions
MAX_DAILY_LOSS_PCT = 0.05     # Stop trading if daily drawdown exceeds 5%
MAX_DRAWDOWN_PCT = 0.15       # Stop trading if total drawdown exceeds 15%

# ─── Strategy Parameters ─────────────────────────────────────────────────────
EMA_FAST = 9
EMA_SLOW = 21
EMA_TREND = 50
RSI_PERIOD = 14
RSI_OVERSOLD = 35
RSI_OVERBOUGHT = 70
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2.0
ATR_PERIOD = 14
VOLUME_MA_PERIOD = 20

# ─── Position Sizing & Exits ─────────────────────────────────────────────────
ATR_STOP_MULTIPLIER = 1.5    # Stop loss = entry - (ATR * multiplier)
RISK_REWARD_RATIO = 2.5      # Take profit = entry + (stop distance * R:R)
TRAILING_STOP_TRIGGER = 1.0  # Activate trailing stop after 1x risk gain
TRAILING_STOP_PCT = 0.02     # Trailing stop distance: 2%

# ─── Execution Settings ──────────────────────────────────────────────────────
LOOP_INTERVAL_SECONDS = 60   # How often to scan the market (seconds)
CANDLES_LOOKBACK = 200       # How many candles to fetch for indicator calculation
MIN_VOLUME_SPIKE = 1.3       # Volume must be 1.3x the MA to confirm signal
SLIPPAGE_PCT = 0.001         # Assumed slippage 0.1%
FEE_PCT = 0.001              # Assumed trading fee 0.1%

# ─── Logging ─────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
LOG_FILE = "logs/trading_bot.log"
TRADES_FILE = "logs/trades.json"
