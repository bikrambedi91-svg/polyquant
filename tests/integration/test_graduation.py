"""Integration tests for orchestrator/graduation.py — Paper→Live transition."""

import pytest
from datetime import datetime, timezone, timedelta

from orchestrator.graduation import GraduationManager, TradeStats, GraduationCheck


def _good_stats(**overrides) -> TradeStats:
    """Trade stats that meet ALL graduation criteria."""
    defaults = {
        "total_trades": 120,
        "wins": 70,
        "losses": 50,
        "total_pnl": 500.0,
        "daily_pnls": [10.0, -5.0, 15.0, -3.0, 8.0, 12.0, -2.0] * 4,
        "first_trade_date": datetime.now(timezone.utc) - timedelta(days=20),
        "calibration_error": 0.10,
        "recalibration_cycles": 3,
        "critical_model_count": 0,
    }
    defaults.update(overrides)
    return TradeStats(**defaults)


@pytest.fixture
def manager():
    return GraduationManager(bankroll=10000.0)


class TestGraduationCriteria:
    def test_all_criteria_met_eligible(self, manager):
        """All criteria met → eligible."""
        check = manager.check_graduation(_good_stats())
        assert check.eligible is True
        assert len(check.failed_criteria) == 0

    def test_insufficient_trades_blocked(self, manager):
        """< 100 trades → blocked."""
        check = manager.check_graduation(_good_stats(total_trades=80, wins=50, losses=30))
        assert check.eligible is False
        assert "min_trades" in check.failed_criteria

    def test_low_win_rate_blocked(self, manager):
        """Win rate < 54% → blocked."""
        check = manager.check_graduation(_good_stats(wins=50, losses=70))
        assert check.eligible is False
        assert "win_rate" in check.failed_criteria

    def test_negative_pnl_blocked(self, manager):
        check = manager.check_graduation(_good_stats(total_pnl=-50.0))
        assert check.eligible is False
        assert "positive_pnl" in check.failed_criteria

    def test_low_sharpe_blocked(self, manager):
        """Very noisy returns → low Sharpe → blocked."""
        # Daily PnLs with tiny mean and huge std
        pnls = [100, -100, 100, -100, 100, -100, 100, -100] * 4
        check = manager.check_graduation(_good_stats(daily_pnls=pnls))
        assert check.eligible is False
        assert "sharpe" in check.failed_criteria

    def test_high_calibration_error_blocked(self, manager):
        check = manager.check_graduation(_good_stats(calibration_error=0.20))
        assert check.eligible is False
        assert "calibration" in check.failed_criteria

    def test_daily_drawdown_blocked(self, manager):
        """Single day loss > 6% of bankroll → blocked."""
        # $650 loss on $10k bankroll = 6.5%
        pnls = [10.0, 5.0, -650.0, 10.0, 5.0]
        check = manager.check_graduation(_good_stats(daily_pnls=pnls))
        assert check.eligible is False
        assert "daily_drawdown" in check.failed_criteria

    def test_too_few_days_blocked(self, manager):
        check = manager.check_graduation(
            _good_stats(first_trade_date=datetime.now(timezone.utc) - timedelta(days=10))
        )
        assert check.eligible is False
        assert "min_days" in check.failed_criteria

    def test_insufficient_recal_cycles_blocked(self, manager):
        check = manager.check_graduation(_good_stats(recalibration_cycles=1))
        assert check.eligible is False
        assert "recal_cycles" in check.failed_criteria

    def test_critical_model_blocked(self, manager):
        """Any CRITICAL model → blocked."""
        check = manager.check_graduation(_good_stats(critical_model_count=1))
        assert check.eligible is False
        assert "no_critical" in check.failed_criteria


