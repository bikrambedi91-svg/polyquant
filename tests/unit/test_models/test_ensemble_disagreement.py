"""Tests for ensemble disagreement detection."""

import pytest
from models.base import ModelOutput
from models.ensemble import EnsembleAggregator


def _make_signal(model_name: str, prob_up: float, confidence: int = 70) -> ModelOutput:
    return ModelOutput(
        asset="BTC", timeframe="1h", prob_up=prob_up,
        confidence=confidence, model_name=model_name, param_version=1,
    )


class TestDisagreementFlags:
    def test_outlier_model_flagged(self):
        """5 models at ~0.60, 1 at 0.30 → disagreement flag raised."""
        signals = [
            _make_signal("MomRegime", 0.60),
            _make_signal("FundBasis", 0.62),
            _make_signal("ChainFlow", 0.58),
            _make_signal("VolSurf", 0.61),
            _make_signal("SentComp", 0.59),
            _make_signal("TechConf", 0.30),  # Outlier
            _make_signal("CLOBSignal", 0.60),
        ]
        ens = EnsembleAggregator()
        result = ens.aggregate(signals, "1h")

        assert len(result.disagreement_flags) >= 1
        assert any("TechConf" in f for f in result.disagreement_flags)

    def test_no_disagreement_when_aligned(self):
        """All models agree → no flags."""
        signals = [
            _make_signal("MomRegime", 0.60),
            _make_signal("FundBasis", 0.62),
            _make_signal("TechConf", 0.58),
        ]
        ens = EnsembleAggregator()
        result = ens.aggregate(signals, "1h")
        assert len(result.disagreement_flags) == 0

    def test_disagreement_threshold_boundary(self):
        """Model exactly at 12% diff shouldn't trigger, >12% should."""
        # Ensemble should be near 0.60, so 0.60 + 0.13 = 0.73 should flag
        signals = [
            _make_signal("MomRegime", 0.60, 70),
            _make_signal("FundBasis", 0.60, 70),
            _make_signal("TechConf", 0.60, 70),
            _make_signal("CLOBSignal", 0.80, 70),  # ~0.20 away → should flag
        ]
        ens = EnsembleAggregator()
        result = ens.aggregate(signals, "1h")
        assert any("CLOBSignal" in f for f in result.disagreement_flags)

    def test_param_versions_tracked(self):
        """Ensemble should track which param version each model used."""
        signals = [
            ModelOutput(asset="BTC", timeframe="1h", prob_up=0.60, confidence=70,
                        model_name="MomRegime", param_version=3),
            ModelOutput(asset="BTC", timeframe="1h", prob_up=0.55, confidence=70,
                        model_name="TechConf", param_version=7),
        ]
        ens = EnsembleAggregator()
        result = ens.aggregate(signals, "1h")
        assert result.param_versions["MomRegime"] == 3
        assert result.param_versions["TechConf"] == 7
