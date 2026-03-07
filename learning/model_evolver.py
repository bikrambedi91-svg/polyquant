"""Model evolution — WARNING / CRITICAL / RETIRED pipeline.

Evaluates model performance via Brier scores and manages lifecycle:
- Brier > 0.28 → WARNING (reduce weight 30%, flag for mutation)
- Brier > 0.35 → CRITICAL (near-zero weight, force Optuna optimization)
- 2 consecutive CRITICAL cycles → RETIRED (move to graveyard, weight=0)

Safety rails:
- Max 1 model mutated per recalibration cycle
- Max 1 model retired per cycle
- Minimum 4 active models at all times
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog

from config.constants import (
    DEFAULT_MODEL_WEIGHTS,
    LEARNING_SAFETY_RAILS,
    MODEL_NAMES,
)

logger = structlog.get_logger(__name__)

BRIER_WARNING = 0.28
BRIER_CRITICAL = 0.35
MAX_MUTATED_PER_CYCLE = LEARNING_SAFETY_RAILS["max_models_mutated_per_cycle"]
MAX_RETIRED_PER_CYCLE = LEARNING_SAFETY_RAILS["max_models_retired_per_cycle"]
MIN_ACTIVE_MODELS = LEARNING_SAFETY_RAILS["min_active_models"]
MAX_WEIGHT_CHANGE = LEARNING_SAFETY_RAILS["max_weight_change_per_cycle"]


@dataclass
class ModelHealth:
    """Health status of a single model."""
    model_name: str
    status: str = "ACTIVE"             # ACTIVE, WARNING, CRITICAL, RETIRED
    brier_score: float = 0.25
    consecutive_critical: int = 0
    current_weight_mult: float = 1.0   # Multiplier on default weight
    last_evaluated: str = ""
    mutation_count: int = 0


@dataclass
class EvolutionAction:
    """Action taken during an evolution cycle."""
    model_name: str
    action: str            # "warning", "critical", "retired", "recovered", "weight_reduced"
    old_status: str
    new_status: str
    brier_score: float
    details: str = ""


class ModelEvolver:
    """Manages model lifecycle: evaluation, warning, retirement.

    Tracks per-model health status and enforces safety rails.
    """

    def __init__(self):
        self._health: dict[str, ModelHealth] = {}
        for name in MODEL_NAMES:
            self._health[name] = ModelHealth(model_name=name)

    @property
    def active_count(self) -> int:
        """Number of non-retired models."""
        return sum(
            1 for h in self._health.values()
            if h.status != "RETIRED"
        )

    def get_health(self, model_name: str) -> ModelHealth | None:
        return self._health.get(model_name)

    def get_all_health(self) -> dict[str, ModelHealth]:
        return dict(self._health)

    def evaluate_cycle(
        self,
        brier_scores: dict[str, float],
    ) -> list[EvolutionAction]:
        """Run one evaluation cycle with updated Brier scores.

        Args:
            brier_scores: model_name -> brier_score for this cycle.

        Returns:
            List of actions taken during this cycle.
        """
        actions = []
        mutated_count = 0
        retired_count = 0
        now = datetime.now(timezone.utc).isoformat()

        for model_name, brier in brier_scores.items():
            health = self._health.get(model_name)
            if not health:
                continue

            if health.status == "RETIRED":
                # Already retired — skip
                continue

            old_status = health.status
            health.brier_score = brier
            health.last_evaluated = now

            if brier > BRIER_CRITICAL:
                # CRITICAL
                health.consecutive_critical += 1
                health.current_weight_mult = 0.05  # Near-zero weight

                if health.consecutive_critical >= 2:
                    # Check if we can retire (min active models)
                    if self.active_count > MIN_ACTIVE_MODELS and retired_count < MAX_RETIRED_PER_CYCLE:
                        health.status = "RETIRED"
                        health.current_weight_mult = 0.0
                        retired_count += 1
                        actions.append(EvolutionAction(
                            model_name=model_name,
                            action="retired",
                            old_status=old_status,
                            new_status="RETIRED",
                            brier_score=brier,
                            details=f"2 consecutive CRITICAL cycles (Brier={brier:.3f})",
                        ))
                    else:
                        # Can't retire — stay CRITICAL
                        health.status = "CRITICAL"
                        actions.append(EvolutionAction(
                            model_name=model_name,
                            action="critical",
                            old_status=old_status,
                            new_status="CRITICAL",
                            brier_score=brier,
                            details=f"Would retire but min active={MIN_ACTIVE_MODELS} blocks it",
                        ))
                else:
                    health.status = "CRITICAL"
                    actions.append(EvolutionAction(
                        model_name=model_name,
                        action="critical",
                        old_status=old_status,
                        new_status="CRITICAL",
                        brier_score=brier,
                        details=f"First CRITICAL cycle (consecutive={health.consecutive_critical})",
                    ))

            elif brier > BRIER_WARNING:
                # WARNING
                health.status = "WARNING"
                health.current_weight_mult = 0.70  # Reduce weight 30%
                health.consecutive_critical = 0  # Reset critical counter

                if mutated_count < MAX_MUTATED_PER_CYCLE:
                    mutated_count += 1
                    health.mutation_count += 1
                    actions.append(EvolutionAction(
                        model_name=model_name,
                        action="warning",
                        old_status=old_status,
                        new_status="WARNING",
                        brier_score=brier,
                        details=f"Brier={brier:.3f} > {BRIER_WARNING}, flagged for mutation",
                    ))
                else:
                    actions.append(EvolutionAction(
                        model_name=model_name,
                        action="weight_reduced",
                        old_status=old_status,
                        new_status="WARNING",
                        brier_score=brier,
                        details=f"WARNING but mutation limit ({MAX_MUTATED_PER_CYCLE}) reached",
                    ))

            else:
                # HEALTHY — recover from WARNING/CRITICAL
                if old_status in ("WARNING", "CRITICAL"):
                    actions.append(EvolutionAction(
                        model_name=model_name,
                        action="recovered",
                        old_status=old_status,
                        new_status="ACTIVE",
                        brier_score=brier,
                        details=f"Recovered from {old_status} (Brier={brier:.3f})",
                    ))
                health.status = "ACTIVE"
                health.current_weight_mult = 1.0
                health.consecutive_critical = 0

        logger.info(
            "evolution_cycle_complete",
            actions=len(actions),
            active=self.active_count,
            mutated=mutated_count,
            retired=retired_count,
        )

        return actions

    def get_effective_weights(self, timeframe: str) -> dict[str, float]:
        """Get effective model weights after health adjustments.

        Applies weight multiplier from health status to default weights.
        Normalizes so weights sum to 1.0.
        """
        defaults = DEFAULT_MODEL_WEIGHTS.get(timeframe, {})
        raw = {}

        for model_name, default_weight in defaults.items():
            health = self._health.get(model_name)
            if health:
                raw[model_name] = default_weight * health.current_weight_mult
            else:
                raw[model_name] = default_weight

        # Normalize
        total = sum(raw.values())
        if total > 0:
            return {k: v / total for k, v in raw.items()}
        return raw

    def can_retire(self) -> bool:
        """Check if we can retire another model (min 4 active)."""
        return self.active_count > MIN_ACTIVE_MODELS

    def force_status(self, model_name: str, status: str) -> None:
        """Force a model's status (for testing/manual override)."""
        health = self._health.get(model_name)
        if health:
            health.status = status
            if status == "RETIRED":
                health.current_weight_mult = 0.0
