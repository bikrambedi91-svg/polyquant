"""Tests for learning/sl_tp_learner.py — percentage-based MAE/MFE simulation, clamping, learned provider."""

import pytest
from learning.sl_tp_learner import (
    SLTPLearner,
    LearnedSLTPProvider,
    TradeData,
    SLTPResult,
)


def _trade(
    entry_price=0.55, exit_price=0.70, action="BUY_YES",
    our_prob=0.65, mae=0.05, mfe=0.15, pnl_usd=15.0,
    size_usd=100.0, book_depth=200.0, result="WON",
) -> TradeData:
    return TradeData(
        entry_price=entry_price,
        exit_price=exit_price,
        action=action,
        our_prob=our_prob,
        max_adverse_excursion=mae,
        max_favorable_excursion=mfe,
        pnl_usd=pnl_usd,
        size_usd=size_usd,
        book_depth_at_exit=book_depth,
        result=result,
    )


class TestSLTPOptimization:
    def test_insufficient_data_returns_none(self):
        """< 30 trades → returns None (use defaults)."""
        learner = SLTPLearner()
        trades = [_trade() for _ in range(20)]
        result = learner.optimize(trades, "BTC", "1h", "RISK_ON")
        assert result is None

    def test_converges_with_known_mae(self):
        """50 trades with small MAE → SL should converge to reasonable %."""
        learner = SLTPLearner()
        # MAE=0.03 on entry=0.55 → mae_pct=0.03/0.55≈5.5%
        trades = [
            _trade(mae=0.03, mfe=0.08, pnl_usd=10.0) for _ in range(50)
        ]
        result = learner.optimize(
            trades, "BTC", "1h", "RISK_ON",
            current_sl_pct=0.05, current_tp_pct=0.05,
        )
        assert result is not None
        assert result.trade_count == 50
        assert 0.02 <= result.optimal_sl_pct <= 0.15

    def test_max_sl_change_capped(self):
        """SL change > 0.03 per cycle → clamped."""
        learner = SLTPLearner()
        # Very small MAE → optimizer wants low SL %
        trades = [
            _trade(mae=0.005, mfe=0.10, pnl_usd=8.0) for _ in range(40)
        ]
        result = learner.optimize(
            trades, "BTC", "1h", "RISK_ON",
            current_sl_pct=0.10,
        )
        assert result is not None
        if result.was_clamped:
            assert abs(result.optimal_sl_pct - 0.10) <= 0.03 + 0.001

    def test_max_tp_change_capped(self):
        """TP change > 0.03 per cycle → clamped."""
        learner = SLTPLearner()
        # Large MFE → optimizer wants high TP %
        trades = [
            _trade(mae=0.02, mfe=0.20, pnl_usd=15.0) for _ in range(40)
        ]
        result = learner.optimize(
            trades, "BTC", "1h", "RISK_ON",
            current_tp_pct=0.05,
        )
        assert result is not None
        if result.was_clamped:
            assert abs(result.optimal_tp_pct - 0.05) <= 0.03 + 0.001

    def test_stores_learned_levels(self):
        """After optimization, get_learned_levels returns sl_pct/tp_pct."""
        learner = SLTPLearner()
        trades = [_trade() for _ in range(35)]
        result = learner.optimize(trades, "BTC", "1h", "RISK_ON")
        assert result is not None
        assert learner.has_learned("BTC", "1h", "RISK_ON")
        levels = learner.get_learned_levels("BTC", "1h", "RISK_ON")
        assert levels is not None
        assert "sl_pct" in levels
        assert "tp_pct" in levels

    def test_not_learned_returns_none(self):
        learner = SLTPLearner()
        assert learner.has_learned("BTC", "1h", "RISK_ON") is False
        assert learner.get_learned_levels("BTC", "1h", "RISK_ON") is None

    def test_mixed_trades_pnl_optimized(self):
        """Mix of winners and losers — optimizer finds productive SL %."""
        learner = SLTPLearner()
        trades = []
        # 30 winners with small MAE, big MFE
        for i in range(30):
            trades.append(_trade(mae=0.02, mfe=0.08, pnl_usd=10.0, result="WON"))
        # 20 losers with big MAE
        for i in range(20):
            trades.append(_trade(mae=0.12, mfe=0.01, pnl_usd=-12.0, result="LOST"))

        result = learner.optimize(
            trades, "BTC", "1h", "RISK_ON",
            current_sl_pct=0.05, current_tp_pct=0.05,
        )
        assert result is not None
        assert result.simulated_pnl != 0

    def test_percentage_conversion_in_simulation(self):
        """MAE/MFE are converted to % of cost basis before comparison."""
        learner = SLTPLearner()
        # entry=0.50, mae=0.025 → mae_pct = 0.025/0.50 = 5%
        # SL at 4% should trigger, SL at 6% should not
        trades = [_trade(entry_price=0.50, mae=0.025, mfe=0.05, pnl_usd=-5.0, result="LOST")
                  for _ in range(35)]

        # SL at 4% → triggers (5% >= 4%), simulated loss = -0.04*100 = -$4 per trade
        pnl_4pct = learner._simulate_sl(trades, 0.04)
        # SL at 6% → does NOT trigger (5% < 6%), actual loss = -$5 per trade
        pnl_6pct = learner._simulate_sl(trades, 0.06)

        # With 4% SL: loss per trade = -0.04*100 = -$4, total = -$140
        assert pnl_4pct == pytest.approx(-4.0 * 35, abs=1.0)
        # With 6% SL: uses actual pnl = -$5, total = -$175
        assert pnl_6pct == pytest.approx(-5.0 * 35, abs=1.0)
        # 4% SL is better than 6% (less loss)
        assert pnl_4pct > pnl_6pct


