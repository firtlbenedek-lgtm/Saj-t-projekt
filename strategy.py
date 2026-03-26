"""
Multi-Indicator Momentum Strategy
──────────────────────────────────
Entry logic (LONG):
  1. Trend alignment : EMA9 > EMA21 > EMA50
  2. Momentum       : RSI between 45–70 (bullish, not overbought)
  3. MACD confirm   : MACD histogram positive AND increasing
  4. Pullback entry : Price retraced to EMA21 or lower Bollinger Band
  5. Volume confirm : Current volume > 1.3× volume MA

SHORT signals are the mirror image with RSI < 55.

Exit logic:
  - Hard stop-loss   : entry ± (ATR × 1.5)
  - Take-profit      : entry ± (stop distance × 2.5)
  - Trailing stop    : activated after +1R move
  - RSI reversal exit: RSI crosses back through 50 against position
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd

import config


class Signal(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


@dataclass
class TradeSetup:
    symbol: str
    signal: Signal
    entry: float
    stop_loss: float
    take_profit: float
    atr: float
    risk_distance: float
    score: float = 0.0          # 0–100 quality score
    reasons: list = field(default_factory=list)


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd(series: pd.Series, fast: int, slow: int, signal: int):
    ema_fast = _ema(series, fast)
    ema_slow = _ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _bollinger(series: pd.Series, period: int, std_mult: float):
    mid = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    return upper, mid, lower


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all technical indicators to an OHLCV DataFrame."""
    df = df.copy()
    c = df["close"]
    h, l, v = df["high"], df["low"], df["volume"]

    df["ema_fast"] = _ema(c, config.EMA_FAST)
    df["ema_slow"] = _ema(c, config.EMA_SLOW)
    df["ema_trend"] = _ema(c, config.EMA_TREND)
    df["rsi"] = _rsi(c, config.RSI_PERIOD)
    df["macd"], df["macd_signal"], df["macd_hist"] = _macd(
        c, config.MACD_FAST, config.MACD_SLOW, config.MACD_SIGNAL
    )
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = _bollinger(c, config.BB_PERIOD, config.BB_STD)
    df["atr"] = _atr(h, l, c, config.ATR_PERIOD)
    df["vol_ma"] = v.rolling(config.VOLUME_MA_PERIOD).mean()
    df["vol_ratio"] = v / df["vol_ma"]

    return df


def _score_setup(reasons: list[str]) -> float:
    """Assign a quality score (0–100) based on how many confirmations fired."""
    weights = {
        "trend_aligned": 25,
        "rsi_bullish": 20,
        "rsi_bearish": 20,
        "macd_confirm": 20,
        "pullback": 15,
        "volume_spike": 20,
    }
    return min(100.0, sum(weights.get(r, 10) for r in reasons))


def analyze(symbol: str, df: pd.DataFrame) -> Optional[TradeSetup]:
    """
    Evaluate the latest candle for a trade setup.
    Returns a TradeSetup or None if no signal.
    """
    df = compute_indicators(df)
    if df.isnull().iloc[-1].any():
        return None

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    price = float(latest["close"])
    atr = float(latest["atr"])

    reasons_long: list[str] = []
    reasons_short: list[str] = []

    # ── 1. Trend alignment ────────────────────────────────────────────────────
    if latest["ema_fast"] > latest["ema_slow"] > latest["ema_trend"]:
        reasons_long.append("trend_aligned")
    elif latest["ema_fast"] < latest["ema_slow"] < latest["ema_trend"]:
        reasons_short.append("trend_aligned")

    # ── 2. RSI condition ─────────────────────────────────────────────────────
    rsi = float(latest["rsi"])
    if 45 <= rsi <= config.RSI_OVERBOUGHT:
        reasons_long.append("rsi_bullish")
    if config.RSI_OVERSOLD <= rsi <= 55:
        reasons_short.append("rsi_bearish")

    # ── 3. MACD histogram positive and increasing ─────────────────────────────
    hist_now = float(latest["macd_hist"])
    hist_prev = float(prev["macd_hist"])
    if hist_now > 0 and hist_now > hist_prev:
        reasons_long.append("macd_confirm")
    if hist_now < 0 and hist_now < hist_prev:
        reasons_short.append("macd_confirm")

    # ── 4. Pullback / mean-reversion entry ────────────────────────────────────
    bb_lower = float(latest["bb_lower"])
    bb_upper = float(latest["bb_upper"])
    ema_slow_val = float(latest["ema_slow"])

    long_pullback = price <= ema_slow_val * 1.005 or price <= bb_lower * 1.01
    short_pullback = price >= ema_slow_val * 0.995 or price >= bb_upper * 0.99

    if long_pullback:
        reasons_long.append("pullback")
    if short_pullback:
        reasons_short.append("pullback")

    # ── 5. Volume spike ───────────────────────────────────────────────────────
    vol_ratio = float(latest["vol_ratio"])
    if vol_ratio >= config.MIN_VOLUME_SPIKE:
        reasons_long.append("volume_spike")
        reasons_short.append("volume_spike")

    # ── Decide signal (need at least 4 out of 5 conditions) ──────────────────
    MIN_CONDITIONS = 4
    signal = Signal.NONE
    reasons: list[str] = []

    if len(reasons_long) >= MIN_CONDITIONS and len(reasons_long) >= len(reasons_short):
        signal = Signal.LONG
        reasons = reasons_long
    elif len(reasons_short) >= MIN_CONDITIONS:
        signal = Signal.SHORT
        reasons = reasons_short

    if signal == Signal.NONE:
        return None

    # ── Build stop-loss and take-profit levels ────────────────────────────────
    stop_distance = atr * config.ATR_STOP_MULTIPLIER

    if signal == Signal.LONG:
        stop_loss = price - stop_distance
        take_profit = price + stop_distance * config.RISK_REWARD_RATIO
    else:
        stop_loss = price + stop_distance
        take_profit = price - stop_distance * config.RISK_REWARD_RATIO

    return TradeSetup(
        symbol=symbol,
        signal=signal,
        entry=price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        atr=atr,
        risk_distance=stop_distance,
        score=_score_setup(reasons),
        reasons=reasons,
    )
