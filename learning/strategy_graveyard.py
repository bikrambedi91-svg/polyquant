"""Strategy graveyard — stores retired model configurations with death reports.

Keeps historical record of what failed and why, enabling:
1. Avoiding re-discovering failed parameter sets
2. Resurrection checks if market conditions change
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class GraveyardEntry:
    """A retired model/strategy with full death report."""
    model_name: str
    timeframe: str
    retired_params: dict             # The param values at time of retirement
    param_version: int
    brier_at_death: float
    consecutive_critical: int
    trade_count: int                 # How many trades before retirement
    death_reason: str
    retired_at: str = ""
    win_rate_at_death: float = 0.0
    total_pnl_at_death: float = 0.0
    resurrection_eligible: bool = True  # Can be resurrected later

    def __post_init__(self):
        if not self.retired_at:
            self.retired_at = datetime.now(timezone.utc).isoformat()


class StrategyGraveyard:
    """Stores and manages retired strategies."""

    def __init__(self):
        self._entries: list[GraveyardEntry] = []

    def bury(self, entry: GraveyardEntry) -> None:
        """Add a retired strategy to the graveyard."""
        self._entries.append(entry)
        logger.info(
            "strategy_buried",
            model=entry.model_name,
            timeframe=entry.timeframe,
            reason=entry.death_reason,
            brier=entry.brier_at_death,
        )

    def get_all(self) -> list[GraveyardEntry]:
        return list(self._entries)

    def get_by_model(self, model_name: str) -> list[GraveyardEntry]:
        return [e for e in self._entries if e.model_name == model_name]

    def check_resurrection(
        self,
        model_name: str,
        current_brier: float,
        min_improvement: float = 0.10,
    ) -> GraveyardEntry | None:
        """Check if a buried strategy should be resurrected.

        A strategy is eligible for resurrection if:
        1. It's marked as resurrection_eligible
        2. The current model performance (Brier) is significantly worse
           than what the buried strategy had at death (suggesting the
           replacement is also failing)

        Returns the entry to resurrect, or None.
        """
        candidates = [
            e for e in self._entries
            if e.model_name == model_name and e.resurrection_eligible
        ]

        if not candidates:
            return None

        # Find the best-performing buried entry
        best = min(candidates, key=lambda e: e.brier_at_death)

        # Resurrect if current performance is worse than the buried version
        # by at least min_improvement
        if current_brier > best.brier_at_death + min_improvement:
            logger.info(
                "resurrection_candidate_found",
                model=model_name,
                current_brier=current_brier,
                buried_brier=best.brier_at_death,
            )
            return best

        return None

    def mark_no_resurrect(self, model_name: str, timeframe: str) -> None:
        """Mark entries as not eligible for resurrection."""
        for e in self._entries:
            if e.model_name == model_name and e.timeframe == timeframe:
                e.resurrection_eligible = False

    @property
    def count(self) -> int:
        return len(self._entries)