class TestGraduation:
    def test_graduate_success(self, manager):
        assert manager.is_live is False
        success = manager.graduate(_good_stats())
        assert success is True
        assert manager.is_live is True

    def test_graduate_failure(self, manager):
        success = manager.graduate(_good_stats(total_trades=50))
        assert success is False
        assert manager.is_live is False

    def test_half_size_after_graduation(self, manager):
        """First 48h after graduation → half-size."""
        manager.graduate(_good_stats())
        assert manager.is_half_size is True
        assert manager.size_multiplier == 0.5

    def test_full_size_after_48h(self, manager):
        """After 48h → full size."""
        manager.graduate(_good_stats())
        # Simulate 49h passed
        manager._graduated_at = datetime.now(timezone.utc) - timedelta(hours=49)
        assert manager.is_half_size is False
        assert manager.size_multiplier == 1.0

    def test_not_half_size_when_paper(self, manager):
        assert manager.is_half_size is False
        assert manager.size_multiplier == 1.0


class TestDeGraduation:
    def test_live_drawdown_degrades(self, manager):
        manager.graduate(_good_stats())
        assert manager.is_live is True

        # Simulate 6% daily drawdown (>5% threshold)
        live_stats = TradeStats(
            total_trades=20, wins=10, losses=10,
            daily_pnls=[10.0, -510.0],  # $510 on $10k = 5.1%
        )
        should, reason = manager.check_degraduation(live_stats)
        assert should is True
        assert "drawdown" in reason.lower()

    def test_low_win_rate_degrades(self, manager):
        manager.graduate(_good_stats())

        # 50+ trades with < 48% win rate
        live_stats = TradeStats(
            total_trades=60, wins=25, losses=35,
            daily_pnls=[5.0] * 10,
        )
        should, reason = manager.check_degraduation(live_stats)
        assert should is True
        assert "win rate" in reason.lower()

    def test_two_critical_models_degrades(self, manager):
        manager.graduate(_good_stats())

        live_stats = TradeStats(
            total_trades=30, wins=18, losses=12,
            daily_pnls=[5.0] * 5,
            critical_model_count=2,
        )
        should, reason = manager.check_degraduation(live_stats)
        assert should is True
        assert "CRITICAL" in reason

    def test_no_degrad_when_ok(self, manager):
        manager.graduate(_good_stats())

        live_stats = TradeStats(
            total_trades=30, wins=20, losses=10,
            daily_pnls=[10.0, 5.0, -3.0],
            critical_model_count=0,
        )
        should, reason = manager.check_degraduation(live_stats)
        assert should is False

    def test_no_degrad_when_paper(self, manager):
        """Can't de-graduate if not live."""
        should, reason = manager.check_degraduation(TradeStats())
        assert should is False

    def test_degraduate_resets_state(self, manager):
        manager.graduate(_good_stats())
        assert manager.is_live is True

        manager.degraduate("daily drawdown exceeded")
        assert manager.is_live is False


class TestTradeStats:
    def test_win_rate(self):
        stats = TradeStats(total_trades=100, wins=60, losses=40)
        assert stats.win_rate == pytest.approx(0.60)

    def test_win_rate_zero_trades(self):
        stats = TradeStats()
        assert stats.win_rate == 0.0

    def test_sharpe_positive(self):
        stats = TradeStats(
            daily_pnls=[10, 12, 8, 15, 11, 9, 14, 13, 10, 12]
        )
        assert stats.sharpe_ratio > 0

    def test_sharpe_zero_std(self):
        stats = TradeStats(daily_pnls=[5, 5, 5, 5])
        # All same → std=0, positive mean → capped at 10
        assert stats.sharpe_ratio == 10.0

    def test_days_trading(self):
        stats = TradeStats(
            first_trade_date=datetime.now(timezone.utc) - timedelta(days=15)
        )
        assert stats.days_trading >= 14  # Allow 1 day tolerance

    def test_max_daily_drawdown(self):
        stats = TradeStats(daily_pnls=[10, -50, 20, -30, 5])
        assert stats.max_daily_drawdown == 50.0


class TestGraduationStatus:
    def test_status_paper(self, manager):
        status = manager.get_status()
        assert status["is_live"] is False
        assert status["graduated_at"] is None

    def test_status_live(self, manager):
        manager.graduate(_good_stats())
        status = manager.get_status()
        assert status["is_live"] is True
        assert status["graduated_at"] is not None
        assert status["is_half_size"] is True
