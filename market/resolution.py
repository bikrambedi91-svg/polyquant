"""Resolution risk scoring — assess ambiguity and failure risk per market.

5m/15m/1h/4h up_down markets use Chainlink oracle → LOW risk.
Longer or more complex markets carry higher risk penalties.
"""

from dataclasses import dataclass

import structlog

from market.scanner import CryptoMarket

logger = structlog.get_logger(__name__)


@dataclass
class ResolutionRisk:
    """Resolution risk assessment for a market."""
    level: str          # "LOW", "MEDIUM", "MEDIUM_HIGH", "HIGH"
    penalty: float      # percentage penalty to apply to edge (0.0 - 0.03)
    reason: str


class ResolutionAnalyzer:
    """Assesses resolution risk for Polymarket crypto markets."""

    def assess_risk(self, market: CryptoMarket) -> ResolutionRisk:
        """Score resolution risk based on market type, timeframe, and source."""
        tf = market.timeframe
        mtype = market.market_type

        # 5m/15m/1h/4h up_down with Chainlink oracle → LOW risk
        if tf in ("5m", "15m", "1h", "4h") and mtype == "up_down":
            return ResolutionRisk(
                level="LOW",
                penalty=0.0,
                reason="Automated Chainlink oracle, no ambiguity",
            )

        # Daily/weekly price_target markets
        if tf in ("daily", "weekly") and mtype == "price_target":
            return ResolutionRisk(
                level="MEDIUM",
                penalty=0.015,
                reason="Flash crash edge cases near resolution time",
            )

        # Daily/weekly up_down — slightly less risk than price targets
        if tf in ("daily", "weekly") and mtype == "up_down":
            return ResolutionRisk(
                level="MEDIUM",
                penalty=0.015,
                reason="Longer duration increases uncertainty",
            )

        # Monthly+ markets
        if tf in ("monthly",):
            return ResolutionRisk(
                level="MEDIUM_HIGH",
                penalty=0.02,
                reason="Long duration, more things can go wrong",
            )

        # Anything else — unclear resolution criteria
        return ResolutionRisk(
            level="HIGH",
            penalty=0.03,
            reason="Unclear resolution criteria or unknown market type",
        )
