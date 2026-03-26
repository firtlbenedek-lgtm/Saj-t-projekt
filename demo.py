"""
Demo mode — offline simulation with synthetic market data.
Shows the full bot logic (signals, risk management, trade journal) without
requiring any exchange API connection.

Usage:
    python demo.py
"""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

import config
from demo_data import generate_ohlcv
from risk_manager import Portfolio, RiskManager
from strategy import Signal, analyze

# ── Logging ───────────────────────────────────────────────────────────────────
Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

TRADES_FILE = "logs/demo_trades.json"


def _save_trade(trade: dict):
    trades = []
    if Path(TRADES_FILE).exists():
        with open(TRADES_FILE) as f:
            trades = json.load(f)
    trades.append(trade)
    with open(TRADES_FILE, "w") as f:
        json.dump(trades, f, indent=2, default=str)


def _get_current_price(df, candle_idx: int) -> float:
    return float(df["close"].iloc[candle_idx])


def _print_status(portfolio: Portfolio, cycle: int):
    total_return = (portfolio.capital - config.INITIAL_CAPITAL) / config.INITIAL_CAPITAL
    print(f"""
╔══════════════════════════════════════════════╗
║  LIVE STATUS  (Cycle {cycle:<3})                    ║
╠══════════════════════════════════════════════╣
║  Capital   : ${portfolio.capital:>10.2f}  (${config.INITIAL_CAPITAL:.0f} start)  ║
║  Return    : {total_return:>+10.2%}                    ║
║  Drawdown  : {portfolio.drawdown_pct:>10.2%}                    ║
║  Trades    : {portfolio.trade_count:<5}  Win Rate: {portfolio.win_rate:.0%}           ║
║  Positions : {portfolio.open_position_count}/{config.MAX_OPEN_POSITIONS}                            ║
╚══════════════════════════════════════════════╝""")


def run_demo():
    logger.info("=" * 60)
    logger.info("  DEMO MODE — Synthetic market data (no real orders)")
    logger.info("=" * 60)

    # Generate synthetic data for all symbols
    datasets = {sym: generate_ohlcv(sym, n_candles=400) for sym in config.SYMBOLS}

    portfolio = Portfolio()
    risk = RiskManager(portfolio)
    n_candles = min(len(df) for df in datasets.values())

    logger.info(f"Simulating {n_candles} candles across {len(config.SYMBOLS)} symbols")
    logger.info(f"Starting capital: ${portfolio.capital:.2f}\n")

    for candle_idx in range(150, n_candles):
        # ── Check existing positions ──────────────────────────────────────
        for symbol in list(portfolio.positions.keys()):
            position = portfolio.positions[symbol]
            current_price = _get_current_price(datasets[symbol], candle_idx)
            reason = risk.should_close(position, current_price)
            if reason:
                pnl = risk.close_position(symbol, current_price, reason)
                _save_trade({
                    "candle": candle_idx,
                    "time": str(datasets[symbol].index[candle_idx]),
                    "symbol": symbol,
                    "direction": position.signal.value,
                    "entry": position.entry,
                    "exit": current_price,
                    "pnl_usd": round(pnl, 2),
                    "reason": reason,
                })

        # ── Scan for new signals ──────────────────────────────────────────
        allowed, block_reason = risk.is_trading_allowed()
        if allowed:
            setups = []
            for symbol in config.SYMBOLS:
                if symbol in portfolio.positions:
                    continue
                window = datasets[symbol].iloc[: candle_idx + 1]
                setup = analyze(symbol, window)
                if setup:
                    setups.append(setup)

            setups.sort(key=lambda s: s.score, reverse=True)

            for setup in setups:
                allowed, _ = risk.is_trading_allowed()
                if not allowed:
                    break
                size = risk.calculate_position_size(setup)
                if size is None:
                    continue
                position = risk.open_position(setup, size)
                if position:
                    _save_trade({
                        "candle": candle_idx,
                        "time": str(datasets[setup.symbol].index[candle_idx]),
                        "symbol": setup.symbol,
                        "direction": setup.signal.value,
                        "entry": setup.entry,
                        "stop_loss": setup.stop_loss,
                        "take_profit": setup.take_profit,
                        "size": size,
                        "score": setup.score,
                        "reasons": setup.reasons,
                    })

        # ── Print status every 50 candles ─────────────────────────────────
        step = candle_idx - 150
        if step % 50 == 0:
            _print_status(portfolio, step)

        time.sleep(0.02)  # slight delay for visual effect

    # ── Final report ──────────────────────────────────────────────────────
    # Close all open positions at last price
    for symbol in list(portfolio.positions.keys()):
        position = portfolio.positions[symbol]
        last_price = _get_current_price(datasets[symbol], -1)
        risk.close_position(symbol, last_price, "end_of_simulation")

    total_return = (portfolio.capital - config.INITIAL_CAPITAL) / config.INITIAL_CAPITAL

    print(f"""
╔══════════════════════════════════════════════════════╗
║            SIMULATION COMPLETE                       ║
╠══════════════════════════════════════════════════════╣
║  Start Capital  : ${config.INITIAL_CAPITAL:>10.2f}                      ║
║  End Capital    : ${portfolio.capital:>10.2f}                      ║
║  Total Return   : {total_return:>+10.2%}                      ║
║  Total Trades   : {portfolio.trade_count:>10}                      ║
║  Win Rate       : {portfolio.win_rate:>10.1%}                      ║
║  Max Drawdown   : {portfolio.drawdown_pct:>10.2%}                      ║
╚══════════════════════════════════════════════════════╝
Trade log saved to: {TRADES_FILE}
""")


if __name__ == "__main__":
    run_demo()
