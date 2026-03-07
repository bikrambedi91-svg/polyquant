"""Optuna-based parameter optimization with walk-forward validation.

Walk-forward split: 60% train / 20% validate / 20% holdout.
Min 80 trades before optimization is available.
Overfit check: validate Brier > train Brier + 0.05 → reject.
After Optuna returns params, runs through param_registry.validate_params()
to ensure constraints are met (ema_fast < ema_slow, etc.)
"""

from dataclasses import dataclass

import structlog

from config.constants import LEARNING_SAFETY_RAILS
from learning.feedback_db import FeedbackRecord
from models.param_registry import PARAM_RANGES, validate_params

logger = structlog.get_logger(__name__)

MIN_TRADES = LEARNING_SAFETY_RAILS["min_trades_for_param_mutation"]  # 80
OVERFIT_THRESHOLD = LEARNING_SAFETY_RAILS["optuna_overfit_threshold"]  # 0.05


@dataclass
class OptimizationResult:
    """Result of a parameter optimization run."""
    model_name: str
    timeframe: str
    new_params: dict          # param_name -> value
    train_brier: float
    validate_brier: float
    holdout_brier: float
    accepted: bool
    reject_reason: str = ""
    n_trials: int = 0
    n_trades: int = 0


def _compute_brier(records: list[FeedbackRecord], model_name: str) -> float:
    """Compute Brier score for a model across records."""
    scored = [r for r in records if model_name in r.model_probs]
    if not scored:
        return 0.5
    return sum(
        (r.model_probs[model_name] - r.actual_outcome) ** 2
        for r in scored
    ) / len(scored)


def _split_walk_forward(
    records: list[FeedbackRecord],
) -> tuple[list[FeedbackRecord], list[FeedbackRecord], list[FeedbackRecord]]:
    """Split records into 60/20/20 train/validate/holdout.

    Records should be sorted by time (oldest first).
    """
    n = len(records)
    train_end = int(n * 0.60)
    val_end = int(n * 0.80)
    return records[:train_end], records[train_end:val_end], records[val_end:]


class ParamOptimizer:
    """Optuna-based model parameter optimizer."""

    def __init__(self, n_trials: int = 50):
        self._n_trials = n_trials

    def optimize(
        self,
        model_name: str,
        timeframe: str,
        records: list[FeedbackRecord],
        current_params: dict,
    ) -> OptimizationResult | None:
        """Run parameter optimization for a single model.

        Args:
            model_name: The model to optimize
            timeframe: Which timeframe
            records: All feedback records (will be sorted and split)
            current_params: Current parameter values

        Returns:
            OptimizationResult or None if insufficient data.
        """
        # Filter records that include this model
        model_records = [r for r in records if model_name in r.model_probs]

        if len(model_records) < MIN_TRADES:
            logger.info(
                "optuna_insufficient_data",
                model=model_name,
                count=len(model_records),
                required=MIN_TRADES,
            )
            return None

        # Sort by time
        model_records.sort(key=lambda r: r.created_at)

        # Walk-forward split
        train, validate, holdout = _split_walk_forward(model_records)

        if len(train) < 10 or len(validate) < 5:
            return None

        # Get param ranges for this model
        ranges = PARAM_RANGES.get(model_name, {})
        if not ranges:
            return None

        try:
            import optuna
            optuna.logging.set_verbosity(optuna.logging.WARNING)

            def objective(trial):
                # Suggest params within defined ranges
                suggested = {}
                for param_name, (lo, hi) in ranges.items():
                    if isinstance(lo, int) and isinstance(hi, int):
                        suggested[param_name] = trial.suggest_int(param_name, lo, hi)
                    else:
                        suggested[param_name] = trial.suggest_float(param_name, float(lo), float(hi))

                # Simulate: compute pseudo-Brier on train set
                # We approximate by computing how well the params would have predicted
                brier = self._simulate_brier(train, model_name, suggested, current_params)
                return brier

            study = optuna.create_study(direction="minimize")
            study.optimize(objective, n_trials=self._n_trials, show_progress_bar=False)

            best_params = {}
            for param_name, (lo, hi) in ranges.items():
                if param_name in study.best_params:
                    best_params[param_name] = study.best_params[param_name]
                else:
                    best_params[param_name] = current_params.get(param_name, lo)

            # Validate constraints
            valid, reason = validate_params(model_name, best_params)
            if not valid:
                return OptimizationResult(
                    model_name=model_name,
                    timeframe=timeframe,
                    new_params=best_params,
                    train_brier=study.best_value,
                    validate_brier=0.0,
                    holdout_brier=0.0,
                    accepted=False,
                    reject_reason=f"Constraint violation: {reason}",
                    n_trials=self._n_trials,
                    n_trades=len(model_records),
                )

            # Compute Brier on each split
            train_brier = study.best_value
            validate_brier = self._simulate_brier(validate, model_name, best_params, current_params)
            holdout_brier = self._simulate_brier(holdout, model_name, best_params, current_params)

            # Overfit check
            if validate_brier > train_brier + OVERFIT_THRESHOLD:
                return OptimizationResult(
                    model_name=model_name,
                    timeframe=timeframe,
                    new_params=best_params,
                    train_brier=train_brier,
                    validate_brier=validate_brier,
                    holdout_brier=holdout_brier,
                    accepted=False,
                    reject_reason=f"Overfitting: validate ({validate_brier:.4f}) > train ({train_brier:.4f}) + {OVERFIT_THRESHOLD}",
                    n_trials=self._n_trials,
                    n_trades=len(model_records),
                )

            logger.info(
                "optuna_optimization_complete",
                model=model_name,
                timeframe=timeframe,
                train_brier=round(train_brier, 4),
                validate_brier=round(validate_brier, 4),
                holdout_brier=round(holdout_brier, 4),
            )

            return OptimizationResult(
                model_name=model_name,
                timeframe=timeframe,
                new_params=best_params,
                train_brier=train_brier,
                validate_brier=validate_brier,
                holdout_brier=holdout_brier,
                accepted=True,
                n_trials=self._n_trials,
                n_trades=len(model_records),
            )

        except ImportError:
            logger.error("optuna_not_installed")
            return None
        except Exception as exc:
            logger.error("optuna_error", model=model_name, error=str(exc))
            return None

    def _simulate_brier(
        self,
        records: list[FeedbackRecord],
        model_name: str,
        new_params: dict,
        old_params: dict,
    ) -> float:
        """Compute a pseudo-Brier score approximation.

        The approximation works by computing a param distance factor:
        the further new_params are from old_params, the more uncertainty
        we add to the original model prediction. This is a proxy since we
        can't re-run the actual model with new params during optimization.
        """
        if not records:
            return 0.5

        # Compute distance between old and new params (normalized)
        param_distance = 0.0
        n_params = 0
        for key, new_val in new_params.items():
            if key in old_params:
                old_val = old_params[key]
                if old_val != 0:
                    param_distance += abs(new_val - old_val) / abs(old_val)
                n_params += 1
        if n_params > 0:
            param_distance /= n_params

        # Adjustment factor: small changes → similar predictions
        adjustment = param_distance * 0.1

        total_brier = 0.0
        count = 0
        for r in records:
            if model_name in r.model_probs:
                # Adjust prediction slightly based on param distance
                pred = r.model_probs[model_name]
                # Nudge toward 0.5 by adjustment amount
                adjusted = pred + (0.5 - pred) * adjustment
                actual = r.actual_outcome
                total_brier += (adjusted - actual) ** 2
                count += 1

        return total_brier / count if count > 0 else 0.5
