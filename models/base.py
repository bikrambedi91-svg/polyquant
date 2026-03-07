"""Base model interface — ModelParams, ModelOutput, and abstract BaseModel."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd


@dataclass
class ModelParams:
    """Every model's tunable parameters. This is what the learning engine mutates."""

    values: dict  # e.g. {"adx_period": 14, "ema_fast": 20, "ema_slow": 50}
    version: int = 1
    created_at: str = ""
    parent_version: int = 0  # Which version these evolved from (0 = original)
    performance: dict = field(default_factory=lambda: {"brier_30d": 0.25, "trades": 0, "win_rate": 0.0})

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


@dataclass
class ModelOutput:
    """Standard output from every quant model."""

    asset: str
    timeframe: str
    prob_up: float  # 0.0 to 1.0
    confidence: int  # 0 to 100
    model_name: str
    param_version: int
    key_drivers: list[str] = field(default_factory=list)
    raw_indicators: dict = field(default_factory=dict)

    def __post_init__(self):
        self.prob_up = max(0.0, min(1.0, self.prob_up))
        self.confidence = max(0, min(100, self.confidence))


@dataclass
class EnsembleOutput:
    """Output from the ensemble aggregator."""

    asset: str
    timeframe: str
    prob_up: float
    confidence: int
    model_outputs: list[ModelOutput] = field(default_factory=list)
    model_weights_used: dict = field(default_factory=dict)
    disagreement_flags: list[str] = field(default_factory=list)
    param_versions: dict = field(default_factory=dict)


class BaseModel(ABC):
    """Abstract base class for all quant models."""

    def __init__(self, params: ModelParams):
        self.params = params

    @abstractmethod
    async def generate_signal(
        self, asset: str, timeframe: str, ohlcv: pd.DataFrame, **kwargs
    ) -> ModelOutput:
        """Generate a directional signal. Must not raise — return low confidence on failure."""
        pass

    def update_params(self, new_params: ModelParams) -> None:
        """Called by the learning engine when parameters are evolved."""
        self.params = new_params

    def _safe_output(self, asset: str, timeframe: str, model_name: str) -> ModelOutput:
        """Return a neutral, zero-confidence output (used on errors)."""
        return ModelOutput(
            asset=asset,
            timeframe=timeframe,
            prob_up=0.5,
            confidence=0,
            model_name=model_name,
            param_version=self.params.version,
            key_drivers=["error_fallback"],
        )
