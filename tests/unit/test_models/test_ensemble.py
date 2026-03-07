"""Tests for Ensemble aggregator — weighted combination of model signals."""

import pytest
from models.base import ModelOutput
from models.ensemble import EnsembleAggregator


def _make_signal(model_name: str, prob_up: float, confidence: int, asset: str = "BTC") -> ModelOutput:
    return ModelOutput(
        asset=asset, timeframe="1h", prob_up=prob_up,
        confidence=confidence, model_name=model_name, param_version=1,
    )


class TestEnsembleWeightedAverage:
    def test_hand_calculated_weighted_average(self):
        """Verify weighted average matches hand calculation for 1h timeframe.

        Default 1h weights: MomRegime=0.18, FundBasis=0.18, ChainFlow=0.12,
        VolSurf=0.14, SentComp=0.08, TechConf=0.20, CLOBSignal=0.10

        All confidence=70 → confidence_scalar = 70/70 = 1.0
        No Brier adjustment → brier_weight = 1.0
        So effective_weight = default_weight * 1.0 * 1.0 = default_weight
        """
        signals = [
            _make_signal("MomRegime", 0.60, 70),
            _make_signal("FundBasis", 0.65, 70),
            _make_signal("ChainFlow", 0.55, 70),
            _make_signal("VolSurf", 0.50, 70),
            _make_signal("SentComp", 0.70, 70),
            _make_signal("TechConf", 0.60, 70),
            _make_signal("CLOBSignal", 0.55, 70),
        ]
        ens = EnsembleAggregator()
        result = ens.aggregate(signals, "1h")

        # Hand calc: sum(prob * weight) / sum(weight)
        # = (0.60*0.18 + 0.65*0.18 + 0.55*0.12 + 0.50*0.14 + 0.70*0.08 + 0.60*0.20 + 0.55*0.10) / 1.0
        expected = (0.108 + 0.117 + 0.066 + 0.070 + 0.056 + 0.120 + 0.055) / 1.0
        assert result.prob_up == pytest.approx(expected, abs=0.01)

    def test_empty_signals(self):
        """No signals → prob=0.5, confidence=0."""
        ens = EnsembleAggregator()
        result = ens.aggregate([], "1h")
        assert result.prob_up == 0.5
        assert result.confidence == 0


class TestZeroConfidenceAutoDisable:
    def test_zero_confidence_gets_zero_weight(self):
        """Model with confidence=0 should get zero effective weight."""
        signals = [
            _make_signal("MomRegime", 0.80, 70),     # Active
            _make_signal("ChainFlow", 0.20, 0),       # confidence=0 → disabled
            _make_signal("TechConf", 0.70, 70),       # Active
        ]
        ens = EnsembleAggregator()
        result = ens.aggregate(signals, "1h")

        # ChainFlow should have 0 effective weight
        assert result.model_weights_used["ChainFlow"] == 0.0
        # Result should be between the two active models (0.70-0.80)
        assert result.prob_up > 0.60

    def test_all_zero_confidence(self):
        """All models at confidence=0 → prob=0.5, confidence=0."""
        signals = [
            _make_signal("MomRegime", 0.80, 0),
            _make_signal("TechConf", 0.70, 0),
        ]
        ens = EnsembleAggregator()
        result = ens.aggregate(signals, "1h")
        assert result.prob_up == 0.5
        assert result.confidence == 0


class TestBrierWeights:
    def test_brier_adjustment(self):
        """Brier weight should scale model influence."""
        signals = [
            _make_signal("MomRegime", 0.80, 70),
            _make_signal("TechConf", 0.40, 70),
        ]
        # MomRegime has been very accurate (brier_weight=2.0)
        # TechConf has been poor (brier_weight=0.5)
        ens = EnsembleAggregator(brier_weights={"MomRegime": 2.0, "TechConf": 0.5})
        result = ens.aggregate(signals, "1h")
        # MomRegime should dominate → prob closer to 0.80
        assert result.prob_up > 0.65


class TestConfidenceScaling:
    def test_high_confidence_gets_more_weight(self):
        """Model with confidence=100 should outweigh confidence=30 model."""
        signals = [
            _make_signal("MomRegime", 0.80, 100),
            _make_signal("TechConf", 0.30, 30),
        ]
        ens = EnsembleAggregator()
        result = ens.aggregate(signals, "1h")
        # MomRegime's confidence scalar = 100/70 = 1.43
        # TechConf's confidence scalar = 30/70 = 0.43
        # MomRegime should dominate
        assert result.prob_up > 0.60
