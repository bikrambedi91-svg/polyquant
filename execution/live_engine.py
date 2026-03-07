"""Live trading engine — real execution via py_clob_client.

IMPORTANT: Must call client.set_api_creds(client.create_or_derive_api_creds())
before placing any orders. Uses EIP-712 signatures on Polygon (chain_id=137).

Fill confirmation: After placing a GTC maker order, polls order status for up to
FILL_TIMEOUT_SECONDS. If not filled, cancels the order and returns None.
"""

import asyncio
import uuid
from datetime import datetime, timezone

import structlog

from config.constants import TAKER_FEE_MAX
from config.settings import Settings
from database.trades import create_trade, update_trade, get_trade

logger = structlog.get_logger(__name__)


def _calculate_taker_fee(price: float, timeframe: str) -> float:
    max_fee = TAKER_FEE_MAX.get(timeframe, 0.0)
    return max_fee * 2.0 * price * (1.0 - price)


# Fill confirmation: poll order status every 2s for up to 30s
FILL_POLL_INTERVAL = 2.0  # seconds between status checks
FILL_TIMEOUT_SECONDS = 30  # cancel unfilled orders after this


class LiveEngine:
    """Real execution engine using py_clob_client."""

    def __init__(self, settings: Settings, db_session):
        self._settings = settings
        self._db = db_session
        self._client = None
        self._fill_attempts = 0
        self._fill_confirmed = 0
        self._fill_cancelled = 0

    def _get_client(self):
        """Lazy-init authenticated ClobClient."""
        if self._client is None:
            from py_clob_client.client import ClobClient

            self._client = ClobClient(
                "https://clob.polymarket.com",
                key=self._settings.POLY_PRIVATE_KEY,
                chain_id=self._settings.POLY_CHAIN_ID,
                signature_type=self._settings.POLY_SIGNATURE_TYPE,
                funder=self._settings.POLY_FUNDER_ADDRESS,
            )
            self._client.set_api_creds(
                self._client.create_or_derive_api_creds()
            )
            logger.info("live_clob_client_initialized")
        return self._client

    async def _wait_for_fill(self, order_id: str) -> dict | None:
        """Poll order status until filled or timeout.

        Returns order details if filled, None if timed out (order cancelled).
        """
        client = self._get_client()
        elapsed = 0.0
        self._fill_attempts += 1

        while elapsed < FILL_TIMEOUT_SECONDS:
            try:
                order = client.get_order(order_id)
                status = getattr(order, "status", None) or order.get("status", "")
                size_matched = getattr(order, "size_matched", 0) or order.get("size_matched", 0)

                if status == "MATCHED" or float(size_matched) > 0:
                    self._fill_confirmed += 1
                    avg_price = getattr(order, "average_price", None) or order.get("average_price")
                    logger.info("live_order_filled",
                                order_id=order_id,
                                size_matched=size_matched,
                                avg_price=avg_price,
                                wait_seconds=round(elapsed, 1))
                    return {
                        "status": "filled",
                        "size_matched": float(size_matched),
                        "average_price": float(avg_price) if avg_price else None,
                    }

                if status in ("CANCELLED", "EXPIRED"):
                    logger.warning("live_order_cancelled_externally",
                                   order_id=order_id, status=status)
                    return None

            except Exception as exc:
                logger.warning("live_fill_check_error",
                               order_id=order_id, error=str(exc))

            await asyncio.sleep(FILL_POLL_INTERVAL)
            elapsed += FILL_POLL_INTERVAL

        # Timeout: cancel the unfilled order
        try:
            client.cancel(order_id)
            self._fill_cancelled += 1
            logger.warning("live_order_timeout_cancelled",
                           order_id=order_id,
                           timeout=FILL_TIMEOUT_SECONDS)
        except Exception as exc:
            logger.error("live_cancel_failed",
                         order_id=order_id, error=str(exc))
        return None

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
        price: float = 0.0,
        market_title: str = "",
        market_url: str = "",
        param_versions: dict | None = None,
        was_sl_learned: bool = False,
    ) -> dict | None:
        """Place a maker GTC limit order on Polymarket CLOB.

        All timeframes use maker orders (0% fee + USDC rebates).
        Price should be set to best_ask - 0.01 by the caller.
        """
        client = self._get_client()

        try:
            from py_clob_client.clob_types import OrderArgs, OrderType
            from py_clob_client.order_builder.constants import BUY

            # Maker entry: GTC limit at price (should be <= best_ask - 0.01)
            maker_price = price or market_implied
            shares = size_usd / maker_price if maker_price > 0 else 0

            order = client.create_order(OrderArgs(
                token_id=token_id,
                price=maker_price,
                size=shares,
                side=BUY,
            ))
            resp = client.post_order(order, OrderType.GTC)

            # Extract order ID for fill tracking
            order_id = None
            if isinstance(resp, dict):
                order_id = resp.get("orderID") or resp.get("id")
            elif hasattr(resp, "orderID"):
                order_id = resp.orderID

            # Wait for fill confirmation before recording trade
            if order_id:
                fill_result = await self._wait_for_fill(order_id)
                if fill_result is None:
                    logger.warning("live_buy_not_filled",
                                   asset=asset, action=action,
                                   maker_price=maker_price)
                    return None  # Order cancelled, no trade recorded
                # Use actual fill price if available
                fill_price = fill_result.get("average_price") or maker_price
            else:
                # No order ID available — assume immediate fill (legacy behavior)
                fill_price = maker_price
                logger.warning("live_buy_no_order_id",
                               asset=asset, resp=str(resp)[:200])

            # Maker entry = 0% fee (+ earns daily USDC rebates)
            taker_fee_usd = 0.0

            trade_id = f"LIVE-{uuid.uuid4().hex[:12].upper()}"

            import json
            param_versions_json = json.dumps(param_versions) if param_versions else None

            create_trade(
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
                param_versions_json=param_versions_json,
            )

            logger.info(
                "live_buy_executed",
                trade_id=trade_id,
                asset=asset,
                action=action,
                fill_price=fill_price,
                size_usd=size_usd,
                order_id=order_id,
            )

            return {
                "trade_id": trade_id,
                "fill_price": fill_price,
                "taker_fee_usd": taker_fee_usd,
                "order_response": resp,
            }

        except Exception as exc:
            logger.error("live_buy_failed", asset=asset, error=str(exc))
            return None

    async def execute_sell(
        self,
        trade_id: str,
        token_id: str,
        exit_price: float,
        exit_reason: str,
    ) -> dict | None:
        """Place a sell order on Polymarket CLOB."""
        trade = get_trade(self._db, trade_id)
        if not trade:
            logger.error("live_sell_trade_not_found", trade_id=trade_id)
            return None

        client = self._get_client()

        try:
            from py_clob_client.clob_types import OrderArgs, OrderType
            from py_clob_client.order_builder.constants import SELL

            shares = trade.size_usd / exit_price if exit_price > 0 else 0

            order = client.create_order(OrderArgs(
                token_id=token_id,
                price=exit_price,
                size=shares,
                side=SELL,
            ))
            resp = client.post_order(order, OrderType.GTC)

            # P&L — TP exits are maker (0% fee), SL/timeout exits are taker
            if exit_reason == "take_profit":
                exit_fee = 0.0  # Maker limit sell — 0% fee
            else:
                exit_fee = _calculate_taker_fee(exit_price, trade.timeframe)  # Taker
            exit_fee_usd = exit_fee * trade.size_usd

            if trade.action == "BUY_YES":
                pnl_usd = (exit_price - trade.entry_price) * trade.size_usd
            else:
                pnl_usd = (trade.entry_price - exit_price) * trade.size_usd

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
                "live_sell_executed",
                trade_id=trade_id,
                exit_price=exit_price,
                pnl_usd=round(pnl_usd, 4),
            )

            return {
                "trade_id": trade_id,
                "exit_price": exit_price,
                "pnl_usd": round(pnl_usd, 4),
                "result": result,
                "order_response": resp,
            }

        except Exception as exc:
            logger.error("live_sell_failed", trade_id=trade_id, error=str(exc))
            return None
