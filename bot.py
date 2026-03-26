"""
AI Trading Bot — Main Entry Point
──────────────────────────────────
Run:
    python bot.py              # Live / testnet trading
    python bot.py --backtest   # Backtest mode
    python bot.py --paper      # Paper trading (no real orders)
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import config
from exchange import ExchangeClient
from risk_manager import Portfolio, RiskManager
from strategy import Signal, analyze

# ── Logging setup ─────────────────────────────────────────────────────────────
Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(config.LOG_FILE),
    ],
)
logger = logging.getLogger(__name__)


# ── Trade journal ─────────────────────────────────────────────────────────────
def _save_trade(trade: dict):
    trades = []
    if Path(config.TRADES_FILE).exists():
        with open(config.TRADES_FILE) as f:
            trades = json.load(f)
    trades.append(trade)
    with open(config.TRADES_FILE, "w") as f:
        json.dump(trades, f, indent=2, default=str)


def _print_status(portfolio: Portfolio):
    total_return = (portfolio.capital - config.INITIAL_CAPITAL) / config.INITIAL_CAPITAL
    logger.info(
        f"\n{'═'*60}\n"
        f"  Capital  : ${portfolio.capital:>10.2f}   (start: ${config.INITIAL_CAPITAL:.2f})\n"
        f"  Return   : {total_return:>+10.2%}\n"
        f"  Drawdown : {portfolio.drawdown_pct:>10.2%}\n"
        f"  Trades   : {portfolio.trade_count}  (Win rate: {portfolio.win_rate:.0%})\n"
        f"  Positions: {portfolio.open_position_count}/{config.MAX_OPEN_POSITIONS}\n"
        f"{'═'*60}"
    )


# ── Main trading loop ─────────────────────────────────────────────────────────
class TradingBot:
    def __init__(self, paper: bool = False):
        self.paper = paper
        self.client = ExchangeClient()
        self.portfolio = Portfolio()
        self.risk = RiskManager(self.portfolio)
        logger.info(
            f"Bot started | Capital: ${config.INITIAL_CAPITAL} | "
            f"Symbols: {config.SYMBOLS} | TF: {config.TIMEFRAME}"
        )

    def _execute_open(self, symbol: str, signal: Signal, size: float) -> bool:
        if self.paper:
            logger.info(f"[PAPER] Would BUY {size} {symbol}")
            return True
        side = "buy" if signal == Signal.LONG else "sell"
        order = self.client.place_market_order(symbol, side, size)
        return order is not None

    def _execute_close(self, symbol: str, signal: Signal, size: float) -> bool:
        if self.paper:
            logger.info(f"[PAPER] Would CLOSE {symbol}")
            return True
        side = "sell" if signal == Signal.LONG else "buy"
        order = self.client.place_market_order(symbol, side, size)
        return order is not None

    def _check_existing_positions(self):
        """Check open positions for exits."""
        for symbol in list(self.portfolio.positions.keys()):
            position = self.portfolio.positions[symbol]
            price = self.client.get_current_price(symbol)
            if price is None:
                continue

            reason = self.risk.should_close(position, price)
            if reason:
                if self._execute_close(symbol, position.signal, position.size):
                    pnl = self.risk.close_position(symbol, price, reason)
                    _save_trade({
                        "time": datetime.utcnow().isoformat(),
                        "symbol": symbol,
                        "direction": position.signal.value,
                        "entry": position.entry,
                        "exit": price,
                        "pnl": pnl,
                        "reason": reason,
                    })

    def _scan_for_signals(self):
        """Scan all symbols for new trade setups."""
        allowed, reason = self.risk.is_trading_allowed()
        if not allowed:
            logger.warning(f"New entries blocked: {reason}")
            return

        setups = []
        for symbol in config.SYMBOLS:
            if symbol in self.portfolio.positions:
                continue  # already in position

            df = self.client.fetch_ohlcv(symbol)
            if df is None or len(df) < config.CANDLES_LOOKBACK // 2:
                continue

            setup = analyze(symbol, df)
            if setup:
                logger.info(
                    f"Signal: {setup.signal.value} {symbol} | "
                    f"Score: {setup.score:.0f} | "
                    f"Conditions: {setup.reasons}"
                )
                setups.append(setup)

        # Sort by quality score — take best setups first
        setups.sort(key=lambda s: s.score, reverse=True)

        for setup in setups:
            allowed, reason = self.risk.is_trading_allowed()
            if not allowed:
                break

            size = self.risk.calculate_position_size(setup)
            if size is None:
                continue

            position = self.risk.open_position(setup, size)
            if position and self._execute_open(setup.symbol, setup.signal, size):
                _save_trade({
                    "time": datetime.utcnow().isoformat(),
                    "symbol": setup.symbol,
                    "direction": setup.signal.value,
                    "entry": setup.entry,
                    "stop_loss": setup.stop_loss,
                    "take_profit": setup.take_profit,
                    "size": size,
                    "score": setup.score,
                    "reasons": setup.reasons,
                })

    def run(self):
        logger.info("Starting main loop. Press Ctrl+C to stop.")
        cycle = 0
        while True:
            try:
                cycle += 1
                logger.info(f"── Cycle {cycle} ──────────────────────────")
                self._check_existing_positions()
                self._scan_for_signals()
                if cycle % 10 == 0:
                    _print_status(self.portfolio)
                time.sleep(config.LOOP_INTERVAL_SECONDS)
            except KeyboardInterrupt:
                logger.info("Bot stopped by user.")
                _print_status(self.portfolio)
                break
            except Exception as e:
                logger.exception(f"Unexpected error in main loop: {e}")
                time.sleep(10)  # brief pause before retry


# ── Entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Trading Bot")
    parser.add_argument("--paper", action="store_true", help="Paper trade (no real orders)")
    parser.add_argument("--backtest", action="store_true", help="Run backtester")
    args = parser.parse_args()

    if args.backtest:
        from backtester import run_backtest
        run_backtest()
    else:
        TradingBot(paper=args.paper).run()
