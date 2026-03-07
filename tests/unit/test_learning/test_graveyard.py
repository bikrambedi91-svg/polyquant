"""Tests for learning/strategy_graveyard.py — Retire + resurrection check."""

import pytest
from learning.strategy_graveyard import StrategyGraveyard, GraveyardEntry


def _entry(
    model_name="MomRegime", timeframe="1h", brier=0.38,
    trade_count=100, reason="2 consecutive CRITICAL",
    **kwargs,
) -> GraveyardEntry:
    return GraveyardEntry(
        model_name=model_name,
        timeframe=timeframe,
        retired_params={"adx_period": 14, "ema_fast": 20},
        param_version=3,
        brier_at_death=brier,
        consecutive_critical=2,
        trade_count=trade_count,
        death_reason=reason,
        **kwargs,
    )


class TestGraveyard:
    def test_bury_and_retrieve(self):
        gy = StrategyGraveyard()
        gy.bury(_entry())
        assert gy.count == 1
        assert len(gy.get_all()) == 1

    def test_get_by_model(self):
        gy = StrategyGraveyard()
        gy.bury(_entry(model_name="MomRegime"))
        gy.bury(_entry(model_name="TechConf"))
        gy.bury(_entry(model_name="MomRegime", brier=0.40))
        assert len(gy.get_by_model("MomRegime")) == 2
        assert len(gy.get_by_model("TechConf")) == 1

    def test_resurrection_check_eligible(self):
        """Current Brier much worse than buried → resurrect."""
        gy = StrategyGraveyard()
        gy.bury(_entry(model_name="MomRegime", brier=0.30))

        # Current model Brier is 0.45 (way worse than 0.30 + 0.10)
        candidate = gy.check_resurrection("MomRegime", current_brier=0.45)
        assert candidate is not None
        assert candidate.brier_at_death == 0.30

    def test_resurrection_check_not_eligible(self):
        """Current Brier close to buried → no resurrect."""
        gy = StrategyGraveyard()
        gy.bury(_entry(model_name="MomRegime", brier=0.35))

        # Current model at 0.38 — only 0.03 worse, less than 0.10 threshold
        candidate = gy.check_resurrection("MomRegime", current_brier=0.38)
        assert candidate is None

    def test_resurrection_no_entries(self):
        gy = StrategyGraveyard()
        assert gy.check_resurrection("MomRegime", current_brier=0.50) is None

    def test_mark_no_resurrect(self):
        """After marking no-resurrect, check returns None."""
        gy = StrategyGraveyard()
        gy.bury(_entry(model_name="MomRegime", brier=0.30))
        gy.mark_no_resurrect("MomRegime", "1h")

        candidate = gy.check_resurrection("MomRegime", current_brier=0.50)
        assert candidate is None

    def test_entry_has_death_report(self):
        entry = _entry(
            model_name="TechConf",
            brier=0.40,
            reason="Failed recalibration",
            win_rate_at_death=0.45,
            total_pnl_at_death=-150.0,
        )
        assert entry.death_reason == "Failed recalibration"
        assert entry.win_rate_at_death == 0.45
        assert entry.total_pnl_at_death == -150.0
        assert len(entry.retired_at) > 0

    def test_resurrection_picks_best(self):
        """Multiple buried entries → picks the one with lowest Brier."""
        gy = StrategyGraveyard()
        gy.bury(_entry(model_name="MomRegime", brier=0.38))
        gy.bury(_entry(model_name="MomRegime", brier=0.32))  # Better one
        gy.bury(_entry(model_name="MomRegime", brier=0.36))

        candidate = gy.check_resurrection("MomRegime", current_brier=0.50)
        assert candidate is not None
        assert candidate.brier_at_death == 0.32
