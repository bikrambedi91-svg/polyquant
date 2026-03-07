"""Bayesian ensemble aggregator — weighted combination of all model signals.

Weight = default_weight × brier_weight × (confidence / 70).
Models with confidence=0 get effective weight 0 (auto-disabled).
Flags disagreements where any model differs from ensemble by >12%.
COLD START: For first 50 trades (no Brier data), use DEFAULT weights only.
"""

import structlog

from config.constants import DEFAULT_MODEL_WEIGHTS
from models.base import ModelOutput, EnsembleOutput

logger = structlog.get_logger(__name__)

DISAGREEMENT_THRESHOLD = 0.12
CONFIDENCE_NORMALIZER = 70.0


class EnsembleAggregator:
    def __init__(self, brier_weights: dict[str, float] | None = None):
        """Initialize with optional per-model Brier accuracy weights.

        brier_weights: {"MomRegime": 1.1, "FundBasis": 0.9, ...}
        Higher = model has been more accurate. Default 1.0 during cold start.
        """
        self.brier_weights = brier_weights or {}

    def aggregate(
        self, signals: list[ModelOutput], timeframe: str
    ) -> EnsembleOutput:
        """Aggregate model signals into a single ensemble output."""
        if not signals:
            return EnsembleOutput(
                asset="", timeframe=timeframe, prob_up=0.5, confidence=0,
            )

        asset = signals[0].asset
        default_weights = DEFAULT_MODEL_WEIGHTS.get(timeframe, {})

        # Compute effective weight for each signal
        weighted_probs = []
        total_weight = 0.0
        weights_used = {}
        param_versions = {}

        for sig in signals:
            # Default weight for this model at this timeframe
            dw = default_weights.get(sig.model_name, 0.0)

            # Brier accuracy weight (default 1.0 during cold start)
            bw = self.brier_weights.get(sig.model_name, 1.0)

            # Confidence scalar (models returning confidence=0 get zero weight)
            cs = sig.confidence / CONFIDENCE_NORMALIZER

            effective_weight = dw * bw * cs

            if effective_weight > 0:
                weighted_probs.append((sig.prob_up, effective_weight))
                total_weight += effective_weight

            weights_used[sig.model_name] = effective_weight
            param_versions[sig.model_name] = sig.param_version

        if total_weight == 0:
            return EnsembleOutput(
                asset=asset, timeframe=timeframe, prob_up=0.5, confidence=0,
                model_outputs=signals, model_weights_used=weights_used,
                param_versions=param_versions,
            )

        # Weighted average prob_up
        ensemble_prob = sum(p * w for p, w in weighted_probs) / total_weight

        # Ensemble confidence: penalized by inter-model variance
        valid_probs = [p for p, w in weighted_probs if w > 0]
        if len(valid_probs) > 1:
            mean_p = ensemble_prob
            variance = sum((p - mean_p) ** 2 for p in valid_probs) / len(valid_probs)
            # Higher variance = less agreement = lower confidence
            agreement_penalty = min(variance * 400, 30)  # Cap at 30 point penalty
        else:
            agreement_penalty = 10  # Single model → lower confidence

        # Base confidence from weighted average of model confidences
        weighted_conf = sum(
            sig.confidence * weights_used.get(sig.model_name, 0)
            for sig in signals
        )
        base_confidence = weighted_conf / total_weight if total_weight > 0 else 0
        ensemble_confidence = max(0, min(100, int(base_confidence - agreement_penalty)))

        # Flag disagreements: any model differs from ensemble by > 12%
        disagreement_flags = []
        for sig in signals:
            if weights_used.get(sig.model_name, 0) > 0:
                diff = abs(sig.prob_up - ensemble_prob)
                if diff > DISAGREEMENT_THRESHOLD:
                    disagreement_flags.append(
                        f"{sig.model_name}: {sig.prob_up:.2f} vs ensemble {ensemble_prob:.2f} "
                        f"(diff={diff:.2f})"
                    )

        if disagreement_flags:
            logger.warning(
                "ensemble_disagreement",
                asset=asset,
                timeframe=timeframe,
                flags=disagreement_flags,
            )

        return EnsembleOutput(
            asset=asset,
            timeframe=timeframe,
            prob_up=max(0.0, min(1.0, ensemble_prob)),
            confidence=ensemble_confidence,
            model_outputs=signals,
            model_weights_used=weights_used,
            disagreement_flags=disagreement_flags,
            param_versions=param_versions,
        )
