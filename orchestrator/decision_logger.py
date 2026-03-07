"""DecisionLogger — records every pipeline decision step to the DB.

Each cycle gets a unique cycle_id. Each asset evaluation logs multiple
rows (one per decision stage: signal, ensemble, edge, filter, risk, execute).
The dashboard reads these rows to show the full reasoning chain in real time.

IMPORTANT: All writes use a short-lived session to avoid holding DB locks.
Failures are silently logged — never crash the trading pipeline.
"""

import json
import uuid
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger(__name__)


class DecisionLogger:
    """Lightweight decision logger injected into the TradingPipeline."""

    def __init__(self, session_factory):
        self._session_factory = session_factory
        self._cycle_id: str = ""
        self._timeframe: str = ""

    def start_cycle(self, timeframe: str) -> str:
        """Begin a new cycle. Returns cycle_id."""
        self._cycle_id = uuid.uuid4().hex[:12]
        self._timeframe = timeframe
        return self._cycle_id

    def log(
        self,
        asset: str,
        stage: str,
        decision: str,
        reason: str = "",
        details: dict | None = None,
        market_title: str = "",
    ) -> None:
        """Log one decision step. Never raises."""
        try:
            from database.models import PipelineDecision

            row = PipelineDecision(
                cycle_id=self._cycle_id,
                asset=asset,
                timeframe=self._timeframe,
                market_title=market_title,
                stage=stage,
                decision=decision,
                reason=reason,
                details_json=json.dumps(details, default=str) if details else None,
                created_at=datetime.now(timezone.utc),
            )
            session = self._session_factory()
            try:
                session.add(row)
                session.commit()
            finally:
                session.close()
        except Exception as exc:
            logger.warning("decision_log_write_error", error=str(exc))

    def log_cycle_summary(
        self,
        regime: str,
        markets_found: int,
        signals_generated: int,
        trades_opened: int,
        action: str,
    ) -> None:
        """Log a cycle-level summary row (asset='_CYCLE')."""
        self.log(
            asset="_CYCLE",
            stage="summary",
            decision=action,
            reason=f"regime={regime} markets={markets_found} signals={signals_generated} trades={trades_opened}",
            details={
                "regime": regime,
                "markets_found": markets_found,
                "signals_generated": signals_generated,
                "trades_opened": trades_opened,
            },
        )

    def log_market_scan(self, markets: list, timeframe: str) -> None:
        """Log which markets were found and basic info."""
        market_info = []
        for m in markets:  # Max ~12 markets (4 assets × 3 timeframes)
            asset = getattr(m, "asset", None) or m.get("asset", "")
            tf = getattr(m, "timeframe", None) or m.get("timeframe", "")
            yes_price = getattr(m, "current_yes_price", 0.5)
            title = getattr(m, "title", "")[:60]
            mtype = getattr(m, "market_type", "")
            market_info.append({
                "asset": asset,
                "timeframe": tf,
                "yes_price": round(yes_price, 3),
                "title": title,
                "type": mtype,
            })

        self.log(
            asset="_SCAN",
            stage="market_scan",
            decision="INFO",
            reason=f"Found {len(markets)} markets for {timeframe}",
            details={"markets": market_info, "total": len(markets)},
        )

    def log_signals(
        self, asset: str, signals: list, ensemble, timeframe: str,
    ) -> None:
        """Log individual model signals and ensemble result."""
        model_details = []
        for sig in signals:
            model_details.append({
                "model": sig.model_name,
                "prob_up": round(sig.prob_up, 4),
                "confidence": sig.confidence,
                "weight": round(
                    getattr(ensemble, "model_weights_used", {}).get(sig.model_name, 0), 4
                ),
                "key_drivers": getattr(sig, "key_drivers", [])[:3],
            })

        self.log(
            asset=asset,
            stage="signals",
            decision="INFO",
            reason=f"ensemble_prob={ensemble.prob_up:.3f} conf={ensemble.confidence}",
            details={
                "models": model_details,
                "ensemble_prob": round(ensemble.prob_up, 4),
                "ensemble_confidence": ensemble.confidence,
                "disagreement_flags": getattr(ensemble, "disagreement_flags", []),
            },
        )

    def log_edge_check(
        self,
        asset: str,
        action: str,
        yes_price: float,
        our_prob: float,
        effective_yes: float,
        edge: float,
        threshold: float,
        confidence: int,
        market_title: str = "",
        extra: dict | None = None,
    ) -> None:
        """Log the edge calculation details."""
        passed = edge >= threshold
        details = {
            "action": action,
            "yes_price": round(yes_price, 4),
            "our_prob": round(our_prob, 4),
            "effective_yes": round(effective_yes, 4),
            "edge": round(edge, 4),
            "threshold": round(threshold, 4),
            "confidence": confidence,
        }
        if extra:
            details.update(extra)

        self.log(
            asset=asset,
            stage="edge",
            decision="PASS" if passed else "REJECT",
            reason=f"{action} edge={edge:.3f} vs threshold={threshold:.3f}",
            details=details,
            market_title=market_title,
        )

    def log_filter(
        self,
        asset: str,
        filter_name: str,
        passed: bool,
        reason: str,
        details: dict | None = None,
        market_title: str = "",
    ) -> None:
        """Log a filter step (YES price, model agreement, confidence, etc.)."""
        self.log(
            asset=asset,
            stage=f"filter_{filter_name}",
            decision="PASS" if passed else "REJECT",
            reason=reason,
            details=details,
            market_title=market_title,
        )

    def log_risk_check(
        self, asset: str, passed: bool, reason: str, details: dict | None = None,
    ) -> None:
        """Log risk manager check."""
        self.log(
            asset=asset,
            stage="risk",
            decision="PASS" if passed else "REJECT",
            reason=reason,
            details=details,
        )

    def log_trade_executed(
        self,
        asset: str,
        action: str,
        entry_price: float,
        size_usd: float,
        tp: float,
        sl: float,
        market_title: str = "",
    ) -> None:
        """Log a trade that was actually executed."""
        self.log(
            asset=asset,
            stage="execute",
            decision="TRADE",
            reason=f"{action} entry={entry_price:.3f} size=${size_usd:.0f}",
            details={
                "action": action,
                "entry_price": round(entry_price, 4),
                "size_usd": size_usd,
                "tp_level": round(tp, 4),
                "sl_level": round(sl, 4),
            },
            market_title=market_title,
        )

    @staticmethod
    def cleanup_old(session_factory, keep_hours: int = 6) -> int:
        """Delete decision logs older than keep_hours. Returns rows deleted."""
        try:
            from database.models import PipelineDecision
            cutoff = datetime.now(timezone.utc).replace(
                hour=max(0, datetime.now(timezone.utc).hour - keep_hours),
            )
            session = session_factory()
            try:
                deleted = (
                    session.query(PipelineDecision)
                    .filter(PipelineDecision.created_at < cutoff)
                    .delete()
                )
                session.commit()
                return deleted
            finally:
                session.close()
        except Exception:
            return 0
