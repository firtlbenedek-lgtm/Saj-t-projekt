"""
Backtester
──────────
Simulates the strategy on historical data to evaluate performance before
going live. Uses the same strategy and risk logic as the live bot.

Usage:
    python bot.py --backtest
    python backtester.py   (direct run)
"""

import logging
from dataclasses import dataclass
from typing import List

import pandas as pd

import config
from strategy import Signal, analyze, compute_indicators

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    symbol: str
    direction: str
    entry_idx: int
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_price: float = 0.0
    exit_idx: int = 0
    exit_reason: str = ""
    pnl_pct: float = 0.0
    pnl_usd: float = 0.0


def _simulate_trade(df: pd.DataFrame, entry_idx: int, entry: float,
                    stop: float, tp: float, signal: Signal) -> tuple[float, int, str]:
    """Walk forward bar-by-bar to find the exit."""
    for i in range(entry_idx + 1, len(df)):
        high = df["high"].iloc[i]
        low = df["low"].iloc[i]

        if signal == Signal.LONG:
            if low <= stop:
                return stop, i, "stop_loss"
            if high >= tp:
                return tp, i, "take_profit"
        else:
            if high >= stop:
                return stop, i, "stop_loss"
            if low <= tp:
                return tp, i, "take_profit"

    # Position still open at end of data — close at last price
    last_price = df["close"].iloc[-1]
    return last_price, len(df) - 1, "end_of_data"


def backtest_symbol(symbol: str, df: pd.DataFrame, capital: float) -> tuple[List[BacktestTrade], float]:
    df = compute_indicators(df)
    trades: List[BacktestTrade] = []
    current_capital = capital
    in_trade = False
    entry_idx = 0

    # Walk-forward: for each candle, analyze up to that candle
    for i in range(100, len(df) - 1):
        if in_trade:
            continue

        window = df.iloc[: i + 1]
        setup = analyze(symbol, window)
        if setup is None:
            continue

        risk_amount = current_capital * config.RISK_PER_TRADE
        risk_per_unit = abs(setup.entry - setup.stop_loss)
        if risk_per_unit <= 0:
            continue
        size = risk_amount / risk_per_unit

        exit_price, exit_idx, reason = _simulate_trade(
            df, i, setup.entry, setup.stop_loss, setup.take_profit, setup.signal
        )

        if setup.signal == Signal.LONG:
            raw_pnl = (exit_price - setup.entry) * size
        else:
            raw_pnl = (setup.entry - exit_price) * size

        fee = exit_price * config.FEE_PCT * size * 2  # entry + exit fees
        net_pnl = raw_pnl - fee
        pnl_pct = net_pnl / current_capital

        current_capital += net_pnl

        trade = BacktestTrade(
            symbol=symbol,
            direction=setup.signal.value,
            entry_idx=i,
            entry_price=setup.entry,
            stop_loss=setup.stop_loss,
            take_profit=setup.take_profit,
            exit_price=exit_price,
            exit_idx=exit_idx,
            exit_reason=reason,
            pnl_pct=pnl_pct,
            pnl_usd=net_pnl,
        )
        trades.append(trade)

        # Skip forward to exit candle
        in_trade = False  # simplified: allow new trades after exit
        i = exit_idx

    return trades, current_capital


def _print_report(symbol: str, trades: List[BacktestTrade], start_capital: float, end_capital: float):
    if not trades:
        print(f"\n{symbol}: No trades generated.")
        return

    wins = [t for t in trades if t.pnl_usd > 0]
    losses = [t for t in trades if t.pnl_usd <= 0]
    total_return = (end_capital - start_capital) / start_capital
    win_rate = len(wins) / len(trades)

    avg_win = sum(t.pnl_usd for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t.pnl_usd for t in losses) / len(losses) if losses else 0
    profit_factor = abs(sum(t.pnl_usd for t in wins) / sum(t.pnl_usd for t in losses)) if losses else float("inf")

    # Max drawdown
    running = start_capital
    peak = start_capital
    max_dd = 0.0
    for t in trades:
        running += t.pnl_usd
        peak = max(peak, running)
        dd = (peak - running) / peak
        max_dd = max(max_dd, dd)

    print(f"""
╔══════════════════════════════════════════════════════╗
║  BACKTEST RESULTS — {symbol:<34}║
╠══════════════════════════════════════════════════════╣
║  Start Capital : ${start_capital:>10.2f}                        ║
║  End Capital   : ${end_capital:>10.2f}                        ║
║  Total Return  : {total_return:>+10.2%}                        ║
║  Max Drawdown  : {max_dd:>10.2%}                        ║
╠══════════════════════════════════════════════════════╣
║  Total Trades  : {len(trades):>10}                        ║
║  Win Rate      : {win_rate:>10.1%}                        ║
║  Profit Factor : {profit_factor:>10.2f}                        ║
║  Avg Win       : ${avg_win:>10.2f}                        ║
║  Avg Loss      : ${avg_loss:>10.2f}                        ║
╚══════════════════════════════════════════════════════╝""")


def run_backtest():
    """
    To backtest, you need historical OHLCV data.
    Options:
      1. Fetch live from exchange (requires ccxt + credentials)
      2. Load from CSV files placed in data/ directory

    This function tries CSV first, then falls back to exchange.
    """
    import os
    from pathlib import Path
    from exchange import ExchangeClient

    total_start = config.INITIAL_CAPITAL / len(config.SYMBOLS)

    for symbol in config.SYMBOLS:
        csv_path = Path("data") / f"{symbol.replace('/', '_')}.csv"

        if csv_path.exists():
            df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
            df.columns = [c.lower() for c in df.columns]
        else:
            print(f"Fetching data for {symbol} from exchange...")
            client = ExchangeClient()
            df = client.fetch_ohlcv(symbol, limit=1000)
            if df is None:
                print(f"Could not fetch data for {symbol}, skipping.")
                continue
            os.makedirs("data", exist_ok=True)
            df.to_csv(csv_path)

        trades, end_capital = backtest_symbol(symbol, df, total_start)
        _print_report(symbol, trades, total_start, end_capital)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    run_backtest()
