"""Tests for market/resolution.py — Resolution risk scoring."""

import pytest
from market.scanner import CryptoMarket
from market.resolution import ResolutionAnalyzer, ResolutionRisk
from datetime import datetime, timezone, timedelta


@pytest.fixture
def analyzer():
    return ResolutionAnalyzer()


def _make_market(timeframe: str, market_type: str = "up_down") -> CryptoMarket:
    """Create a minimal CryptoMarket for testing."""
    return CryptoMarket(
        title="Test market",
        url="",
        token_id_yes="YES_1",
        token_id_no="NO_1",
        asset="BTC",
        market_type=market_type,
        timeframe=timeframe,
        volume=100000,
        end_datetime=datetime.now(timezone.utc) + timedelta(hours=1),
    )


class TestResolutionRisk:
    def test_5m_up_down_low_risk(self, analyzer):
        """5m up/down → LOW, 0% penalty."""
        risk = analyzer.assess_risk(_make_market("5m", "up_down"))
        assert risk.level == "LOW"
        assert risk.penalty == 0.0

    def test_15m_up_down_low_risk(self, analyzer):
        risk = analyzer.assess_risk(_make_market("15m", "up_down"))
        assert risk.level == "LOW"
        assert risk.penalty == 0.0

    def test_1h_up_down_low_risk(self, analyzer):
        risk = analyzer.assess_risk(_make_market("1h", "up_down"))
        assert risk.level == "LOW"
        assert risk.penalty == 0.0

    def test_4h_up_down_low_risk(self, analyzer):
        risk = analyzer.assess_risk(_make_market("4h", "up_down"))
        assert risk.level == "LOW"
        assert risk.penalty == 0.0

    def test_daily_price_target_medium(self, analyzer):
        """Daily price_target → MEDIUM, 1.5% penalty."""
        risk = analyzer.assess_risk(_make_market("daily", "price_target"))
        assert risk.level == "MEDIUM"
        assert risk.penalty == 0.015

    def test_weekly_up_down_medium(self, analyzer):
        risk = analyzer.assess_risk(_make_market("weekly", "up_down"))
        assert risk.level == "MEDIUM"
        assert risk.penalty == 0.015

    def test_monthly_medium_high(self, analyzer):
        """Monthly → MEDIUM_HIGH, 2% penalty."""
        risk = analyzer.assess_risk(_make_market("monthly", "up_down"))
        assert risk.level == "MEDIUM_HIGH"
        assert risk.penalty == 0.02

    def test_unknown_type_high(self, analyzer):
        """Unknown timeframe/type combo → HIGH, 3% penalty."""
        risk = analyzer.assess_risk(_make_market("yearly", "other"))
        assert risk.level == "HIGH"
        assert risk.penalty == 0.03

    def test_risk_has_reason(self, analyzer):
        """All risk assessments include a reason string."""
        risk = analyzer.assess_risk(_make_market("5m"))
        assert len(risk.reason) > 0
