"""Adaptive SL/TP optimizer — learns optimal percentage levels from MAE/MFE data.

Simulates SL percentages 0.02-0.15 against actual MAE data (converted to %).
When simulating exits, also considers whether there was sufficient
book depth to actually execute (don't optimize for SL levels that
assume perfect execution in illiquid conditions).

Safety: max SL/TP change per cycle = 0.03 (3 percentage points).
Min 30 trades per (asset, timeframe, regime) bucket before learning.
"""

from dataclasses import dataclass

import structlog

from config.constants import (
    DEFAULT_SL_PCT,
    LEARNING_SAFETY_RAILS,
    REGIME_ADJUSTMENTS,
    get_tp_pct_for_confidence,
)
from execution.position_manager import SLTPProvider, TPSLLevels

logger = structlog.get_logger(__name__)

MIN_TRADES = LEARNING_SAFETY_RAILS["min_trades_for_sl_optimization"]  # 30
MAX_SL_CHANGE = LEARNING_SAFETY_RAILS["max_sl_change_per_cycle"]      # 0.03
MAX_TP_CHANGE = LEARNING_SAFETY_RAILS["max_tp_change_per_cycle"]      # 0.03
SL_PCT_RANGE = [round(0.02 + i * 0.01, 2) for i in range(14)]  # 0.02 to 0.15
TP_PCT_RANGE = [round(0.02 + i * 0.02, 2) for i in range(20)]  # 0.02 to 0.40


@dataclass
class SLTPResult:
    """Result of SL/TP optimization for a bucket (percentage-based)."""
    asset: str
    timeframe: str
    regime: str
    optimal_sl_pct: float
    optimal_tp_pct: float
    simulated_pnl: float
    trade_count: int
    was_clamped: bool = False  # True if max change cap was applied


@dataclass
class TradeData:
    """Minimal trade data needed for SL/TP simulation."""
    entry_price: float
    exit_price: float
    action: str                 # BUY_YES or BUY_NO
    our_prob: float
    max_adverse_excursion: float
    max_favorable_excursion: float
    pnl_usd: float
    size_usd: float
    book_depth_at_exit: float   # For liquidity-aware simulation
    result: str                 # WON or LOST


