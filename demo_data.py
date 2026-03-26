"""
Synthetic market data generator for demo/offline mode.
Produces realistic OHLCV data with trending + mean-reverting phases.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta


def generate_ohlcv(symbol: str, n_candles: int = 300, seed: int = None) -> pd.DataFrame:
    """Generate realistic synthetic OHLCV data with trend phases."""
    rng = np.random.default_rng(seed or hash(symbol) % (2**32))

    # Starting prices per symbol
    base_prices = {
        "BTC/USDT": 65000.0,
        "ETH/USDT": 3200.0,
        "SOL/USDT": 145.0,
        "BNB/USDT": 580.0,
    }
    price = base_prices.get(symbol, 1000.0)

    closes = [price]
    phase_len = rng.integers(20, 50)
    phase_drift = rng.choice([-1, 1]) * rng.uniform(0.0002, 0.0008)
    phase_counter = 0

    for _ in range(n_candles - 1):
        # Occasionally switch trend phase
        phase_counter += 1
        if phase_counter >= phase_len:
            phase_len = rng.integers(20, 50)
            phase_drift = rng.choice([-1, 1]) * rng.uniform(0.0002, 0.0008)
            phase_counter = 0

        # Geometric Brownian Motion with drift
        volatility = 0.012
        shock = rng.normal(phase_drift, volatility)
        new_price = closes[-1] * (1 + shock)
        closes.append(max(new_price, 1.0))

    closes = np.array(closes)

    # Build OHLCV from close prices
    highs = closes * (1 + np.abs(rng.normal(0, 0.004, n_candles)))
    lows = closes * (1 - np.abs(rng.normal(0, 0.004, n_candles)))
    opens = np.roll(closes, 1)
    opens[0] = closes[0]

    base_volume = {"BTC/USDT": 2000, "ETH/USDT": 15000, "SOL/USDT": 80000, "BNB/USDT": 5000}
    avg_vol = base_volume.get(symbol, 5000)
    volumes = rng.lognormal(mean=np.log(avg_vol), sigma=0.6, size=n_candles)
    # Add occasional volume spikes (simulate news/breakouts)
    spike_idx = rng.choice(n_candles, size=n_candles // 15, replace=False)
    volumes[spike_idx] *= rng.uniform(2.0, 4.0, len(spike_idx))

    now = datetime.utcnow()
    timestamps = [now - timedelta(hours=(n_candles - i)) for i in range(n_candles)]

    df = pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    }, index=pd.DatetimeIndex(timestamps))

    return df
