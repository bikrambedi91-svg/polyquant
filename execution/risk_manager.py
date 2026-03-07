"""Risk manager — fixed sizing, position limits, correlation detection.

Hard limits:
- Fixed position size: $20 per trade
- Max 3 open positions total
- Max per asset: 25% of bankroll
- Max total exposure: 60% of bankroll
- Max net directional: 40% of bankroll
- Max same-direction per timeframe: 3 positions
- Daily loss halt: $100 USD
"""

import structlog

from config.settings import Settings

logger = structlog.get_logger(__name__)

# Directional concentration limits — prevents correlated blowups
MAX_NET_DIRECTIONAL_PCT = 0.40   # Max 40% of bankroll net long or net short
MAX_SAME_DIRECTION_PER_TF = 3    # Max 3 positions in same direction+timeframe
MAX_OPEN_POSITIONS = 3           # Max 3 open positions at once


class RiskManager:
    def __init__(self, settings: Settings):
        self.bankroll = settings.BANKROLL_USDC
        self.max_single_pct = settings.MAX_SINGLE_POSITION_PCT
        self.max_per_asset_pct = settings.MAX_PER_ASSET_PCT
        self.max_total_pct = settings.MAX_TOTAL_EXPOSURE_PCT
        self.daily_loss_halt_usd = getattr(settings, 'DAILY_LOSS_HALT_USD', 100.0)
        self.position_size_usd = getattr(settings, 'POSITION_SIZE_USD', 20.0)
        self.min_position = getattr(settings, 'MIN_POSITION_USD', 5.0)

    def get_position_size(self) -> float:
        """Return fixed position size in USD."""
        return self.position_size_usd

    def check_limits(
        self,
        asset: str,
        size_usd: float,
        active_positions: list[dict],
        daily_pnl: float = 0.0,
        action: str = "",
        timeframe: str = "",
    ) -> tuple[bool, str]:
        """Check all risk limits before placing a trade.

        active_positions: list of dicts with keys: asset, size_usd, status, action, timeframe
        daily_pnl: today's realized P&L (negative = drawdown)
        action: "BUY_YES" or "BUY_NO" for the proposed trade
        timeframe: timeframe of the proposed trade

        Returns (True, "") if OK, (False, reason) if blocked.
        """
        # Daily loss halt — fixed USD amount
        if daily_pnl < 0 and abs(daily_pnl) >= self.daily_loss_halt_usd:
            return False, f"Daily loss halt: ${abs(daily_pnl):.0f} >= ${self.daily_loss_halt_usd:.0f}"

        # Max open positions
        open_count = sum(1 for p in active_positions if p.get("status") == "ACTIVE")
        if open_count >= MAX_OPEN_POSITIONS:
            return False, f"Max {MAX_OPEN_POSITIONS} open positions reached"

        # Single position limit
        max_single = self.bankroll * self.max_single_pct
        if size_usd > max_single:
            return False, f"Position ${size_usd:.0f} exceeds max single ${max_single:.0f}"

        # Per-asset limit
        asset_exposure = sum(
            p["size_usd"] for p in active_positions
            if p.get("asset") == asset and p.get("status") == "ACTIVE"
        )
        max_asset = self.bankroll * self.max_per_asset_pct
        if asset_exposure + size_usd > max_asset:
            return False, (
                f"Asset {asset} exposure ${asset_exposure + size_usd:.0f} "
                f"exceeds max ${max_asset:.0f}"
            )

        # Total exposure limit
        total_exposure = sum(
            p["size_usd"] for p in active_positions
            if p.get("status") == "ACTIVE"
        )
        max_total = self.bankroll * self.max_total_pct
        if total_exposure + size_usd > max_total:
            return False, (
                f"Total exposure ${total_exposure + size_usd:.0f} "
                f"exceeds max ${max_total:.0f}"
            )

        # Directional concentration limit — prevents correlated blowups
        # Crypto assets are highly correlated; all BUY_YES move together
        if action:
            long_exposure = sum(
                p["size_usd"] for p in active_positions
                if p.get("status") == "ACTIVE" and p.get("action") == "BUY_YES"
            )
            short_exposure = sum(
                p["size_usd"] for p in active_positions
                if p.get("status") == "ACTIVE" and p.get("action") == "BUY_NO"
            )
            if action == "BUY_YES":
                long_exposure += size_usd
            else:
                short_exposure += size_usd

            net_directional = abs(long_exposure - short_exposure)
            max_directional = self.bankroll * MAX_NET_DIRECTIONAL_PCT
            if net_directional > max_directional:
                return False, (
                    f"Net directional ${net_directional:.0f} exceeds max ${max_directional:.0f}. "
                    f"Long=${long_exposure:.0f} Short=${short_exposure:.0f}"
                )

        # Same-direction per timeframe limit — prevents clusters of identical trades
        if action and timeframe:
            same_dir_tf_count = sum(
                1 for p in active_positions
                if p.get("status") == "ACTIVE"
                and p.get("action") == action
                and p.get("timeframe") == timeframe
            )
            if same_dir_tf_count >= MAX_SAME_DIRECTION_PER_TF:
                return False, (
                    f"{action} {timeframe}: already {same_dir_tf_count} positions "
                    f"(max {MAX_SAME_DIRECTION_PER_TF})"
                )

        # Minimum position
        if size_usd < self.min_position:
            return False, f"Position ${size_usd:.0f} below minimum ${self.min_position:.0f}"

        return True, ""

    def detect_correlation(
        self, market_a: dict, market_b: dict
    ) -> float:
        """Detect correlation between two markets.

        Simple heuristic: same asset and overlapping timeframe → high correlation.
        Returns 0.0-1.0 (1.0 = perfectly correlated).
        """
        if market_a.get("asset") == market_b.get("asset"):
            # Same asset, different timeframes still correlated
            if market_a.get("timeframe") == market_b.get("timeframe"):
                return 1.0  # Same asset + same TF = duplicate
            return 0.7  # Same asset, different TF
        # Different assets — crypto is generally correlated
        return 0.3
