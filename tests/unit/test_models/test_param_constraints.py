"""Tests for parameter constraint validation — cross-field and range checks."""

import pytest
from models.param_registry import validate_params, ParamRegistry
from models.base import ModelParams


class TestValidateParams:
    def test_valid_mom_regime(self):
        ok, reason = validate_params("MomRegime", {
            "adx_period": 14, "ema_fast": 20, "ema_slow": 50,
            "adx_threshold": 25, "lookback": 100,
        })
        assert ok is True
        assert reason == ""

    def test_ema_fast_gt_ema_slow_rejected(self):
        """ema_fast > ema_slow must be rejected."""
        ok, reason = validate_params("MomRegime", {
            "adx_period": 14, "ema_fast": 25, "ema_slow": 20,
            "adx_threshold": 25, "lookback": 100,
        })
        assert ok is False
        assert "ema_fast" in reason
        assert "ema_slow" in reason

    def test_ema_fast_equals_ema_slow_rejected(self):
        """ema_fast == ema_slow must be rejected (not strictly less)."""
        ok, reason = validate_params("MomRegime", {
            "adx_period": 14, "ema_fast": 30, "ema_slow": 30,
            "adx_threshold": 25, "lookback": 100,
        })
        assert ok is False

    def test_rsi_bear_gt_rsi_bull_rejected(self):
        """rsi_bear == rsi_bull must be rejected (not strictly less)."""
        ok, reason = validate_params("TechConf", {
            "rsi_period": 14, "rsi_bull": 50, "rsi_bear": 50,
            "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
            "bb_period": 20, "bb_std": 2.0, "volume_avg_period": 20,
            "confluence_threshold": 3,
        })
        assert ok is False
        assert "rsi_bear" in reason

    def test_macd_fast_gt_macd_slow_rejected(self):
        """macd_fast > macd_slow must be rejected."""
        ok, reason = validate_params("TechConf", {
            "rsi_period": 14, "rsi_bull": 55, "rsi_bear": 45,
            "macd_fast": 30, "macd_slow": 15, "macd_signal": 9,
            "bb_period": 20, "bb_std": 2.0, "volume_avg_period": 20,
            "confluence_threshold": 3,
        })
        assert ok is False
        assert "macd_fast" in reason

    def test_out_of_range_low(self):
        """Value below minimum should be rejected."""
        ok, reason = validate_params("MomRegime", {
            "adx_period": 2,  # min is 6
            "ema_fast": 10, "ema_slow": 25,
            "adx_threshold": 25, "lookback": 100,
        })
        assert ok is False
        assert "adx_period" in reason

    def test_out_of_range_high(self):
        """Value above maximum should be rejected."""
        ok, reason = validate_params("MomRegime", {
            "adx_period": 14, "ema_fast": 10, "ema_slow": 25,
            "adx_threshold": 25, "lookback": 500,  # max is 250
        })
        assert ok is False
        assert "lookback" in reason

    def test_valid_tech_conf(self):
        ok, reason = validate_params("TechConf", {
            "rsi_period": 14, "rsi_bull": 55, "rsi_bear": 45,
            "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
            "bb_period": 20, "bb_std": 2.0, "volume_avg_period": 20,
            "confluence_threshold": 3,
        })
        assert ok is True

    def test_valid_clob_signal(self):
        ok, reason = validate_params("CLOBSignal", {
            "imbalance_threshold": 1.3, "trade_size_threshold": 500,
            "boost_factor": 0.10, "lookback_seconds": 120,
        })
        assert ok is True

    def test_clob_signal_out_of_range(self):
        ok, reason = validate_params("CLOBSignal", {
            "imbalance_threshold": 5.0,  # max is 2.0
            "trade_size_threshold": 500,
            "boost_factor": 0.10, "lookback_seconds": 120,
        })
        assert ok is False

    def test_unknown_model_passes(self):
        """Unknown model with no defined ranges → passes (no ranges to check)."""
        ok, reason = validate_params("FutureModel", {"whatever": 42})
        assert ok is True

    def test_partial_params_validated(self):
        """Only provided params are checked — missing ones are fine."""
        ok, reason = validate_params("MomRegime", {"adx_period": 14})
        assert ok is True


class TestRegistryRejectsInvalid:
    def test_save_rejects_constraint_violation(self):
        registry = ParamRegistry()
        registry.initialize_defaults()
        bad = ModelParams(values={
            "adx_period": 14, "ema_fast": 25, "ema_slow": 20,
            "adx_threshold": 25, "lookback": 100,
        })
        with pytest.raises(ValueError):
            registry.save_new_version("MomRegime", "5m", bad)
