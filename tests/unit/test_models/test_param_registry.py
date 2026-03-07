"""Tests for ParamRegistry — save, promote, retire, lineage, defaults."""

import pytest
from models.base import ModelParams
from models.param_registry import ParamRegistry


@pytest.fixture
def registry():
    r = ParamRegistry()
    r.initialize_defaults()
    return r


class TestInitializeDefaults:
    def test_all_models_seeded(self, registry):
        """All 7 models × 4 timeframes should be seeded."""
        models = ["MomRegime", "FundBasis", "ChainFlow", "VolSurf", "SentComp", "TechConf", "CLOBSignal"]
        timeframes = ["5m", "15m", "1h", "4h"]
        for m in models:
            for tf in timeframes:
                params = registry.get_active_params(m, tf)
                assert params.version == 1
                assert len(params.values) > 0

    def test_unknown_model_raises(self, registry):
        with pytest.raises(KeyError):
            registry.get_active_params("NonexistentModel", "5m")


class TestGetActiveParams:
    def test_returns_correct_values(self, registry):
        params = registry.get_active_params("MomRegime", "5m")
        assert params.values["adx_period"] == 10
        assert params.values["ema_fast"] == 8
        assert params.values["ema_slow"] == 21

    def test_different_timeframes(self, registry):
        p5m = registry.get_active_params("TechConf", "5m")
        p1h = registry.get_active_params("TechConf", "1h")
        assert p5m.values["rsi_period"] == 10
        assert p1h.values["rsi_period"] == 14


class TestSaveNewVersion:
    def test_save_probation(self, registry):
        new_params = ModelParams(values={"adx_period": 12, "ema_fast": 10, "ema_slow": 25,
                                          "adx_threshold": 22, "lookback": 100})
        saved = registry.save_new_version("MomRegime", "5m", new_params, "PROBATION")
        assert saved.version == 2
        # Active should still be version 1
        active = registry.get_active_params("MomRegime", "5m")
        assert active.version == 1

    def test_save_active_immediately(self, registry):
        new_params = ModelParams(values={"adx_period": 12, "ema_fast": 10, "ema_slow": 25,
                                          "adx_threshold": 22, "lookback": 100})
        saved = registry.save_new_version("MomRegime", "5m", new_params, "ACTIVE")
        assert saved.version == 2
        active = registry.get_active_params("MomRegime", "5m")
        assert active.version == 2

    def test_invalid_params_rejected(self, registry):
        """ema_fast > ema_slow should be rejected."""
        bad_params = ModelParams(values={"adx_period": 14, "ema_fast": 25, "ema_slow": 20,
                                          "adx_threshold": 25, "lookback": 100})
        with pytest.raises(ValueError, match="Constraint violated"):
            registry.save_new_version("MomRegime", "5m", bad_params)

    def test_out_of_range_rejected(self, registry):
        """Parameter out of defined range should be rejected."""
        bad_params = ModelParams(values={"adx_period": 100, "ema_fast": 10, "ema_slow": 25,
                                          "adx_threshold": 22, "lookback": 100})
        with pytest.raises(ValueError, match="out of range"):
            registry.save_new_version("MomRegime", "5m", bad_params)


class TestPromote:
    def test_promote_version(self, registry):
        new_params = ModelParams(values={"adx_period": 12, "ema_fast": 10, "ema_slow": 25,
                                          "adx_threshold": 22, "lookback": 100})
        saved = registry.save_new_version("MomRegime", "5m", new_params, "PROBATION")
        registry.promote("MomRegime", "5m", saved.version)
        active = registry.get_active_params("MomRegime", "5m")
        assert active.version == saved.version

    def test_promote_nonexistent_raises(self, registry):
        with pytest.raises(KeyError):
            registry.promote("MomRegime", "5m", 999)


class TestRetire:
    def test_retire_version(self, registry):
        registry.retire("MomRegime", "5m", 1, "Brier > 0.35 for 2 cycles")
        params = registry.get_active_params("MomRegime", "5m")
        assert params.performance.get("retired") is True
        assert "Brier" in params.performance.get("retire_reason", "")

    def test_retire_nonexistent_raises(self, registry):
        with pytest.raises(KeyError):
            registry.retire("MomRegime", "5m", 999, "reason")


class TestGetLineage:
    def test_lineage_tracks_history(self, registry):
        # Default is version 1
        lineage = registry.get_lineage("MomRegime", "5m")
        assert len(lineage) == 1

        # Add version 2
        new_params = ModelParams(values={"adx_period": 12, "ema_fast": 10, "ema_slow": 25,
                                          "adx_threshold": 22, "lookback": 100})
        registry.save_new_version("MomRegime", "5m", new_params)

        lineage = registry.get_lineage("MomRegime", "5m")
        assert len(lineage) == 2
        assert lineage[0].version == 1
        assert lineage[1].version == 2

    def test_lineage_empty_for_unknown(self, registry):
        lineage = registry.get_lineage("NonexistentModel", "5m")
        assert lineage == []


class TestGetAllActive:
    def test_returns_all(self, registry):
        all_active = registry.get_all_active()
        assert len(all_active) == 35  # 7 models × 5 timeframes (5m, 15m, 1h, 4h, daily)
