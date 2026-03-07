"""Tests for learning/model_evolver.py — WARNING/CRITICAL/RETIRED pipeline."""

import pytest
from learning.model_evolver import ModelEvolver, ModelHealth


@pytest.fixture
def evolver():
    return ModelEvolver()


class TestEvaluateCycle:
    def test_healthy_model_stays_active(self, evolver):
        """Brier < 0.28 → ACTIVE, weight=1.0."""
        actions = evolver.evaluate_cycle({"MomRegime": 0.20})
        health = evolver.get_health("MomRegime")
        assert health.status == "ACTIVE"
        assert health.current_weight_mult == 1.0
        # No warning/critical actions
        assert all(a.action in ("recovered",) or a.model_name != "MomRegime" for a in actions)

    def test_brier_warning(self, evolver):
        """Brier=0.32 > 0.28 → WARNING, weight reduced to 0.70."""
        actions = evolver.evaluate_cycle({"MomRegime": 0.32})
        health = evolver.get_health("MomRegime")
        assert health.status == "WARNING"
        assert health.current_weight_mult == pytest.approx(0.70)
        assert any(a.action == "warning" and a.model_name == "MomRegime" for a in actions)

    def test_brier_critical(self, evolver):
        """Brier=0.38 > 0.35 → CRITICAL, weight near-zero."""
        actions = evolver.evaluate_cycle({"MomRegime": 0.38})
        health = evolver.get_health("MomRegime")
        assert health.status == "CRITICAL"
        assert health.current_weight_mult == pytest.approx(0.05)
        assert health.consecutive_critical == 1

    def test_two_critical_cycles_retires(self, evolver):
        """2 consecutive CRITICAL → RETIRED."""
        evolver.evaluate_cycle({"MomRegime": 0.38})
        assert evolver.get_health("MomRegime").status == "CRITICAL"

        evolver.evaluate_cycle({"MomRegime": 0.40})
        assert evolver.get_health("MomRegime").status == "RETIRED"
        assert evolver.get_health("MomRegime").current_weight_mult == 0.0

    def test_min_active_blocks_retirement(self, evolver):
        """Can't retire if it would drop below 4 active models."""
        # Retire 3 models (7-3=4, the minimum)
        for model in ["ChainFlow", "SentComp", "VolSurf"]:
            evolver.evaluate_cycle({model: 0.38})
            evolver.evaluate_cycle({model: 0.40})

        assert evolver.active_count == 4

        # Try to retire a 4th — should be blocked
        evolver.evaluate_cycle({"FundBasis": 0.38})
        evolver.evaluate_cycle({"FundBasis": 0.40})
        assert evolver.get_health("FundBasis").status == "CRITICAL"  # NOT retired
        assert evolver.active_count == 4

    def test_recovery_from_warning(self, evolver):
        """Good Brier after WARNING → back to ACTIVE."""
        evolver.evaluate_cycle({"MomRegime": 0.32})
        assert evolver.get_health("MomRegime").status == "WARNING"

        actions = evolver.evaluate_cycle({"MomRegime": 0.20})
        assert evolver.get_health("MomRegime").status == "ACTIVE"
        assert any(a.action == "recovered" and a.model_name == "MomRegime" for a in actions)

    def test_recovery_from_critical(self, evolver):
        """Good Brier after CRITICAL → back to ACTIVE, counter resets."""
        evolver.evaluate_cycle({"MomRegime": 0.38})
        assert evolver.get_health("MomRegime").consecutive_critical == 1

        evolver.evaluate_cycle({"MomRegime": 0.20})
        health = evolver.get_health("MomRegime")
        assert health.status == "ACTIVE"
        assert health.consecutive_critical == 0

    def test_max_one_mutation_per_cycle(self, evolver):
        """Only 1 model flagged for mutation even if multiple are WARNING."""
        actions = evolver.evaluate_cycle({
            "MomRegime": 0.30,
            "TechConf": 0.31,
            "FundBasis": 0.32,
        })
        warning_mutations = [a for a in actions if a.action == "warning"]
        assert len(warning_mutations) == 1  # Only 1 gets the mutation flag

    def test_already_retired_skipped(self, evolver):
        """Retired models are not re-evaluated."""
        evolver.evaluate_cycle({"MomRegime": 0.38})
        evolver.evaluate_cycle({"MomRegime": 0.40})
        assert evolver.get_health("MomRegime").status == "RETIRED"

        # Evaluate again — should not change
        actions = evolver.evaluate_cycle({"MomRegime": 0.20})
        assert evolver.get_health("MomRegime").status == "RETIRED"


class TestEffectiveWeights:
    def test_default_weights_unchanged(self, evolver):
        """All healthy → effective weights match defaults (after normalization)."""
        weights = evolver.get_effective_weights("1h")
        assert "MomRegime" in weights
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_warning_reduces_weight(self, evolver):
        """WARNING model gets 70% of default weight."""
        evolver.evaluate_cycle({"MomRegime": 0.32})
        weights = evolver.get_effective_weights("1h")
        # MomRegime should have lower relative weight
        # Default 1h MomRegime = 0.18, with 0.70 mult = 0.126
        # Others are full weight, so MomRegime fraction should be lower
        assert weights["MomRegime"] < 0.18  # Less than default (before normalization)

    def test_retired_gets_zero_weight(self, evolver):
        """RETIRED model gets 0 weight."""
        evolver.evaluate_cycle({"MomRegime": 0.38})
        evolver.evaluate_cycle({"MomRegime": 0.40})
        weights = evolver.get_effective_weights("1h")
        assert weights["MomRegime"] == pytest.approx(0.0, abs=0.001)


class TestHelpers:
    def test_can_retire(self, evolver):
        assert evolver.can_retire() is True  # 7 active > 4 min

    def test_active_count(self, evolver):
        assert evolver.active_count == 7

    def test_force_status(self, evolver):
        evolver.force_status("MomRegime", "RETIRED")
        assert evolver.get_health("MomRegime").status == "RETIRED"
        assert evolver.active_count == 6

    def test_get_all_health(self, evolver):
        health = evolver.get_all_health()
        assert len(health) == 7
