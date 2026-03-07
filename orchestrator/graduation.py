"""Graduation manager — Paper → Live transition with safety criteria.

ALL criteria must be met simultaneously for graduation:
1. ≥ 100 paper trades
2. Win rate > 54%
3. Total P&L > 0
4. Sharpe ratio > 0.8
5. Calibration error < 0.15
6. No single day drawdown > 6% in last 30 days
7. ≥ 14 calendar days of paper trading
8. ≥ 2 recalibration cycles completed
9. No model currently in CRITICAL state

De-graduation (back to paper):
- Live daily drawdown > 5%
- Win rate < 48% over 50+ live trades
- 2+ models in CRITICAL simultaneously

Live safety: First 48 hours at half-size (50% of normal Kelly).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class GraduationCheck:
    """Result of a graduation eligibility check."""
    eligible: bool
    criteria: dict[str, bool] = field(default_factory=dict)
    details: dict[str, str] = field(default_factory=dict)

    @property
    def failed_criteria(self) -> list[str]:
        return [k for k, v in self.criteria.items() if not v]


@dataclass
class TradeStats:
    """Aggregated trade statistics for graduation evaluation."""
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    daily_pnls: list[float] = field(default_factory=list)
    first_trade_date: datetime | None = None
    calibration_error: float = 0.0
    recalibration_cycles: int = 0
    critical_model_count: int = 0

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.wins / self.total_trades

    @property
    def sharpe_ratio(self) -> float:
        if not self.daily_pnls or len(self.daily_pnls) < 2:
            return 0.0
        pnls = np.array(self.daily_pnls)
        mean_pnl = float(np.mean(pnls))
        std_pnl = float(np.std(pnls, ddof=1))
        if std_pnl == 0:
            return 0.0 if mean_pnl <= 0 else 10.0
        # Annualize: sqrt(365) for daily
        return (mean_pnl / std_pnl) * np.sqrt(365)

    @property
    def days_trading(self) -> int:
        if self.first_trade_date is None:
            return 0
        return (datetime.now(timezone.utc) - self.first_trade_date).days

    @property
    def max_daily_drawdown(self) -> float:
        """Worst single-day P&L as percentage of daily_pnls."""
        if not self.daily_pnls:
            return 0.0
        return abs(min(self.daily_pnls)) if min(self.daily_pnls) < 0 else 0.0


class GraduationManager:
    """Manages Paper → Live graduation with safety criteria."""

    def __init__(
        self,
        min_trades: int = 100,
        min_win_rate: float = 0.54,
        min_sharpe: float = 0.8,
        max_calibration_error: float = 0.15,
        max_daily_dd_pct: float = 0.06,
        min_days: int = 14,
        min_recal_cycles: int = 2,
        bankroll: float = 10000.0,
        live_dd_threshold: float = 0.05,
        live_min_win_rate: float = 0.48,
        live_min_trades_for_degrad: int = 50,
        half_size_hours: int = 48,
    ):
        self._min_trades = min_trades
        self._min_win_rate = min_win_rate
        self._min_sharpe = min_sharpe
        self._max_cal_error = max_calibration_error
        self._max_daily_dd = max_daily_dd_pct
        self._min_days = min_days
        self._min_recal = min_recal_cycles
        self._bankroll = bankroll
        self._live_dd = live_dd_threshold
        self._live_wr = live_min_win_rate
        self._live_min_trades = live_min_trades_for_degrad
        self._half_size_hours = half_size_hours

        self._is_live = False
        self._graduated_at: datetime | None = None
        self._degraduated_at: datetime | None = None

    @property
    def is_live(self) -> bool:
        return self._is_live

    @property
    def is_half_size(self) -> bool:
        """True if within first 48 hours of live trading."""
        if not self._is_live or not self._graduated_at:
            return False
        elapsed = (datetime.now(timezone.utc) - self._graduated_at).total_seconds()
        return elapsed < self._half_size_hours * 3600

    @property
    def size_multiplier(self) -> float:
        """Returns 0.5 during half-size period, 1.0 otherwise."""
        return 0.5 if self.is_half_size else 1.0

    def check_graduation(self, stats: TradeStats) -> GraduationCheck:
        """Check if paper trading meets all graduation criteria.

        Returns GraduationCheck with per-criterion pass/fail.
        """
        criteria = {}
        details = {}

        # 1. Minimum trades
        criteria["min_trades"] = stats.total_trades >= self._min_trades
        details["min_trades"] = f"{stats.total_trades}/{self._min_trades}"

        # 2. Win rate
        criteria["win_rate"] = stats.win_rate > self._min_win_rate
        details["win_rate"] = f"{stats.win_rate:.1%} (need >{self._min_win_rate:.0%})"

        # 3. Positive P&L
        criteria["positive_pnl"] = stats.total_pnl > 0
        details["positive_pnl"] = f"${stats.total_pnl:.2f}"

        # 4. Sharpe ratio
        criteria["sharpe"] = stats.sharpe_ratio > self._min_sharpe
        details["sharpe"] = f"{stats.sharpe_ratio:.2f} (need >{self._min_sharpe})"

        # 5. Calibration error
        criteria["calibration"] = stats.calibration_error < self._max_cal_error
        details["calibration"] = f"{stats.calibration_error:.3f} (need <{self._max_cal_error})"

        # 6. No >6% daily drawdown in last 30 days
        dd_ok = True
        if stats.daily_pnls:
            max_dd_usd = stats.max_daily_drawdown
            max_dd_pct = max_dd_usd / self._bankroll if self._bankroll > 0 else 0
            dd_ok = max_dd_pct <= self._max_daily_dd
            details["daily_drawdown"] = f"{max_dd_pct:.1%} (max {self._max_daily_dd:.0%})"
        else:
            details["daily_drawdown"] = "no data"
        criteria["daily_drawdown"] = dd_ok

        # 7. Minimum days
        criteria["min_days"] = stats.days_trading >= self._min_days
        details["min_days"] = f"{stats.days_trading}/{self._min_days} days"

        # 8. Recalibration cycles
        criteria["recal_cycles"] = stats.recalibration_cycles >= self._min_recal
        details["recal_cycles"] = f"{stats.recalibration_cycles}/{self._min_recal}"

        # 9. No CRITICAL models
        criteria["no_critical"] = stats.critical_model_count == 0
        details["no_critical"] = f"{stats.critical_model_count} critical"

        eligible = all(criteria.values())

        return GraduationCheck(
            eligible=eligible,
            criteria=criteria,
            details=details,
        )

    def graduate(self, stats: TradeStats) -> bool:
        """Attempt to graduate from paper to live.

        Returns True if graduated, False if criteria not met.
        """
        check = self.check_graduation(stats)
        if not check.eligible:
            logger.info(
                "graduation_blocked",
                failed=check.failed_criteria,
                details=check.details,
            )
            return False

        self._is_live = True
        self._graduated_at = datetime.now(timezone.utc)
        self._degraduated_at = None

        logger.info(
            "graduated_to_live",
            trades=stats.total_trades,
            win_rate=f"{stats.win_rate:.1%}",
            sharpe=f"{stats.sharpe_ratio:.2f}",
            pnl=f"${stats.total_pnl:.2f}",
        )

        return True

    def check_degraduation(self, live_stats: TradeStats) -> tuple[bool, str]:
        """Check if live performance warrants de-graduation.

        Returns (should_degraduate, reason).
        """
        if not self._is_live:
            return False, ""

        # Daily drawdown > 5%
        if live_stats.daily_pnls:
            today_pnl = live_stats.daily_pnls[-1] if live_stats.daily_pnls else 0
            if today_pnl < 0:
                dd_pct = abs(today_pnl) / self._bankroll if self._bankroll > 0 else 0
                if dd_pct > self._live_dd:
                    return True, f"Live daily drawdown {dd_pct:.1%} > {self._live_dd:.0%}"

        # Win rate < 48% over 50+ trades
        if live_stats.total_trades >= self._live_min_trades:
            if live_stats.win_rate < self._live_wr:
                return True, (
                    f"Live win rate {live_stats.win_rate:.1%} < {self._live_wr:.0%} "
                    f"over {live_stats.total_trades} trades"
                )

        # 2+ CRITICAL models
        if live_stats.critical_model_count >= 2:
            return True, f"{live_stats.critical_model_count} models in CRITICAL"

        return False, ""

    def degraduate(self, reason: str) -> None:
        """De-graduate back to paper trading."""
        self._is_live = False
        self._degraduated_at = datetime.now(timezone.utc)

        logger.warning(
            "degraduated_to_paper",
            reason=reason,
            was_live_for=str(
                self._degraduated_at - self._graduated_at
            ) if self._graduated_at else "unknown",
        )

    def get_status(self) -> dict:
        """Get graduation status for dashboard."""
        return {
            "is_live": self._is_live,
            "is_half_size": self.is_half_size,
            "size_multiplier": self.size_multiplier,
            "graduated_at": self._graduated_at.isoformat() if self._graduated_at else None,
            "degraduated_at": self._degraduated_at.isoformat() if self._degraduated_at else None,
        }
