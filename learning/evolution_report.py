"""Human-readable evolution report — summarizes recalibration cycle results.

Generates a structured report of what happened during each learning cycle:
model health changes, parameter mutations, SL/TP updates, graduations, etc.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog

from learning.model_evolver import EvolutionAction, ModelHealth
from learning.sl_tp_learner import SLTPResult
from learning.param_optimizer import OptimizationResult

logger = structlog.get_logger(__name__)


@dataclass
class EvolutionReport:
    """Summary of a single recalibration cycle."""
    cycle_number: int
    timestamp: str = ""
    total_trades: int = 0
    new_trades_since_last: int = 0

    # Model health
    model_actions: list[EvolutionAction] = field(default_factory=list)
    model_health_snapshot: dict = field(default_factory=dict)  # model -> status

    # SL/TP updates
    sl_tp_updates: list[SLTPResult] = field(default_factory=list)

    # Parameter optimizations
    param_optimizations: list[OptimizationResult] = field(default_factory=list)

    # Ensemble metrics
    ensemble_brier: float = 0.0
    ensemble_win_rate: float = 0.0
    total_pnl: float = 0.0

    # Safety
    active_model_count: int = 7
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_text(self) -> str:
        """Generate human-readable text report."""
        lines = []
        lines.append(f"=== Evolution Report #{self.cycle_number} ===")
        lines.append(f"Time: {self.timestamp}")
        lines.append(f"Total trades: {self.total_trades} (+{self.new_trades_since_last} new)")
        lines.append("")

        # Ensemble performance
        lines.append("-- Ensemble Performance --")
        lines.append(f"  Brier score: {self.ensemble_brier:.4f}")
        lines.append(f"  Win rate: {self.ensemble_win_rate:.1%}")
        lines.append(f"  Total P&L: ${self.total_pnl:.2f}")
        lines.append("")

        # Model health
        lines.append(f"-- Model Health ({self.active_model_count} active) --")
        for name, status in sorted(self.model_health_snapshot.items()):
            lines.append(f"  {name}: {status}")
        lines.append("")

        # Actions taken
        if self.model_actions:
            lines.append("-- Actions Taken --")
            for action in self.model_actions:
                lines.append(
                    f"  [{action.action.upper()}] {action.model_name}: "
                    f"{action.old_status} -> {action.new_status} "
                    f"(Brier={action.brier_score:.3f}) {action.details}"
                )
            lines.append("")

        # SL/TP updates
        if self.sl_tp_updates:
            lines.append("-- SL/TP Updates --")
            for update in self.sl_tp_updates:
                clamped = " [CLAMPED]" if update.was_clamped else ""
                lines.append(
                    f"  {update.asset}/{update.timeframe}/{update.regime}: "
                    f"SL={update.optimal_sl_pct:.1%} TP={update.optimal_tp_pct:.1%} "
                    f"({update.trade_count} trades){clamped}"
                )
            lines.append("")

        # Param optimizations
        if self.param_optimizations:
            lines.append("-- Parameter Optimizations --")
            for opt in self.param_optimizations:
                status = "ACCEPTED" if opt.accepted else f"REJECTED ({opt.reject_reason})"
                lines.append(
                    f"  {opt.model_name}/{opt.timeframe}: {status} "
                    f"(train={opt.train_brier:.4f}, val={opt.validate_brier:.4f})"
                )
            lines.append("")

        # Warnings
        if self.warnings:
            lines.append("-- Warnings --")
            for w in self.warnings:
                lines.append(f"  ! {w}")
            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return {
            "cycle_number": self.cycle_number,
            "timestamp": self.timestamp,
            "total_trades": self.total_trades,
            "new_trades_since_last": self.new_trades_since_last,
            "ensemble_brier": self.ensemble_brier,
            "ensemble_win_rate": self.ensemble_win_rate,
            "total_pnl": self.total_pnl,
            "active_model_count": self.active_model_count,
            "model_health": self.model_health_snapshot,
            "actions": [
                {"model": a.model_name, "action": a.action, "brier": a.brier_score}
                for a in self.model_actions
            ],
            "sl_tp_updates": [
                {"asset": u.asset, "tf": u.timeframe, "sl_pct": u.optimal_sl_pct, "tp_pct": u.optimal_tp_pct}
                for u in self.sl_tp_updates
            ],
            "param_optimizations": [
                {"model": o.model_name, "accepted": o.accepted}
                for o in self.param_optimizations
            ],
            "warnings": self.warnings,
        }


class ReportGenerator:
    """Generates evolution reports from cycle data."""

    def __init__(self):
        self._reports: list[EvolutionReport] = []
        self._cycle_count = 0

    def generate(
        self,
        total_trades: int,
        new_trades: int,
        model_actions: list[EvolutionAction],
        model_health: dict[str, ModelHealth],
        sl_tp_updates: list[SLTPResult] | None = None,
        param_optimizations: list[OptimizationResult] | None = None,
        ensemble_brier: float = 0.0,
        ensemble_win_rate: float = 0.0,
        total_pnl: float = 0.0,
        active_model_count: int = 7,
    ) -> EvolutionReport:
        """Generate a report for a recalibration cycle."""
        self._cycle_count += 1

        health_snapshot = {
            name: h.status for name, h in model_health.items()
        }

        warnings = []
        if active_model_count <= 4:
            warnings.append(f"Only {active_model_count} active models — near minimum!")
        if ensemble_brier > 0.30:
            warnings.append(f"Ensemble Brier ({ensemble_brier:.3f}) is high")

        report = EvolutionReport(
            cycle_number=self._cycle_count,
            total_trades=total_trades,
            new_trades_since_last=new_trades,
            model_actions=model_actions,
            model_health_snapshot=health_snapshot,
            sl_tp_updates=sl_tp_updates or [],
            param_optimizations=param_optimizations or [],
            ensemble_brier=ensemble_brier,
            ensemble_win_rate=ensemble_win_rate,
            total_pnl=total_pnl,
            active_model_count=active_model_count,
            warnings=warnings,
        )

        self._reports.append(report)

        logger.info(
            "evolution_report_generated",
            cycle=self._cycle_count,
            actions=len(model_actions),
            warnings=len(warnings),
        )

        return report

    def get_latest(self) -> EvolutionReport | None:
        return self._reports[-1] if self._reports else None

    def get_all(self) -> list[EvolutionReport]:
        return list(self._reports)
