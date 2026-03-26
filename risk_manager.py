"""
Risk Manager
────────────
Handles:
  - Position sizing (fixed fractional / Kelly-inspired)
  - Daily loss limit enforcement
  - Maximum drawdown circuit breaker
  - Trailing stop updates
  - Portfolio exposure cap
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Optional

import config
from strategy import Signal, TradeSetup

logger = logging.getLogger(__name__)


@dataclass
class Position:
    symbol: str
    signal: Signal
    entry: float
    stop_loss: float
    take_profit: float
    size: float           # position size in base asset
    value_at_risk: float  # USD risked on this trade
    trailing_active: bool = False
    trailing_stop: float = 0.0
    peak_price: float = 0.0


@dataclass
class Portfolio:
    capital: float = config.INITIAL_CAPITAL
    peak_capital: float = config.INITIAL_CAPITAL
    daily_start_capital: float = config.INITIAL_CAPITAL
    last_reset_date: date = field(default_factory=date.today)
    positions: Dict[str, Position] = field(default_factory=dict)
    closed_pnl: float = 0.0
    trade_count: int = 0
    win_count: int = 0

    @property
    def open_position_count(self) -> int:
        return len(self.positions)

    @property
    def total_value(self) -> float:
        return self.capital  # unrealized PnL tracked externally

    @property
    def drawdown_pct(self) -> float:
        if self.peak_capital == 0:
            return 0.0
        return (self.peak_capital - self.capital) / self.peak_capital

    @property
    def daily_loss_pct(self) -> float:
        if self.daily_start_capital == 0:
            return 0.0
        return max(0.0, (self.daily_start_capital - self.capital) / self.daily_start_capital)

    @property
    def win_rate(self) -> float:
        if self.trade_count == 0:
            return 0.0
        return self.win_count / self.trade_count


class RiskManager:
    def __init__(self, portfolio: Portfolio):
        self.portfolio = portfolio

    # ── Daily reset ───────────────────────────────────────────────────────────
    def check_daily_reset(self):
        today = date.today()
        if self.portfolio.last_reset_date != today:
            self.portfolio.daily_start_capital = self.portfolio.capital
            self.portfolio.last_reset_date = today
            logger.info(f"Daily capital reset: ${self.portfolio.capital:.2f}")

    # ── Circuit breakers ──────────────────────────────────────────────────────
    def is_trading_allowed(self) -> tuple[bool, str]:
        self.check_daily_reset()

        if self.portfolio.daily_loss_pct >= config.MAX_DAILY_LOSS_PCT:
            return False, f"Daily loss limit hit ({self.portfolio.daily_loss_pct:.1%})"

        if self.portfolio.drawdown_pct >= config.MAX_DRAWDOWN_PCT:
            return False, f"Max drawdown hit ({self.portfolio.drawdown_pct:.1%})"

        if self.portfolio.open_position_count >= config.MAX_OPEN_POSITIONS:
            return False, f"Max positions open ({config.MAX_OPEN_POSITIONS})"

        return True, "OK"

    # ── Position sizing ───────────────────────────────────────────────────────
    def calculate_position_size(self, setup: TradeSetup) -> Optional[float]:
        """
        Fixed fractional sizing:
          risk_amount = capital × RISK_PER_TRADE
          size        = risk_amount / risk_distance_in_USD
        Returns size in base asset units, or None if trade is too small.
        """
        risk_amount = self.portfolio.capital * config.RISK_PER_TRADE
        risk_per_unit = abs(setup.entry - setup.stop_loss)

        if risk_per_unit <= 0:
            logger.warning(f"Zero risk distance for {setup.symbol}, skipping.")
            return None

        size = risk_amount / risk_per_unit

        # Sanity check: don't use more than 30% of capital on one trade
        max_size = (self.portfolio.capital * 0.30) / setup.entry
        size = min(size, max_size)

        min_notional = 10.0  # $10 minimum order
        if size * setup.entry < min_notional:
            logger.info(f"Position too small for {setup.symbol} (${size * setup.entry:.2f})")
            return None

        return round(size, 6)

    # ── Open a new position ───────────────────────────────────────────────────
    def open_position(self, setup: TradeSetup, size: float) -> Optional[Position]:
        allowed, reason = self.is_trading_allowed()
        if not allowed:
            logger.warning(f"Trade blocked: {reason}")
            return None

        if setup.symbol in self.portfolio.positions:
            logger.info(f"Already in position for {setup.symbol}")
            return None

        value_at_risk = size * abs(setup.entry - setup.stop_loss)
        position = Position(
            symbol=setup.symbol,
            signal=setup.signal,
            entry=setup.entry,
            stop_loss=setup.stop_loss,
            take_profit=setup.take_profit,
            size=size,
            value_at_risk=value_at_risk,
            peak_price=setup.entry,
        )
        self.portfolio.positions[setup.symbol] = position
        self.portfolio.capital -= value_at_risk  # reserve risk capital
        logger.info(
            f"OPENED {setup.signal.value} {setup.symbol} | "
            f"Entry: {setup.entry:.4f} | SL: {setup.stop_loss:.4f} | "
            f"TP: {setup.take_profit:.4f} | Size: {size} | Risk: ${value_at_risk:.2f}"
        )
        return position

    # ── Update trailing stop ──────────────────────────────────────────────────
    def update_trailing_stop(self, position: Position, current_price: float):
        if position.signal == Signal.LONG:
            if current_price > position.peak_price:
                position.peak_price = current_price
            gain = current_price - position.entry
            trigger = position.value_at_risk / position.size  # 1R
            if gain >= trigger and not position.trailing_active:
                position.trailing_active = True
                logger.info(f"Trailing stop activated for {position.symbol}")
            if position.trailing_active:
                new_stop = position.peak_price * (1 - config.TRAILING_STOP_PCT)
                position.trailing_stop = max(position.trailing_stop, new_stop)
        else:
            if current_price < position.peak_price or position.peak_price == 0:
                position.peak_price = current_price
            loss = position.entry - current_price
            trigger = position.value_at_risk / position.size
            if loss >= trigger and not position.trailing_active:
                position.trailing_active = True
                logger.info(f"Trailing stop activated for {position.symbol}")
            if position.trailing_active:
                new_stop = position.peak_price * (1 + config.TRAILING_STOP_PCT)
                if position.trailing_stop == 0:
                    position.trailing_stop = new_stop
                else:
                    position.trailing_stop = min(position.trailing_stop, new_stop)

    # ── Check if position should be closed ───────────────────────────────────
    def should_close(self, position: Position, current_price: float) -> Optional[str]:
        self.update_trailing_stop(position, current_price)

        if position.signal == Signal.LONG:
            if current_price <= position.stop_loss:
                return "stop_loss"
            if position.trailing_active and current_price <= position.trailing_stop:
                return "trailing_stop"
            if current_price >= position.take_profit:
                return "take_profit"
        else:
            if current_price >= position.stop_loss:
                return "stop_loss"
            if position.trailing_active and current_price >= position.trailing_stop:
                return "trailing_stop"
            if current_price <= position.take_profit:
                return "take_profit"

        return None

    # ── Close a position ──────────────────────────────────────────────────────
    def close_position(self, symbol: str, exit_price: float, reason: str) -> float:
        position = self.portfolio.positions.pop(symbol, None)
        if not position:
            return 0.0

        slippage_cost = exit_price * config.SLIPPAGE_PCT
        fee_cost = exit_price * config.FEE_PCT

        if position.signal == Signal.LONG:
            raw_pnl = (exit_price - position.entry) * position.size
        else:
            raw_pnl = (position.entry - exit_price) * position.size

        net_pnl = raw_pnl - (slippage_cost + fee_cost) * position.size

        # Return reserved risk capital + PnL
        self.portfolio.capital += position.value_at_risk + net_pnl
        self.portfolio.closed_pnl += net_pnl
        self.portfolio.trade_count += 1
        if net_pnl > 0:
            self.portfolio.win_count += 1

        if self.portfolio.capital > self.portfolio.peak_capital:
            self.portfolio.peak_capital = self.portfolio.capital

        logger.info(
            f"CLOSED {position.signal.value} {symbol} | "
            f"Exit: {exit_price:.4f} | PnL: ${net_pnl:.2f} | "
            f"Reason: {reason} | Capital: ${self.portfolio.capital:.2f}"
        )
        return net_pnl