class TestLearnedSLTPProvider:
    def test_uses_learned_when_available(self):
        learner = SLTPLearner()
        learner._learned[("BTC", "1h", "RISK_ON")] = {"sl_pct": 0.08, "tp_pct": 0.12}

        provider = LearnedSLTPProvider(learner)
        levels = provider.get_levels("BTC", "1h", "RISK_ON", 0.50, 0.65, "BUY_YES", confidence=65)
        assert levels.was_learned is True
        # TP = 0.50 * (1 + 0.12) = 0.56
        assert levels.tp_price == pytest.approx(0.56, abs=0.01)
        # SL = 0.50 * (1 - 0.08) = 0.46
        assert levels.sl_price == pytest.approx(0.46, abs=0.01)

    def test_falls_back_to_default(self):
        learner = SLTPLearner()
        provider = LearnedSLTPProvider(learner)
        levels = provider.get_levels("BTC", "1h", "RISK_ON", 0.50, 0.65, "BUY_YES", confidence=65)
        assert levels.was_learned is False
        # Default SL 10% → sl_price = 0.50 * 0.90 = 0.45
        assert levels.sl_price == pytest.approx(0.45, abs=0.01)
        # Default TP 20% (flat) → tp_price = 0.50 * 1.20 = 0.60
        assert levels.tp_price == pytest.approx(0.60, abs=0.01)

    def test_regime_adjustments_applied(self):
        """RISK_OFF tightens SL 20%, TP 10%."""
        learner = SLTPLearner()
        learner._learned[("BTC", "1h", "RISK_OFF")] = {"sl_pct": 0.10, "tp_pct": 0.10}

        provider = LearnedSLTPProvider(learner)
        levels = provider.get_levels("BTC", "1h", "RISK_OFF", 0.50, 0.65, "BUY_YES", confidence=65)
        # SL = 0.50 * (1 - 0.10*0.80) = 0.50 * 0.92 = 0.46
        assert levels.sl_price == pytest.approx(0.46, abs=0.01)
        # TP = 0.50 * (1 + 0.10*0.90) = 0.50 * 1.09 = 0.545
        assert levels.tp_price == pytest.approx(0.545, abs=0.01)

    def test_buy_no_direction(self):
        learner = SLTPLearner()
        learner._learned[("BTC", "1h", "RISK_ON")] = {"sl_pct": 0.08, "tp_pct": 0.10}

        provider = LearnedSLTPProvider(learner)
        levels = provider.get_levels("BTC", "1h", "RISK_ON", 0.50, 0.35, "BUY_NO", confidence=65)
        # no_cost = 0.50
        # TP = 0.50 - 0.10*0.50 = 0.50 - 0.05 = 0.45
        assert levels.tp_price == pytest.approx(0.45, abs=0.01)
        # SL = 0.50 + 0.08*0.50 = 0.50 + 0.04 = 0.54
        assert levels.sl_price == pytest.approx(0.54, abs=0.01)

    def test_confidence_flat_tp_for_default(self):
        """When no learned levels, TP is flat 20% regardless of confidence."""
        learner = SLTPLearner()
        provider = LearnedSLTPProvider(learner)

        low = provider.get_levels("BTC", "1h", "RISK_ON", 0.50, 0.65, "BUY_YES", confidence=60)
        high = provider.get_levels("BTC", "1h", "RISK_ON", 0.50, 0.65, "BUY_YES", confidence=90)
        # Flat TP → same for all confidence levels
        assert high.tp_price == pytest.approx(low.tp_price, abs=0.001)
        # SL same for both (10% default)
        assert low.sl_price == pytest.approx(high.sl_price, abs=0.001)
