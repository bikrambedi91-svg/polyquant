"""Tests for market/pricing.py — Fee calculation, effective implied prob, edge.

CRITICAL: Hand-verified calculations from the build spec.
"""

import pytest
from market.pricing import PricingEngine


@pytest.fixture
def engine():
    return PricingEngine()


class TestTakerFee:
    def test_15m_at_50_pct(self, engine):
        """15m, price=0.50: fee = 0.0156 × 2 × 0.5 × 0.5 = 0.0078 (0.78%)."""
        fee = engine.calculate_taker_fee(0.50, "15m")
        assert fee == pytest.approx(0.0078)

    def test_15m_at_80_pct(self, engine):
        """15m, price=0.80: fee = 0.0156 × 2 × 0.8 × 0.2 = 0.004992."""
        fee = engine.calculate_taker_fee(0.80, "15m")
        assert fee == pytest.approx(0.004992)

    def test_1h_taker_fee(self, engine):
        """1h: fee = 0.0156 × 2 × 0.5 × 0.5 = 0.0078 (same curve as all)."""
        fee = engine.calculate_taker_fee(0.50, "1h")
        assert fee == pytest.approx(0.0078)

    def test_4h_taker_fee(self, engine):
        """4h: fee = 0.0156 × 2 × 0.5 × 0.5 = 0.0078."""
        fee = engine.calculate_taker_fee(0.50, "4h")
        assert fee == pytest.approx(0.0078)

    def test_5m_at_50_pct(self, engine):
        """5m, price=0.50: fee = 0.0156 × 2 × 0.5 × 0.5 = 0.0078."""
        fee = engine.calculate_taker_fee(0.50, "5m")
        assert fee == pytest.approx(0.0078)

    def test_all_timeframes_same_curve(self, engine):
        """All timeframes now use the same 1.56% max taker fee curve."""
        fee_5m = engine.calculate_taker_fee(0.50, "5m")
        fee_15m = engine.calculate_taker_fee(0.50, "15m")
        fee_1h = engine.calculate_taker_fee(0.50, "1h")
        fee_4h = engine.calculate_taker_fee(0.50, "4h")
        assert fee_5m == fee_15m == fee_1h == fee_4h

    def test_fee_at_extremes_near_zero(self, engine):
        """Fee at price near 0 or 1 should be ~0."""
        fee_low = engine.calculate_taker_fee(0.01, "15m")
        fee_high = engine.calculate_taker_fee(0.99, "15m")
        assert fee_low < 0.001
        assert fee_high < 0.001

    def test_fee_symmetric(self, engine):
        """fee(0.3) should equal fee(0.7) — symmetric around 0.5."""
        fee_30 = engine.calculate_taker_fee(0.30, "15m")
        fee_70 = engine.calculate_taker_fee(0.70, "15m")
        assert fee_30 == pytest.approx(fee_70)

    def test_unknown_timeframe_zero_fee(self, engine):
        """Unknown timeframe → 0 fee (safe default)."""
        fee = engine.calculate_taker_fee(0.50, "99m")
        assert fee == 0.0


class TestEffectiveImplied:
    def test_maker_entry_no_fee(self, engine):
        """Maker entry (default): yes=0.50, 15m, slippage=0.005 → 0.50 + 0 + 0.005 = 0.505."""
        eff = engine.effective_implied_prob(0.50, "15m", expected_slippage=0.005)
        assert eff == pytest.approx(0.505)

    def test_taker_entry_includes_fee(self, engine):
        """Taker entry: yes=0.50, 15m, slippage=0.005 → 0.50 + 0.0078 + 0.005 = 0.5128."""
        eff = engine.effective_implied_prob(0.50, "15m", expected_slippage=0.005, use_maker=False)
        assert eff == pytest.approx(0.5128)

    def test_1h_maker_entry(self, engine):
        """1h maker entry: yes=0.60, slippage=0.01 → 0.60 + 0 + 0.01 = 0.61."""
        eff = engine.effective_implied_prob(0.60, "1h", expected_slippage=0.01)
        assert eff == pytest.approx(0.61)

    def test_zero_slippage_maker(self, engine):
        """No slippage, maker → effective = price only (0% fee)."""
        eff = engine.effective_implied_prob(0.50, "15m", expected_slippage=0.0)
        assert eff == pytest.approx(0.50)


class TestEdge:
    def test_basic_edge(self, engine):
        """our_prob=0.62, effective=0.52, penalty=0 → edge=0.10."""
        edge = engine.calculate_edge(0.62, 0.52, resolution_penalty=0.0)
        assert edge == pytest.approx(0.10)

    def test_edge_with_penalty(self, engine):
        """our_prob=0.62, effective=0.52, penalty=0.015 → edge=0.085."""
        edge = engine.calculate_edge(0.62, 0.52, resolution_penalty=0.015)
        assert edge == pytest.approx(0.085)

    def test_negative_edge(self, engine):
        """Small difference with penalty → negative edge (no trade)."""
        edge = engine.calculate_edge(0.53, 0.52, resolution_penalty=0.02)
        assert edge < 0

    def test_edge_symmetric(self, engine):
        """Edge should work when our_prob < effective (BUY_NO case)."""
        edge = engine.calculate_edge(0.30, 0.52, resolution_penalty=0.0)
        assert edge == pytest.approx(0.22)


class TestExpectedValue:
    def test_buy_yes_positive_ev(self, engine):
        """BUY_YES: EV = our_prob - entry - fee."""
        ev = engine.expected_value(0.70, 0.55, "BUY_YES", "1h")
        # fee = 0.0156 * 2 * 0.55 * 0.45 = 0.007722
        # EV = 0.70 - 0.55 - 0.007722 = 0.142278
        assert ev == pytest.approx(0.1423, abs=0.001)

    def test_buy_no_positive_ev(self, engine):
        """BUY_NO: EV = (1-our_prob) - (1-entry) - fee."""
        ev = engine.expected_value(0.30, 0.55, "BUY_NO", "1h")
        # fee = 0.0156 * 2 * 0.55 * 0.45 = 0.007722
        # EV = 0.70 - 0.45 - 0.007722 = 0.242278
        assert ev == pytest.approx(0.2423, abs=0.001)

    def test_buy_yes_with_fee(self, engine):
        """BUY_YES on 15m: EV includes taker fee (same curve as all timeframes)."""
        ev = engine.expected_value(0.70, 0.50, "BUY_YES", "15m")
        # fee = 0.0156 * 2 * 0.5 * 0.5 = 0.0078
        # EV = 0.70 - 0.50 - 0.0078 = 0.1922
        assert ev == pytest.approx(0.1922, abs=0.001)

    def test_negative_ev(self, engine):
        """Small edge after fee → small positive EV."""
        ev = engine.expected_value(0.52, 0.50, "BUY_YES", "15m")
        # fee = 0.0078
        # EV = 0.52 - 0.50 - 0.0078 = 0.0122
        assert ev == pytest.approx(0.0122, abs=0.001)

    def test_deeply_negative_ev(self, engine):
        """Wrong direction → deeply negative EV."""
        ev = engine.expected_value(0.40, 0.55, "BUY_YES", "15m")
        # fee = 0.0156 * 2 * 0.55 * 0.45 = 0.007722
        # EV = 0.40 - 0.55 - 0.007722 = -0.157722
        assert ev < -0.15
