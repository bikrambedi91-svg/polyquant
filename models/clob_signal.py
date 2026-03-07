"""Model 7 — CLOBSignal: Polymarket order book imbalance signal.

Reads the CLOB order book as a directional signal:
- Bid/ask size imbalance > threshold → smart money buying YES → bullish boost
- Bid/ask size imbalance < 1/threshold → smart money selling YES → bearish boost
- Recent large trades → follow direction

For 4h+ timeframes: return confidence=0 (too noisy on long horizons).
Weight=0 on 4h in the default ensemble weights.
"""

import structlog

from models.base import BaseModel, ModelParams, ModelOutput

logger = structlog.get_logger(__name__)
MODEL_NAME = "CLOBSignal"

# Timeframes where CLOB signal is noise
NOISE_TIMEFRAMES = {"4h", "24h"}


class CLOBSignalModel(BaseModel):
    async def generate_signal(
        self, asset: str, timeframe: str, ohlcv=None, **kwargs
    ) -> ModelOutput:
        try:
            # CLOB signal is noise on long horizons
            if timeframe in NOISE_TIMEFRAMES:
                return ModelOutput(
                    asset=asset,
                    timeframe=timeframe,
                    prob_up=0.5,
                    confidence=0,
                    model_name=MODEL_NAME,
                    param_version=self.params.version,
                    key_drivers=["noise_on_long_tf"],
                )

            book_data = kwargs.get("book_data")
            if not book_data:
                return self._safe_output(asset, timeframe, MODEL_NAME)

            p = self.params.values
            imbalance_threshold = float(p.get("imbalance_threshold", 1.3))
            trade_size_threshold = float(p.get("trade_size_threshold", 500))
            boost_factor = float(p.get("boost_factor", 0.10))

            total_bid_size = book_data.get("total_bid_size", 0.0)
            total_ask_size = book_data.get("total_ask_size", 0.0)
            recent_large_trades = book_data.get("recent_large_trades", [])

            if total_ask_size <= 0 or total_bid_size <= 0:
                return self._safe_output(asset, timeframe, MODEL_NAME)

            imbalance = total_bid_size / total_ask_size

            # Base signal from order book imbalance
            prob_up = 0.50
            confidence = 30
            key_drivers = []

            if imbalance > imbalance_threshold:
                # More bids than asks → smart money buying YES → bullish
                intensity = min((imbalance - 1.0) / (imbalance_threshold - 1.0), 3.0)
                prob_up = 0.5 + (boost_factor * intensity)
                prob_up = min(prob_up, 0.80)
                confidence = min(int(40 + intensity * 15), 85)
                key_drivers.append(f"bid_heavy_imbalance={imbalance:.2f}")
            elif imbalance < (1.0 / imbalance_threshold):
                # More asks than bids → smart money selling YES → bearish
                inverse = 1.0 / imbalance
                intensity = min((inverse - 1.0) / (imbalance_threshold - 1.0), 3.0)
                prob_up = 0.5 - (boost_factor * intensity)
                prob_up = max(prob_up, 0.20)
                confidence = min(int(40 + intensity * 15), 85)
                key_drivers.append(f"ask_heavy_imbalance={imbalance:.2f}")
            else:
                key_drivers.append(f"balanced_book={imbalance:.2f}")

            # Boost from recent large trades
            buy_volume = 0.0
            sell_volume = 0.0
            for trade in recent_large_trades:
                size = trade.get("size", 0)
                if size >= trade_size_threshold:
                    if trade.get("side") == "BUY":
                        buy_volume += size
                    else:
                        sell_volume += size

            if buy_volume > sell_volume and buy_volume >= trade_size_threshold:
                prob_up += boost_factor * 0.5
                confidence = min(confidence + 10, 90)
                key_drivers.append(f"large_buys=${buy_volume:.0f}")
            elif sell_volume > buy_volume and sell_volume >= trade_size_threshold:
                prob_up -= boost_factor * 0.5
                confidence = min(confidence + 10, 90)
                key_drivers.append(f"large_sells=${sell_volume:.0f}")

            prob_up = max(0.10, min(0.90, prob_up))

            return ModelOutput(
                asset=asset,
                timeframe=timeframe,
                prob_up=prob_up,
                confidence=confidence,
                model_name=MODEL_NAME,
                param_version=self.params.version,
                key_drivers=key_drivers,
                raw_indicators={
                    "imbalance": imbalance,
                    "total_bid_size": total_bid_size,
                    "total_ask_size": total_ask_size,
                    "buy_volume": buy_volume,
                    "sell_volume": sell_volume,
                },
            )

        except Exception as exc:
            logger.error("clob_signal_error", asset=asset, error=str(exc))
            return self._safe_output(asset, timeframe, MODEL_NAME)
