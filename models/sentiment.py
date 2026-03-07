"""Model 5 — SentimentComposite: Fear & Greed Index signal.

Contrarian at extremes, confirming in mid-range.
NOTE: F&G updates ONCE PER DAY. For 5m/15m timeframes: always return confidence=0.
Weight=0 on 5m/15m in the default ensemble weights for this reason.
"""

import structlog

from models.base import BaseModel, ModelParams, ModelOutput

logger = structlog.get_logger(__name__)
MODEL_NAME = "SentComp"

# Timeframes where sentiment is stale / useless
STALE_TIMEFRAMES = {"5m", "15m"}


class SentimentModel(BaseModel):
    async def generate_signal(
        self, asset: str, timeframe: str, ohlcv=None, **kwargs
    ) -> ModelOutput:
        try:
            # Sentiment updates once per day — useless on short timeframes
            if timeframe in STALE_TIMEFRAMES:
                return ModelOutput(
                    asset=asset,
                    timeframe=timeframe,
                    prob_up=0.5,
                    confidence=0,
                    model_name=MODEL_NAME,
                    param_version=self.params.version,
                    key_drivers=["stale_on_short_tf"],
                )

            sentiment_data = kwargs.get("sentiment_data")
            if not sentiment_data:
                return self._safe_output(asset, timeframe, MODEL_NAME)

            p = self.params.values
            fear_threshold = int(p.get("fear_threshold", 25))
            greed_threshold = int(p.get("greed_threshold", 75))
            contrarian_mult = float(p.get("contrarian_mult", 1.5))

            fng_value = sentiment_data.get("value", 50)

            if fng_value <= fear_threshold:
                # Extreme fear → contrarian bullish
                intensity = (fear_threshold - fng_value) / fear_threshold
                prob_up = 0.5 + (0.15 * intensity * contrarian_mult)
                prob_up = min(prob_up, 0.85)
                confidence = min(int(45 + intensity * 30), 80)
                key_drivers = [f"F&G={fng_value}", "extreme_fear", "contrarian_bullish"]
            elif fng_value >= greed_threshold:
                # Extreme greed → contrarian bearish
                intensity = (fng_value - greed_threshold) / (100 - greed_threshold)
                prob_up = 0.5 - (0.15 * intensity * contrarian_mult)
                prob_up = max(prob_up, 0.15)
                confidence = min(int(45 + intensity * 30), 80)
                key_drivers = [f"F&G={fng_value}", "extreme_greed", "contrarian_bearish"]
            else:
                # Mid-range — weak / neutral signal
                # Slight trend-confirming: above 50 → mild bullish, below 50 → mild bearish
                prob_up = 0.50 + (fng_value - 50) * 0.002
                confidence = 25
                key_drivers = [f"F&G={fng_value}", "neutral_range"]

            return ModelOutput(
                asset=asset,
                timeframe=timeframe,
                prob_up=prob_up,
                confidence=confidence,
                model_name=MODEL_NAME,
                param_version=self.params.version,
                key_drivers=key_drivers,
                raw_indicators={"fear_greed": fng_value},
            )

        except Exception as exc:
            logger.error("sentiment_error", asset=asset, error=str(exc))
            return self._safe_output(asset, timeframe, MODEL_NAME)
