"""Paper trading engine — simulated execution with real CLOB prices.

Simulates fills by walking the order book. Calculates and stores taker_fee_paid.
On resolution, retroactively sets would_have_won_if_held for early exits.
"""

import uuid
from datetime import datetime, timezone

import structlog

from config.constants import TAKER_FEE_MAX
from database.trades import create_trade, update_trade, get_trade, get_active_trades

logger = structlog.get_logger(__name__)


def _calculate_taker_fee(price: float, timeframe: str) -> float:
    """Fee = max_fee × 2 × price × (1 - price)."""
    max_fee = TAKER_FEE_MAX.get(timeframe, 0.0)
    return max_fee * 2.0 * price * (1.0 - price)


class PaperEngine:
    """Simulated execution engine for paper trading."""

    def __init__(self, db_session, orderbook_analyzer=None):
        self._db = db_session
        self._ob = orderbook_analyzer

    async def execute_buy(
        self,
        asset: str,
        timeframe: str,
        action: str,
        size_usd: float,
        our_prob: float,
        market_implied: float,
        edge: float,
        confidence: int,
        tp_level: float,
        sl_level: float,
        regime: str,
        token_id: str = "",
        market_title: str = "",
        market_url: str = "",
        market_type: str = "up_down",
        param_versions: dict | None = None,
        was_sl_learned: bool = False,
        end_datetime: datetime | None = None,
    ) -> dict | None:
        """Simulate a buy by walking the book. Returns trade dict or None."""
        # ── ALL TIMEFRAMES: MAKER-ONLY ENTRY ──
        # GTC limit buy one tick below best ask. Maker fee = 0% + USDC rebates.
        # Taker fees are now 1.56% on ALL markets — maker avoids this entirely.
        # In paper mode: assume fill at best_ask - 0.01 (one tick below).
        fill_price = market_implied
        slippage = 0.0
        taker_fee_usd = 0.0  # Maker entry = $0 fee

        if self._ob and token_id:
            try:
                snap = await self._ob.analyze(token_id, size_usd)
                if snap.best_ask and snap.best_ask > 0:
                    fill_price = snap.best_ask - 0.01  # One tick below ask = maker

                    # Spread filter: reject if bid-ask spread too wide (maker fill unlikely in live)
                    from config.constants import MAX_ENTRY_SPREAD
                    if snap.best_bid and snap.best_bid > 0:
                        spread = snap.best_ask - snap.best_bid
                        if spread > MAX_ENTRY_SPREAD:
                            logger.warning(
                                "paper_fill_rejected_spread",
                                asset=asset,
                                action=action,
                                spread=round(spread, 4),
                                max_allowed=MAX_ENTRY_SPREAD,
                                best_bid=snap.best_bid,
                                best_ask=snap.best_ask,
                            )
                            return None  # Spread too wide — maker fill unlikely
                elif snap.avg_fill_price > 0:
                    fill_price = snap.avg_fill_price - 0.01
            except Exception as exc:
                logger.warning("paper_maker_book_error", error=str(exc))

        logger.info("paper_maker_entry", asset=asset, timeframe=timeframe, fill=round(fill_price, 4))

        # Reject trade if fill deviates too far from midpoint
        MAX_FILL_DEVIATION = {
            "5m": 0.05,
            "15m": 0.03,    # Tighter for 15m maker
            "1h": 0.05,
            "4h": 0.05,
        }.get(timeframe, 0.05)
        fill_dev = abs(fill_price - market_implied)
        if fill_dev > MAX_FILL_DEVIATION:
            logger.warning(
                "paper_fill_rejected_slippage",
                asset=asset,
                action=action,
                fill_price=fill_price,
                market_implied=market_implied,
                deviation=round(fill_dev, 4),
                max_allowed=MAX_FILL_DEVIATION,
            )
            return None  # Book too thin — skip trade entirely

        trade_id = f"PAPER-{uuid.uuid4().hex[:12].upper()}"

        import json
        param_versions_json = json.dumps(param_versions) if param_versions else None

        trade = create_trade(
            self._db,
            trade_id=trade_id,
            asset=asset,
            timeframe=timeframe,
            action=action,
            entry_price=fill_price,
            size_usd=size_usd,
            your_prob=our_prob,
            market_implied=market_implied,
            edge_at_entry=edge,
            confidence=confidence,
            tp_level=tp_level,
            sl_level=sl_level,
            regime_at_entry=regime,
            taker_fee_paid=taker_fee_usd,
            was_sl_learned=was_sl_learned,
            market_title=market_title,
            market_url=market_url,
            market_type=market_type,
            param_versions_json=param_versions_json,
        )

        logger.info(
            "paper_buy_executed",
            trade_id=trade_id,
            asset=asset,
            action=action,
            fill_price=fill_price,
            size_usd=size_usd,
            fee_usd=round(taker_fee_usd, 4),
        )

        return {
            "trade_id": trade_id,
            "fill_price": fill_price,
            "taker_fee_usd": taker_fee_usd,
            "slippage": slippage,
        }

    async def execute_sell(
        self,
        trade_id: str,
        exit_price: float,
        exit_reason: str,
    ) -> dict | None:
        """Simulate selling a position. Computes P&L including fees."""
        trade = get_trade(self._db, trade_id)
        if not trade:
            logger.error("paper_sell_trade_not_found", trade_id=trade_id)
            return None
        if trade.status != "ACTIVE":
            logger.info("paper_sell_already_closed", trade_id=trade_id, status=trade.status)
            return None

        # Calculate exit fee: TP = maker limit sell (0%), SL/timeout = taker market sell
        if exit_reason == "take_profit":
            exit_fee = 0.0  # Pre-placed maker limit sell — 0% fee + USDC rebates
        else:
            exit_fee = _calculate_taker_fee(exit_price, trade.timeframe)  # Taker emergency exit
        exit_fee_usd = exit_fee * trade.size_usd

        # P&L calculation: shares = size_usd / cost_per_share
        if trade.action == "BUY_YES":
            # Bought YES at entry_price (YES price)
            shares = trade.size_usd / trade.entry_price if trade.entry_price > 0 else 0
            pnl_usd = (exit_price - trade.entry_price) * shares
        else:
            # Bought NO at (1 - entry_price) where entry_price is YES price
            no_entry = 1.0 - trade.entry_price
            shares = trade.size_usd / no_entry if no_entry > 0 else 0
            no_exit = 1.0 - exit_price
            pnl_usd = (no_exit - no_entry) * shares

        # Subtract exit fee (entry fee already deducted at entry)
        pnl_usd -= exit_fee_usd

        result = "WON" if pnl_usd > 0 else "LOST"

        now = datetime.now(timezone.utc)
        update_trade(
            self._db,
            trade_id,
            exit_price=exit_price,
            pnl_usd=round(pnl_usd, 4),
            result=result,
            status="CLOSED",
            exit_reason=exit_reason,
            resolved_at=now,
        )

        logger.info(
            "paper_sell_executed",
            trade_id=trade_id,
            exit_price=exit_price,
            pnl_usd=round(pnl_usd, 4),
            exit_reason=exit_reason,
        )

        return {
            "trade_id": trade_id,
            "exit_price": exit_price,
            "pnl_usd": round(pnl_usd, 4),
            "exit_fee_usd": exit_fee_usd,
            "result": result,
        }

    async def check_resolution(
        self,
        trade_id: str,
        resolved_up: bool,
    ) -> dict | None:
        """Handle market resolution — compute final P&L.

        Also retroactively sets would_have_won_if_held for early exits.
        """
        trade = get_trade(self._db, trade_id)
        if not trade:
            return None

        # Determine if holding would have won
        if trade.action == "BUY_YES":
            would_have_won = resolved_up
        else:
            would_have_won = not resolved_up

        now = datetime.now(timezone.utc)

        if trade.status == "CLOSED":
            # Already exited early (TP/SL/time_decay) — just set retroactive flag
            update_trade(
                self._db,
                trade_id,
                would_have_won_if_held=would_have_won,
            )
            return {
                "trade_id": trade_id,
                "already_closed": True,
                "would_have_won_if_held": would_have_won,
                "original_result": trade.result,
            }

        # Still active — resolve now. Shares = investment / cost_per_share
        if trade.action == "BUY_YES":
            shares = trade.size_usd / trade.entry_price if trade.entry_price > 0 else 0
            if resolved_up:
                # YES wins: each share pays $1
                exit_price = 1.0
                pnl_usd = (1.0 - trade.entry_price) * shares - trade.taker_fee_paid
            else:
                # YES loses: each share pays $0
                exit_price = 0.0
                pnl_usd = -trade.entry_price * shares - trade.taker_fee_paid
        else:  # BUY_NO
            no_entry = 1.0 - trade.entry_price
            shares = trade.size_usd / no_entry if no_entry > 0 else 0
            if not resolved_up:
                # NO wins: each share pays $1
                exit_price = 0.0  # YES price → 0 means NO wins
                pnl_usd = (1.0 - no_entry) * shares - trade.taker_fee_paid
            else:
                # NO loses: each share pays $0
                exit_price = 1.0
                pnl_usd = -no_entry * shares - trade.taker_fee_paid

        result = "WON" if pnl_usd > 0 else "LOST"

        update_trade(
            self._db,
            trade_id,
            exit_price=exit_price,
            pnl_usd=round(pnl_usd, 4),
            result=result,
            status="RESOLVED",
            exit_reason="resolution",
            resolved_at=now,
            would_have_won_if_held=would_have_won,
        )

        logger.info(
            "paper_resolution",
            trade_id=trade_id,
            resolved_up=resolved_up,
            pnl_usd=round(pnl_usd, 4),
            result=result,
        )

        return {
            "trade_id": trade_id,
            "resolved_up": resolved_up,
            "pnl_usd": round(pnl_usd, 4),
            "result": result,
            "would_have_won_if_held": would_have_won,
        }
