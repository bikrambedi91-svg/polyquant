"""Fee-aware pricing engine — taker fees, effective implied prob, edge calculation.

Fee curve: fee = max_fee_rate × 2 × price × (1 - price)
Maker orders are free. Taker fee highest at price=0.50, zero at extremes.
"""

import structlog

from config.constants import TAKER_FEE_MAX

logger = structlog.get_logger(__name__)


class PricingEngine:
    """Computes fees, effective implied probabilities, and trading edge."""

    def calculate_taker_fee(self, share_price: float, timeframe: str) -> float:
        """Actual Polymarket taker fee for a given price and timeframe.

        fee = max_fee_rate × 2 × price × (1 - price)
        """
        max_fee = TAKER_FEE_MAX.get(timeframe, 0.0)
        return max_fee * 2.0 * share_price * (1.0 - share_price)

    def effective_implied_prob(
        self,
        yes_price: float,
        timeframe: str,
        expected_slippage: float = 0.0,
        use_maker: bool = True,
    ) -> float:
        """True cost of acquiring a YES position.

        With maker orders (default): effective = yes_price + slippage (0% fee)
        With taker orders: effective = yes_price + taker_fee + slippage
        """
        if use_maker:
            fee = 0.0  # Maker orders have 0% fee on Polymarket
        else:
            fee = self.calculate_taker_fee(yes_price, timeframe)
        return yes_price + fee + expected_slippage

    def calculate_edge(
        self,
        our_prob: float,
        effective_implied: float,
        resolution_penalty: float = 0.0,
    ) -> float:
        """Raw edge between our probability and market's effective implied.

        edge = |our_prob - effective_implied| - resolution_penalty
        """
        return abs(our_prob - effective_implied) - resolution_penalty

    def expected_value(
        self,
        our_prob: float,
        entry_price: float,
        action: str,
        timeframe: str,
    ) -> float:
        """Expected value per dollar for a BUY_YES or BUY_NO trade.

        BUY_YES: EV = our_prob - entry_price - fee
        BUY_NO:  EV = (1 - our_prob) - (1 - entry_price) - fee
        """
        fee = self.calculate_taker_fee(entry_price, timeframe)
        if action == "BUY_YES":
            return our_prob - entry_price - fee
        else:  # BUY_NO
            return (1.0 - our_prob) - (1.0 - entry_price) - fee