class SLTPLearner:
    """Learns optimal SL/TP percentages from historical trade data per bucket."""

    def __init__(self, min_liquidity: float = 0.0):
        # Learned levels: (asset, tf, regime) -> {"sl_pct": float, "tp_pct": float}
        self._learned: dict[tuple[str, str, str], dict[str, float]] = {}
        self._min_liquidity = min_liquidity

    def optimize(
        self,
        trades: list[TradeData],
        asset: str,
        timeframe: str,
        regime: str,
        current_sl_pct: float | None = None,
        current_tp_pct: float | None = None,
    ) -> SLTPResult | None:
        """Run SL/TP optimization on trade data for a bucket.

        Returns None if insufficient data (< 30 trades).
        """
        if len(trades) < MIN_TRADES:
            logger.info(
                "sl_tp_insufficient_data",
                asset=asset, timeframe=timeframe, regime=regime,
                count=len(trades), required=MIN_TRADES,
            )
            return None

        # Current reference levels (percentages)
        if current_sl_pct is None:
            current_sl_pct = DEFAULT_SL_PCT
        if current_tp_pct is None:
            current_tp_pct = get_tp_pct_for_confidence(65)  # default low tier

        # Find optimal SL % via simulation
        best_sl_pct = current_sl_pct
        best_sl_pnl = float("-inf")

        for sl_pct in SL_PCT_RANGE:
            pnl = self._simulate_sl(trades, sl_pct)
            if pnl > best_sl_pnl:
                best_sl_pnl = pnl
                best_sl_pct = sl_pct

        # Find optimal TP % via MFE simulation
        best_tp_pct = current_tp_pct
        best_tp_pnl = float("-inf")

        for tp_pct in TP_PCT_RANGE:
            pnl = self._simulate_tp(trades, tp_pct)
            if pnl > best_tp_pnl:
                best_tp_pnl = pnl
                best_tp_pct = tp_pct

        # Clamp changes to max per cycle (3 percentage points)
        was_clamped = False
        sl_change = best_sl_pct - current_sl_pct
        if abs(sl_change) > MAX_SL_CHANGE:
            best_sl_pct = current_sl_pct + MAX_SL_CHANGE * (1 if sl_change > 0 else -1)
            was_clamped = True

        tp_change = best_tp_pct - current_tp_pct
        if abs(tp_change) > MAX_TP_CHANGE:
            best_tp_pct = current_tp_pct + MAX_TP_CHANGE * (1 if tp_change > 0 else -1)
            was_clamped = True

        # Clamp to valid percentage range
        best_sl_pct = max(0.02, min(0.15, round(best_sl_pct, 4)))
        best_tp_pct = max(0.02, min(0.40, round(best_tp_pct, 4)))

        # Store learned values
        key = (asset, timeframe, regime)
        self._learned[key] = {"sl_pct": best_sl_pct, "tp_pct": best_tp_pct}

        result = SLTPResult(
            asset=asset,
            timeframe=timeframe,
            regime=regime,
            optimal_sl_pct=best_sl_pct,
            optimal_tp_pct=best_tp_pct,
            simulated_pnl=best_sl_pnl + best_tp_pnl,
            trade_count=len(trades),
            was_clamped=was_clamped,
        )

        logger.info(
            "sl_tp_optimized",
            asset=asset, timeframe=timeframe, regime=regime,
            sl_pct=best_sl_pct, tp_pct=best_tp_pct,
            prev_sl_pct=current_sl_pct, prev_tp_pct=current_tp_pct,
            was_clamped=was_clamped,
        )

        return result

    def _simulate_sl(self, trades: list[TradeData], sl_pct: float) -> float:
        """Simulate total P&L if SL had been set at sl_pct of position value.

        Converts each trade's MAE to a percentage of cost basis before comparing.
        Liquidity check: if book_depth < size_usd, skip that exit.
        """
        total_pnl = 0.0

        for t in trades:
            # Convert MAE to percentage of cost basis
            if t.action == "BUY_YES":
                cost_basis = t.entry_price
            else:
                cost_basis = 1.0 - t.entry_price
            mae_pct = t.max_adverse_excursion / cost_basis if cost_basis > 0 else 0.0

            # Would SL have triggered?
            if mae_pct >= sl_pct:
                # Liquidity check
                if self._min_liquidity > 0 and t.book_depth_at_exit < t.size_usd:
                    total_pnl += t.pnl_usd
                    continue

                # Simulate SL exit: loss = sl_pct * size
                sl_pnl = -sl_pct * t.size_usd
                total_pnl += sl_pnl
            else:
                total_pnl += t.pnl_usd

        return total_pnl

    def _simulate_tp(self, trades: list[TradeData], tp_pct: float) -> float:
        """Simulate total P&L if TP had been set at tp_pct of position value.

        Converts each trade's MFE to a percentage of cost basis before comparing.
        """
        total_pnl = 0.0

        for t in trades:
            # Convert MFE to percentage of cost basis
            if t.action == "BUY_YES":
                cost_basis = t.entry_price
            else:
                cost_basis = 1.0 - t.entry_price
            mfe_pct = t.max_favorable_excursion / cost_basis if cost_basis > 0 else 0.0

            # Would TP have triggered?
            if mfe_pct >= tp_pct:
                tp_pnl = tp_pct * t.size_usd
                total_pnl += tp_pnl
            else:
                total_pnl += t.pnl_usd

        return total_pnl

    def get_learned_levels(
        self, asset: str, timeframe: str, regime: str,
    ) -> dict[str, float] | None:
        """Return learned SL/TP percentages for a bucket, or None if not learned."""
        return self._learned.get((asset, timeframe, regime))

    def has_learned(self, asset: str, timeframe: str, regime: str) -> bool:
        """Check if we have learned levels for this bucket."""
        return (asset, timeframe, regime) in self._learned


class LearnedSLTPProvider(SLTPProvider):
    """SLTPProvider that uses learned percentage levels when available, defaults otherwise."""

    def __init__(self, learner: SLTPLearner):
        self._learner = learner

    def get_levels(
        self,
        asset: str,
        timeframe: str,
        regime: str,
        entry_price: float,
        our_prob: float,
        action: str,
        confidence: int = 65,
    ) -> TPSLLevels:
        learned = self._learner.get_learned_levels(asset, timeframe, regime)

        if learned:
            sl_pct = learned["sl_pct"]
            tp_pct = learned["tp_pct"]
            was_learned = True
        else:
            sl_pct = DEFAULT_SL_PCT
            tp_pct = get_tp_pct_for_confidence(confidence)
            was_learned = False

        # Apply regime adjustments (multipliers on the percentages)
        adj = REGIME_ADJUSTMENTS.get(regime, {"sl_mult": 1.0, "tp_mult": 1.0})
        sl_pct *= adj["sl_mult"]
        tp_pct *= adj["tp_mult"]

        if action == "BUY_YES":
            tp_price = min(entry_price * (1.0 + tp_pct), 0.95)
            sl_price = max(entry_price * (1.0 - sl_pct), 0.01)
        else:  # BUY_NO
            no_cost = 1.0 - entry_price
            tp_price = max(entry_price - tp_pct * no_cost, 0.05)
            sl_price = min(entry_price + sl_pct * no_cost, 0.99)

        return TPSLLevels(
            tp_price=round(tp_price, 4),
            sl_price=round(sl_price, 4),
            was_learned=was_learned,
        )
