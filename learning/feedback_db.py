"""Trade feedback record storage — captures everything needed for learning.

Each FeedbackRecord captures the full context of a trade: model signals,
parameters used, entry/exit details, MAE/MFE, oracle prices, and fees.
Query by (asset, timeframe, regime) buckets for learning.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class FeedbackRecord:
    """Complete trade outcome record for the learning engine."""

    trade_id: str
    asset: str
    timeframe: str
    action: str                     # BUY_YES or BUY_NO
    regime: str                     # RISK_ON, RISK_OFF, etc.

    # Prices
    entry_price: float
    exit_price: float
    size_usd: float

    # Model signals at entry
    ensemble_prob: float            # Our predicted probability
    model_probs: dict = field(default_factory=dict)  # model_name -> prob_up
    model_confidences: dict = field(default_factory=dict)  # model_name -> confidence
    param_versions: dict = field(default_factory=dict)  # model_name -> version

    # Market context at entry
    market_implied: float = 0.5
    edge_at_entry: float = 0.0
    confidence: int = 50

    # Outcome
    result: str = ""                # WON, LOST
    pnl_usd: float = 0.0
    exit_reason: str = ""           # take_profit, stop_loss, resolution, time_decay

    # Excursions (worst/best price reached during trade)
    max_adverse_excursion: float = 0.0
    max_favorable_excursion: float = 0.0

    # Oracle data (for Chainlink-resolved markets)
    oracle_start_price: Optional[float] = None
    oracle_end_price: Optional[float] = None

    # Fee tracking
    taker_fee_paid: float = 0.0

    # TP/SL used
    tp_level: float = 0.0
    sl_level: float = 0.0
    was_sl_learned: bool = False
    would_have_won_if_held: Optional[bool] = None

    # Liquidity context
    book_depth_at_entry: float = 0.0
    book_depth_at_exit: float = 0.0

    # Timestamps
    created_at: str = ""
    resolved_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    @property
    def actual_outcome(self) -> float:
        """1.0 if the event resolved UP, 0.0 if DOWN. For Brier score calc."""
        if self.action == "BUY_YES":
            return 1.0 if self.result == "WON" else 0.0
        else:  # BUY_NO
            return 0.0 if self.result == "WON" else 1.0

    @property
    def brier_contribution(self) -> float:
        """Brier score for this single trade: (forecast - outcome)^2."""
        return (self.ensemble_prob - self.actual_outcome) ** 2


class FeedbackStore:
    """In-memory store for FeedbackRecords with bucket queries.

    Records are stored in-memory and can be queried by (asset, timeframe, regime).
    """

    def __init__(self):
        self._records: list[FeedbackRecord] = []

    @property
    def total_trades(self) -> int:
        return len(self._records)

    def store(self, record: FeedbackRecord) -> None:
        """Store a feedback record."""
        self._records.append(record)
        logger.info(
            "feedback_stored",
            trade_id=record.trade_id,
            asset=record.asset,
            timeframe=record.timeframe,
            result=record.result,
            total_records=len(self._records),
        )

    def get_all(self) -> list[FeedbackRecord]:
        """Return all stored records."""
        return list(self._records)

    def get_by_bucket(
        self,
        asset: str | None = None,
        timeframe: str | None = None,
        regime: str | None = None,
    ) -> list[FeedbackRecord]:
        """Query records by (asset, timeframe, regime) bucket.

        Any parameter left None is treated as a wildcard.
        """
        results = self._records
        if asset is not None:
            results = [r for r in results if r.asset == asset]
        if timeframe is not None:
            results = [r for r in results if r.timeframe == timeframe]
        if regime is not None:
            results = [r for r in results if r.regime == regime]
        return results

    def get_by_model(self, model_name: str) -> list[FeedbackRecord]:
        """Return records where a specific model contributed a signal."""
        return [r for r in self._records if model_name in r.model_probs]

    def get_recent(self, n: int) -> list[FeedbackRecord]:
        """Return the N most recent records."""
        return self._records[-n:]

    def compute_brier_score(
        self,
        model_name: str | None = None,
        asset: str | None = None,
        timeframe: str | None = None,
    ) -> float | None:
        """Compute Brier score. If model_name given, uses that model's prob.

        Returns None if no records match.
        """
        records = self.get_by_bucket(asset=asset, timeframe=timeframe)

        if model_name:
            records = [r for r in records if model_name in r.model_probs]
            if not records:
                return None
            return sum(
                (r.model_probs[model_name] - r.actual_outcome) ** 2
                for r in records
            ) / len(records)
        else:
            # Ensemble Brier
            if not records:
                return None
            return sum(r.brier_contribution for r in records) / len(records)

    def compute_win_rate(
        self,
        asset: str | None = None,
        timeframe: str | None = None,
        regime: str | None = None,
    ) -> float | None:
        """Compute win rate for a bucket. Returns None if no records."""
        records = self.get_by_bucket(asset, timeframe, regime)
        if not records:
            return None
        wins = sum(1 for r in records if r.result == "WON")
        return wins / len(records)

    def compute_total_pnl(
        self,
        asset: str | None = None,
        timeframe: str | None = None,
    ) -> float:
        """Compute total P&L for a bucket."""
        records = self.get_by_bucket(asset, timeframe)
        return sum(r.pnl_usd for r in records)

    def is_cold_start(self) -> bool:
        """True if fewer than 50 trades — learning engine should be dormant."""
        return len(self._records) < 50

    def is_optuna_ready(self) -> bool:
        """True if 80+ trades — enough for param optimization."""
        return len(self._records) >= 80
