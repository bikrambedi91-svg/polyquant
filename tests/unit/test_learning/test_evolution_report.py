"""Tests for learning/evolution_report.py — Report generation."""

import pytest
from learning.evolution_report import EvolutionReport, ReportGenerator
from learning.model_evolver import EvolutionAction, ModelHealth
from learning.sl_tp_learner import SLTPResult
from learning.param_optimizer import OptimizationResult


@pytest.fixture
def generator():
    return ReportGenerator()


def _make_health() -> dict[str, ModelHealth]:
    return {
        "MomRegime": ModelHealth(model_name="MomRegime", status="ACTIVE"),
        "TechConf": ModelHealth(model_name="TechConf", status="WARNING"),
    }


def _make_action() -> EvolutionAction:
    return EvolutionAction(
        model_name="TechConf",
        action="warning",
        old_status="ACTIVE",
        new_status="WARNING",
        brier_score=0.30,
        details="Brier=0.30 > 0.28",
    )


class TestReportGeneration:
    def test_generate_report(self, generator):
        report = generator.generate(
            total_trades=100,
            new_trades=10,
            model_actions=[_make_action()],
            model_health=_make_health(),
            ensemble_brier=0.22,
            ensemble_win_rate=0.58,
            total_pnl=250.0,
        )
        assert report.cycle_number == 1
        assert report.total_trades == 100
        assert report.ensemble_brier == 0.22

    def test_sequential_cycle_numbers(self, generator):
        r1 = generator.generate(50, 50, [], _make_health())
        r2 = generator.generate(100, 50, [], _make_health())
        assert r1.cycle_number == 1
        assert r2.cycle_number == 2

    def test_to_text_output(self, generator):
        report = generator.generate(
            total_trades=100,
            new_trades=10,
            model_actions=[_make_action()],
            model_health=_make_health(),
            ensemble_brier=0.22,
            ensemble_win_rate=0.58,
            total_pnl=250.0,
        )
        text = report.to_text()
        assert "Evolution Report #1" in text
        assert "Brier score: 0.2200" in text
        assert "TechConf" in text
        assert "WARNING" in text

    def test_to_dict_output(self, generator):
        report = generator.generate(
            total_trades=100,
            new_trades=10,
            model_actions=[_make_action()],
            model_health=_make_health(),
        )
        d = report.to_dict()
        assert d["total_trades"] == 100
        assert "model_health" in d
        assert len(d["actions"]) == 1

    def test_warnings_generated(self, generator):
        """Low active model count → warning in report."""
        report = generator.generate(
            total_trades=100,
            new_trades=10,
            model_actions=[],
            model_health=_make_health(),
            active_model_count=4,
            ensemble_brier=0.35,
        )
        assert len(report.warnings) >= 1
        assert any("4 active" in w for w in report.warnings)
        assert any("Brier" in w for w in report.warnings)

    def test_with_sl_tp_updates(self, generator):
        sl_tp = SLTPResult(
            asset="BTC", timeframe="1h", regime="RISK_ON",
            optimal_sl_pct=0.10, optimal_tp_pct=0.06,
            simulated_pnl=100.0, trade_count=50,
        )
        report = generator.generate(
            total_trades=100, new_trades=10,
            model_actions=[], model_health=_make_health(),
            sl_tp_updates=[sl_tp],
        )
        assert len(report.sl_tp_updates) == 1
        text = report.to_text()
        assert "BTC/1h/RISK_ON" in text

    def test_with_param_optimization(self, generator):
        opt = OptimizationResult(
            model_name="MomRegime", timeframe="1h",
            new_params={"adx_period": 12},
            train_brier=0.20, validate_brier=0.22,
            holdout_brier=0.21, accepted=True,
        )
        report = generator.generate(
            total_trades=100, new_trades=10,
            model_actions=[], model_health=_make_health(),
            param_optimizations=[opt],
        )
        assert len(report.param_optimizations) == 1
        text = report.to_text()
        assert "ACCEPTED" in text

    def test_get_latest(self, generator):
        assert generator.get_latest() is None
        generator.generate(50, 50, [], _make_health())
        assert generator.get_latest() is not None
        assert generator.get_latest().cycle_number == 1

    def test_get_all(self, generator):
        generator.generate(50, 50, [], _make_health())
        generator.generate(100, 50, [], _make_health())
        assert len(generator.get_all()) == 2
