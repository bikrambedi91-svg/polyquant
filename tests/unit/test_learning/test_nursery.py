"""Tests for learning/strategy_nursery.py — Shadow mode + evaluation."""

import pytest
from learning.strategy_nursery import StrategyNursery, NurseryEntry, ShadowSignal


@pytest.fixture
def nursery():
    return StrategyNursery()


class TestAdmission:
    def test_admit_entry(self, nursery):
        entry = nursery.admit("MomRegime", "1h", 2, {"adx_period": 12})
        assert entry.model_name == "MomRegime"
        assert entry.status == "SHADOW"
        assert entry.param_version == 2

    def test_shadow_entries_listed(self, nursery):
        nursery.admit("MomRegime", "1h", 2, {"adx_period": 12})
        nursery.admit("TechConf", "1h", 3, {"rsi_period": 10})
        assert len(nursery.get_shadow_entries()) == 2


class TestSignalRecording:
    def test_record_signal(self, nursery):
        nursery.admit("MomRegime", "1h", 2, {})
        nursery.record_signal("MomRegime", "1h", 2, prob_up=0.65, confidence=70)
        entry = nursery.get_entry("MomRegime", "1h", 2)
        assert len(entry.signals) == 1
        assert entry.signals[0].prob_up == 0.65

    def test_record_multiple_signals(self, nursery):
        nursery.admit("MomRegime", "1h", 2, {})
        for i in range(5):
            nursery.record_signal("MomRegime", "1h", 2, prob_up=0.60 + i * 0.02, confidence=65)
        entry = nursery.get_entry("MomRegime", "1h", 2)
        assert len(entry.signals) == 5

    def test_resolve_signals(self, nursery):
        nursery.admit("MomRegime", "1h", 2, {})
        nursery.record_signal("MomRegime", "1h", 2, prob_up=0.65, confidence=70)
        nursery.record_signal("MomRegime", "1h", 2, prob_up=0.60, confidence=65)

        nursery.resolve_signals("MomRegime", "1h", actual_outcome=1.0)

        entry = nursery.get_entry("MomRegime", "1h", 2)
        assert all(s.actual_outcome == 1.0 for s in entry.signals)
        assert entry.trade_count == 2


class TestEvaluation:
    def test_pending_insufficient_signals(self, nursery):
        """< 30 resolved signals → PENDING."""
        nursery.admit("MomRegime", "1h", 2, {})
        for i in range(10):
            nursery.record_signal("MomRegime", "1h", 2, prob_up=0.65, confidence=70)
        nursery.resolve_signals("MomRegime", "1h", 1.0)

        result = nursery.evaluate("MomRegime", "1h", 2, active_brier=0.25)
        assert result == "PENDING"

    def test_promoted_better_than_active(self, nursery):
        """Shadow Brier < active Brier → PROMOTED."""
        nursery.admit("MomRegime", "1h", 2, {})

        # 30 signals, all correctly predicting UP (prob=0.80, outcome=1.0)
        for i in range(30):
            nursery.record_signal("MomRegime", "1h", 2, prob_up=0.80, confidence=75)
        nursery.resolve_signals("MomRegime", "1h", 1.0)

        # Shadow Brier = (0.80 - 1.0)^2 = 0.04
        # Active Brier = 0.25 → shadow is better
        result = nursery.evaluate("MomRegime", "1h", 2, active_brier=0.25)
        assert result == "PROMOTED"
        entry = nursery.get_entry("MomRegime", "1h", 2)
        assert entry.status == "PROMOTED"

    def test_discarded_worse_than_active(self, nursery):
        """Shadow Brier > active Brier → DISCARDED."""
        nursery.admit("MomRegime", "1h", 2, {})

        # 30 signals, poorly predicting (prob=0.80, outcome=0.0)
        for i in range(30):
            nursery.record_signal("MomRegime", "1h", 2, prob_up=0.80, confidence=75)
        nursery.resolve_signals("MomRegime", "1h", 0.0)

        # Shadow Brier = (0.80 - 0.0)^2 = 0.64
        # Active Brier = 0.25 → shadow is worse
        result = nursery.evaluate("MomRegime", "1h", 2, active_brier=0.25)
        assert result == "DISCARDED"
        entry = nursery.get_entry("MomRegime", "1h", 2)
        assert entry.status == "DISCARDED"

    def test_nonexistent_entry_pending(self, nursery):
        result = nursery.evaluate("FakeModel", "1h", 99, active_brier=0.25)
        assert result == "PENDING"


class TestNurseryEntry:
    def test_brier_score_calculation(self):
        entry = NurseryEntry(
            model_name="MomRegime", timeframe="1h",
            param_version=2, params={},
        )
        # Add resolved signals
        s1 = ShadowSignal(model_name="MomRegime", timeframe="1h", param_version=2,
                          prob_up=0.80, confidence=70, actual_outcome=1.0)
        s2 = ShadowSignal(model_name="MomRegime", timeframe="1h", param_version=2,
                          prob_up=0.60, confidence=70, actual_outcome=0.0)
        entry.signals = [s1, s2]

        # Brier: ((0.80-1)^2 + (0.60-0)^2) / 2 = (0.04 + 0.36) / 2 = 0.20
        assert entry.brier_score == pytest.approx(0.20)

    def test_brier_score_none_when_unresolved(self):
        entry = NurseryEntry(
            model_name="MomRegime", timeframe="1h",
            param_version=2, params={},
        )
        assert entry.brier_score is None

    def test_trade_count(self):
        entry = NurseryEntry(
            model_name="MomRegime", timeframe="1h",
            param_version=2, params={},
        )
        s1 = ShadowSignal(model_name="MomRegime", timeframe="1h", param_version=2,
                          prob_up=0.80, confidence=70, actual_outcome=1.0)
        s2 = ShadowSignal(model_name="MomRegime", timeframe="1h", param_version=2,
                          prob_up=0.60, confidence=70, actual_outcome=-1.0)  # unresolved
        entry.signals = [s1, s2]
        assert entry.trade_count == 1  # Only resolved ones
