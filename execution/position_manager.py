"""Position manager — adaptive TP/SL, excursion tracking, liquidity-checked exits.

CRITICAL: Before any exit, check CLOB has enough liquidity to sell.
If book is too thin, log "exit_failed_no_liquidity" and skip exit.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

import structlog

from config.constants import (
    DEFAULT_SL_PCT,
    DEFAULT_TP_PCT,
)

logger = structlog.get_logger(__name__)


@dataclass
class TPSLLevels:
    """Take-profit and stop-loss price levels."""
    tp_price: float
    sl_price: float
    was_learned: bool = False


@dataclass
class ExitSignal:
    """Signal to exit a position."""
    trade_id: str
    reason: str       # "take_profit", "stop_loss", "time_decay", "edge_evaporated"
    current_price: float
    tp_level: float
    sl_level: float
    available_depth: float = 0.0


class SLTPProvider:
    """Interface for providing TP/SL levels (default or learned)."""

    def get_levels(
        self, asset: str, timeframe: str, regime: str,
        entry_price: float, our_prob: float, action: str,
        confidence: int = 65,
    ) -> TPSLLevels:
        raise NotImplementedError


class DefaultSLTPProvider(SLTPProvider):
    """Returns flat percentage-based TP/SL levels. No tiering, no regime adjustments.

    SL: 4% flat.  TP: 7% flat.

    Math (converts % to YES price levels for DB storage):
      BUY_YES (entry = p):  tp = p*(1+tp_pct), sl = p*(1-sl_pct)
      BUY_NO  (entry = p):  tp = p - tp_pct*(1-p), sl = p + sl_pct*(1-p)
    """

    def get_levels(
        self, asset: str, timeframe: str, regime: str,
        entry_price: float, our_prob: float, action: str,
        confidence: int = 65,
    ) -> TPSLLevels:
        sl_pct = DEFAULT_SL_PCT   # 4% flat
        tp_pct = DEFAULT_TP_PCT   # 7% flat — no tiering, no regime

        if action == "BUY_YES":
            tp_price = min(entry_price * (1.0 + tp_pct), 0.95)
            sl_price = max(entry_price * (1.0 - sl_pct), 0.01)
        else:  # BUY_NO — directions reversed
            no_cost = 1.0 - entry_price
            tp_price = max(entry_price - tp_pct * no_cost, 0.05)
            sl_price = min(entry_price + sl_pct * no_cost, 0.99)

        return TPSLLevels(tp_price=round(tp_price, 4), sl_price=round(sl_price, 4))


class PositionManager:
    """Manages active positions — TP/SL monitoring with liquidity checks."""

    def __init__(self, sl_tp_provider: SLTPProvider | None = None):
        self._provider = sl_tp_provider or DefaultSLTPProvider()

    def calculate_tp_sl(
        self,
        asset: str,
        timeframe: str,
        regime: str,
        entry_price: float,
        our_prob: float,
        action: str,
        confidence: int = 65,
    ) -> TPSLLevels:
        """Calculate TP/SL for a new trade."""
        return self._provider.get_levels(
            asset, timeframe, regime, entry_price, our_prob, action,
            confidence=confidence,
        )

    async def monitor_positions(
        self,
        active_positions: list[dict],
        get_current_price,
        get_book_depth,
    ) -> list[ExitSignal]:
        """Check all active positions for TP/SL/time triggers.

        Args:
            active_positions: list of trade dicts with keys:
                trade_id, asset, timeframe, action, entry_price, size_usd,
                tp_level, sl_level, our_prob, end_datetime,
                max_adverse_excursion, max_favorable_excursion
            get_current_price: async callable(token_id) → float
            get_book_depth: async callable(token_id, size_usd) → float (available depth in USD)

        Returns:
            List of ExitSignal for positions that should be exited.
        """
        signals = []

        for pos in active_positions:
            try:
                token_id = pos.get("token_id_yes", "")
                trade_id = pos["trade_id"]
                action = pos["action"]
                entry_price = pos["entry_price"]
                size_usd = pos["size_usd"]
                tp_level = pos["tp_level"]
                sl_level = pos["sl_level"]

                # 1. Fetch current price
                current_price = await get_current_price(token_id)
                if current_price <= 0:
                    continue

                # 2. Update excursions
                mae = pos.get("max_adverse_excursion") or 0.0
                mfe = pos.get("max_favorable_excursion") or 0.0

                if action == "BUY_YES":
                    adverse = entry_price - current_price
                    favorable = current_price - entry_price
                else:
                    adverse = current_price - entry_price
                    favorable = entry_price - current_price

                pos["max_adverse_excursion"] = max(mae, adverse)
                pos["max_favorable_excursion"] = max(mfe, favorable)

                # 3. Check TP/SL triggers
                exit_reason = None
                if action == "BUY_YES":
                    if current_price >= tp_level:
                        exit_reason = "take_profit"
                    elif current_price <= sl_level:
                        exit_reason = "stop_loss"
                else:  # BUY_NO
                    if current_price <= tp_level:
                        exit_reason = "take_profit"
                    elif current_price >= sl_level:
                        exit_reason = "stop_loss"

                # Time decay check
                if not exit_reason:
                    end_dt = pos.get("end_datetime")
                    if end_dt:
                        now = datetime.now(timezone.utc)
                        if isinstance(end_dt, str):
                            end_dt = datetime.fromisoformat(end_dt.replace("Z", "+00:00"))
                        remaining = (end_dt - now).total_seconds()
                        total_duration = pos.get("total_duration_seconds", 300)
                        if total_duration > 0:
                            pct_remaining = remaining / total_duration
                            if pct_remaining <= 0.05:
                                exit_reason = "time_decay"

                if not exit_reason:
                    continue

                # 4. CRITICAL: Check CLOB liquidity before exit
                available_depth = await get_book_depth(token_id, size_usd)
                if available_depth < size_usd:
                    logger.warning(
                        "exit_failed_no_liquidity",
                        trade_id=trade_id,
                        reason=exit_reason,
                        available=available_depth,
                        needed=size_usd,
                        msg=f"Cannot exit trade {trade_id}: insufficient book depth "
                            f"(${available_depth:.0f} available, need ${size_usd:.0f})",
                    )
                    continue

                signals.append(ExitSignal(
                    trade_id=trade_id,
                    reason=exit_reason,
                    current_price=current_price,
                    tp_level=tp_level,
                    sl_level=sl_level,
                    available_depth=available_depth,
                ))

            except Exception as exc:
                logger.error(
                    "position_monitor_error",
                    trade_id=pos.get("trade_id"),
                    error=str(exc),
                )

        return signals
