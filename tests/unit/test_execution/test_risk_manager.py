"""Tests for execution/risk_manager.py — fixed sizing, limits, daily halt, correlation."""

import pytest
from unittest.mock import MagicMock
from execution.risk_manager import RiskManager, MAX_OPEN_POSITIONS


@pytest.fixture
def settings():
    s = MagicMock()
    s.BANKROLL_USDC = 10000.0
    s.MAX_SINGLE_POSITION_PCT = 0.12
    s.MAX_PER_ASSET_PCT = 0.25
    s.MAX_TOTAL_EXPOSURE_PCT = 0.60
    s.DAILY_LOSS_HALT_USD = 100.0
    s.POSITION_SIZE_USD = 20.0
    s.MIN_POSITION_USD = 5.0
    return s


@pytest.fixture
def rm(settings):
    return RiskManager(settings)


class TestFixedSizing:
    def test_returns_fixed_size(self, rm):
        """get_position_size() returns fixed $20."""
        assert rm.get_position_size() == 20.0

    def test_size_matches_settings(self, settings):
        """Position size comes from settings."""
        settings.POSITION_SIZE_USD = 50.0
        rm = RiskManager(settings)
        assert rm.get_position_size() == 50.0


class TestCheckLimits:
    def test_passes_clean(self, rm):
        """No positions, normal size → passes."""
        ok, reason = rm.check_limits("BTC", 20.0, [])
        assert ok is True
        assert reason == ""

    def test_daily_loss_halt_usd(self, rm):
        """Daily P&L -$100 → halt (fixed USD threshold)."""
        ok, reason = rm.check_limits("BTC", 20.0, [], daily_pnl=-100.0)
        assert ok is False
        assert "daily loss halt" in reason.lower()

    def test_daily_loss_below_threshold(self, rm):
        """Daily P&L -$99 → still OK."""
        ok, reason = rm.check_limits("BTC", 20.0, [], daily_pnl=-99.0)
        assert ok is True

    def test_max_open_positions(self, rm):
        """3 active positions → blocked (max 3)."""
        positions = [
            {"asset": "BTC", "size_usd": 20.0, "status": "ACTIVE"},
            {"asset": "ETH", "size_usd": 20.0, "status": "ACTIVE"},
            {"asset": "SOL", "size_usd": 20.0, "status": "ACTIVE"},
        ]
        ok, reason = rm.check_limits("XRP", 20.0, positions)
        assert ok is False
        assert "open positions" in reason.lower()

    def test_single_position_limit(self, rm):
        """$1500 > 12% of $10k → rejected."""
        ok, reason = rm.check_limits("BTC", 1500.0, [])
        assert ok is False
        assert "single" in reason.lower()

    def test_per_asset_limit(self, rm):
        """Existing $2000 BTC + $600 new = $2600 > $2500 limit."""
        positions = [{"asset": "BTC", "size_usd": 2000.0, "status": "ACTIVE"}]
        ok, reason = rm.check_limits("BTC", 600.0, positions)
        assert ok is False
        assert "asset" in reason.lower()

    def test_total_exposure_limit(self, rm):
        """Total $5500 + $600 = $6100 > $6000 limit (60% of $10k)."""
        # Only 2 active to avoid hitting max-3 first
        positions = [
            {"asset": "BTC", "size_usd": 3000.0, "status": "ACTIVE"},
            {"asset": "ETH", "size_usd": 2500.0, "status": "ACTIVE"},
        ]
        ok, reason = rm.check_limits("XRP", 600.0, positions)
        assert ok is False
        assert "total" in reason.lower()

    def test_below_minimum_rejected(self, rm):
        """$4 < $5 minimum → rejected."""
        ok, reason = rm.check_limits("BTC", 4.0, [])
        assert ok is False
        assert "minimum" in reason.lower()

    def test_closed_positions_not_counted(self, rm):
        """CLOSED positions should not count toward limits."""
        positions = [
            {"asset": "BTC", "size_usd": 2400.0, "status": "CLOSED"},
        ]
        ok, reason = rm.check_limits("BTC", 20.0, positions)
        assert ok is True

    def test_directional_concentration_limit(self, rm):
        """Net directional > 40% of bankroll → blocked."""
        positions = [
            {"asset": "BTC", "size_usd": 2000.0, "status": "ACTIVE", "action": "BUY_YES", "timeframe": "1h"},
            {"asset": "ETH", "size_usd": 2000.0, "status": "ACTIVE", "action": "BUY_YES", "timeframe": "1h"},
        ]
        # Adding another $1000 BUY_YES → net long $5000 > $4000 max (40% of $10k)
        ok, reason = rm.check_limits("SOL", 1000.0, positions, action="BUY_YES", timeframe="1h")
        assert ok is False
        assert "directional" in reason.lower()

    def test_same_direction_per_tf_limit(self):
        """Max 3 same direction per timeframe — test with higher max_open to isolate."""
        s = MagicMock()
        s.BANKROLL_USDC = 10000.0
        s.MAX_SINGLE_POSITION_PCT = 0.12
        s.MAX_PER_ASSET_PCT = 0.25
        s.MAX_TOTAL_EXPOSURE_PCT = 0.60
        s.DAILY_LOSS_HALT_USD = 100.0
        s.POSITION_SIZE_USD = 20.0
        s.MIN_POSITION_USD = 5.0
        rm = RiskManager(s)
        # Use 3 existing ACTIVE + 1 CLOSED to have 3 same-direction without hitting max-open=3
        # Actually max-open check fires first with 3 active. We need to test direction limit
        # by temporarily raising MAX_OPEN via monkeypatch or by having mixed statuses.
        # Workaround: 2 active same-direction + 1 closed, and MAX_SAME_DIRECTION_PER_TF=3
        # means we need 3 active same-direction. But max-open=3 blocks first.
        # Best approach: test the direction check directly with fewer positions.
        import execution.risk_manager as rm_mod
        old_max = rm_mod.MAX_OPEN_POSITIONS
        rm_mod.MAX_OPEN_POSITIONS = 10  # Temporarily raise limit
        try:
            positions = [
                {"asset": "BTC", "size_usd": 20.0, "status": "ACTIVE", "action": "BUY_YES", "timeframe": "1h"},
                {"asset": "ETH", "size_usd": 20.0, "status": "ACTIVE", "action": "BUY_YES", "timeframe": "1h"},
                {"asset": "SOL", "size_usd": 20.0, "status": "ACTIVE", "action": "BUY_YES", "timeframe": "1h"},
            ]
            ok, reason = rm.check_limits("XRP", 20.0, positions, action="BUY_YES", timeframe="1h")
            assert ok is False
            assert "already 3" in reason.lower()
        finally:
            rm_mod.MAX_OPEN_POSITIONS = old_max


class TestDetectCorrelation:
    def test_same_asset_same_tf(self, rm):
        a = {"asset": "BTC", "timeframe": "5m"}
        b = {"asset": "BTC", "timeframe": "5m"}
        assert rm.detect_correlation(a, b) == 1.0

    def test_same_asset_diff_tf(self, rm):
        a = {"asset": "BTC", "timeframe": "5m"}
        b = {"asset": "BTC", "timeframe": "1h"}
        assert rm.detect_correlation(a, b) == 0.7

    def test_different_assets(self, rm):
        a = {"asset": "BTC", "timeframe": "5m"}
        b = {"asset": "ETH", "timeframe": "5m"}
        assert rm.detect_correlation(a, b) == 0.3
