"""
Exchange Connector
──────────────────
Wraps ccxt to provide a clean interface for:
  - Fetching OHLCV candles
  - Placing market / limit orders
  - Checking balances
  - Supports both live and paper-trading (testnet) mode
"""

import logging
import os
import time
from typing import Optional

import ccxt
import pandas as pd

import config

logger = logging.getLogger(__name__)

# Load secrets from environment (never hard-code these)
API_KEY = os.getenv("TRADING_BOT_API_KEY", config.API_KEY)
API_SECRET = os.getenv("TRADING_BOT_API_SECRET", config.API_SECRET)


def _build_exchange() -> ccxt.Exchange:
    exchange_class = getattr(ccxt, config.EXCHANGE)
    params = {
        "apiKey": API_KEY,
        "secret": API_SECRET,
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    }
    if config.TESTNET:
        params["options"]["defaultType"] = "future"
        # Binance testnet URLs
        if config.EXCHANGE == "binance":
            params["urls"] = {
                "api": {
                    "public": "https://testnet.binancefuture.com/fapi/v1",
                    "private": "https://testnet.binancefuture.com/fapi/v1",
                }
            }
    exchange = exchange_class(params)
    if config.TESTNET and hasattr(exchange, "set_sandbox_mode"):
        exchange.set_sandbox_mode(True)
    return exchange


class ExchangeClient:
    def __init__(self):
        self.exchange = _build_exchange()
        logger.info(f"Exchange: {config.EXCHANGE} | Testnet: {config.TESTNET}")

    def fetch_ohlcv(self, symbol: str, timeframe: str = config.TIMEFRAME,
                    limit: int = config.CANDLES_LOOKBACK) -> Optional[pd.DataFrame]:
        """Fetch OHLCV candles and return a DataFrame."""
        retries = 3
        for attempt in range(retries):
            try:
                raw = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                df.set_index("timestamp", inplace=True)
                return df
            except ccxt.NetworkError as e:
                wait = 2 ** attempt
                logger.warning(f"Network error fetching {symbol}: {e}. Retrying in {wait}s...")
                time.sleep(wait)
            except ccxt.ExchangeError as e:
                logger.error(f"Exchange error fetching {symbol}: {e}")
                return None
        return None

    def get_balance(self, currency: str = "USDT") -> float:
        try:
            balance = self.exchange.fetch_balance()
            return float(balance["free"].get(currency, 0.0))
        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")
            return 0.0

    def place_market_order(self, symbol: str, side: str, amount: float) -> Optional[dict]:
        """
        side: 'buy' or 'sell'
        amount: base asset quantity
        """
        if not API_KEY or not API_SECRET:
            logger.warning("No API credentials — paper trade mode (order not sent)")
            return {"id": "PAPER", "symbol": symbol, "side": side, "amount": amount, "status": "closed"}
        try:
            order = self.exchange.create_market_order(symbol, side, amount)
            logger.info(f"Order placed: {side.upper()} {amount} {symbol} | ID: {order['id']}")
            return order
        except ccxt.InsufficientFunds:
            logger.error(f"Insufficient funds for {side} {amount} {symbol}")
        except ccxt.ExchangeError as e:
            logger.error(f"Order failed: {e}")
        return None

    def get_current_price(self, symbol: str) -> Optional[float]:
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return float(ticker["last"])
        except Exception as e:
            logger.error(f"Failed to get price for {symbol}: {e}")
            return None
