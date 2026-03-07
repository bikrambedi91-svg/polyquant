"""Tests for learning/regime_detector.py — 5 regimes from BTC data."""

import numpy as np
import pandas as pd
import pytest

from learning.regime_detector import RegimeDetector, RegimeState


def _make_ohlcv(
    prices: list[float] | None = None,
    n: int = 30,
    start: float = 100.0,
    trend: float = 0.0,
    vol: float = 0.01,
) -> pd.DataFrame:
    """Generate synthetic OHLCV data.

    Args:
        prices: Explicit close prices (overrides other params).
        n: Number of rows.
        start: Starting price.
        trend: Per-bar trend (e.g., 0.005 for uptrend).
        vol: Noise volatility.
    """
    np.random.seed(42)
    if prices is not None:
        close = np.array(prices, dtype=float)
    else:
        returns = np.random.normal(trend, vol, n)
        close = start * np.cumprod(1 + returns)

    high = close * 1.005
    low = close * 0.995
    open_ = (close + np.roll(close, 1)) / 2
    open_[0] = close[0]
    volume = np.random.uniform(100, 1000, len(close))

    return pd.DataFrame({
        "open": open_, "high": high, "low": low,
        "close": close, "volume": volume,
    })


@pytest.fixture
def detector():
    return RegimeDetector()


class TestRegimeDetection:
    def test_crash_detects_risk_off(self, detector):
        """A sharp drop → RISK_OFF."""
        # Price drops 8% over 30 bars
        prices = [100.0 * (1 - 0.003 * i) for i in range(30)]
        df = _make_ohlcv(prices=prices)
        state = detector.detect(df)
        assert state.regime == "RISK_OFF"
        assert state.edge_threshold == 0.10  # Higher edge req

    def test_trending_up(self, detector):
        """Steady uptrend with decent movement → TRENDING."""
        # Steady 0.5% per bar uptrend with good directional movement
        prices = [100.0 * (1.005 ** i) for i in range(30)]
        df = _make_ohlcv(prices=prices)
        state = detector.detect(df)
        assert state.regime in ("TRENDING", "RISK_ON")
        # TRENDING or RISK_ON are both acceptable for steady uptrend

    def test_high_volatility(self, detector):
        """Wild swings → HIGH_VOL."""
        # Alternate +5%, -5% every bar
        prices = [100.0]
        for i in range(29):
            mult = 1.05 if i % 2 == 0 else 0.95
            prices.append(prices[-1] * mult)
        df = _make_ohlcv(prices=prices)
        state = detector.detect(df)
        assert state.regime == "HIGH_VOL"

    def test_flat_market_choppy(self, detector):
        """Flat, range-bound market → CHOPPY or RISK_ON."""
        # Very tiny random moves around 100
        prices = [100.0 + 0.05 * (i % 3 - 1) for i in range(30)]
        df = _make_ohlcv(prices=prices)
        state = detector.detect(df)
        assert state.regime in ("CHOPPY", "RISK_ON")

    def test_normal_conditions_risk_on(self, detector):
        """Moderate conditions → RISK_ON."""
        df = _make_ohlcv(n=30, start=100, trend=0.001, vol=0.005)
        state = detector.detect(df)
        assert state.regime in ("RISK_ON", "TRENDING")

    def test_insufficient_data_fallback(self, detector):
        """< lookback rows → default RISK_ON."""
        df = _make_ohlcv(n=5)
        state = detector.detect(df)
        assert state.regime == "RISK_ON"
        assert state.confidence == 0.0

    def test_none_data_fallback(self, detector):
        state = detector.detect(None)
        assert state.regime == "RISK_ON"


class TestRegimeState:
    def test_risk_off_adjustments(self, detector):
        """RISK_OFF: SL mult=0.80, TP mult=0.90."""
        prices = [100.0 * (1 - 0.003 * i) for i in range(30)]
        df = _make_ohlcv(prices=prices)
        state = detector.detect(df)
        assert state.regime == "RISK_OFF"
        assert state.sl_mult == 0.80
        assert state.tp_mult == 0.90
        assert state.kelly_mult == 0.5

    def test_high_vol_adjustments(self, detector):
        """HIGH_VOL: SL mult=1.30, TP mult=1.20."""
        prices = [100.0]
        for i in range(29):
            mult = 1.05 if i % 2 == 0 else 0.95
            prices.append(prices[-1] * mult)
        df = _make_ohlcv(prices=prices)
        state = detector.detect(df)
        assert state.regime == "HIGH_VOL"
        assert state.sl_mult == 1.30
        assert state.tp_mult == 1.20

    def test_regime_has_indicators(self, detector):
        df = _make_ohlcv(n=30)
        state = detector.detect(df)
        assert "realized_vol" in state.indicators
        assert "adx" in state.indicators

    def test_static_adjustments_lookup(self):
        adj = RegimeDetector.get_regime_adjustments("CHOPPY")
        assert adj["sl_mult"] == 0.85
        assert adj["tp_mult"] == 0.85

    def test_static_adjustments_unknown(self):
        adj = RegimeDetector.get_regime_adjustments("UNKNOWN")
        assert adj["sl_mult"] == 1.0
