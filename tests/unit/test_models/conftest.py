"""Shared fixtures for model tests."""

import numpy as np
import pandas as pd
import pytest

from models.base import ModelParams


def make_ohlcv(
    n: int = 150,
    start_price: float = 60000.0,
    trend: str = "up",
    volatility: float = 0.005,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing.

    trend: "up", "down", "flat", "choppy"
    """
    rng = np.random.RandomState(seed)
    prices = [start_price]

    for _ in range(n - 1):
        if trend == "up":
            drift = 0.002
        elif trend == "down":
            drift = -0.002
        elif trend == "choppy":
            drift = rng.choice([-0.003, 0.003])
        else:
            drift = 0.0

        change = drift + rng.normal(0, volatility)
        prices.append(prices[-1] * (1 + change))

    prices = np.array(prices)
    highs = prices * (1 + rng.uniform(0.001, 0.01, n))
    lows = prices * (1 - rng.uniform(0.001, 0.01, n))
    opens = prices * (1 + rng.normal(0, 0.002, n))
    volumes = rng.uniform(500, 3000, n)

    timestamps = pd.date_range("2024-03-01", periods=n, freq="5min", tz="UTC")

    return pd.DataFrame({
        "timestamp": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": prices,
        "volume": volumes,
    })


def make_default_params(model_name: str, timeframe: str = "1h") -> ModelParams:
    """Get default params for a model from the registry defaults."""
    from models.param_registry import DEFAULT_PARAMS
    values = DEFAULT_PARAMS.get(model_name, {}).get(timeframe, {})
    return ModelParams(values=values.copy(), version=1)
