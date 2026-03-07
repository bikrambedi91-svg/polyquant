"""Model 2 — FundingBasis: Perpetual funding rate contrarian signal.

Extreme negative funding → contrarian long. Extreme positive → caution / contrarian short.
"""

import structlog

from models.base import BaseModel, ModelParams, ModelOutput

logger = structlog.get_logger(__name__)
MODEL_NAME = "FundBasis"


class FundingBasisModel(BaseModel):
    async def generate_signal(
        self, asset: str, timeframe: str, ohlcv=None, **kwargs
    ) -> ModelOutput:
        try:
            funding_data = kwargs.get("funding_data")
            if not funding_data or funding_data.get("rate") is None:
                return self._safe_output(asset, timeframe, MODEL_NAME)

            p = self.params.values
            neg_threshold = float(p.get("neg_threshold", -0.0001))
            pos_threshold = float(p.get("pos_threshold", 0.0005))
            contrarian_mult = float(p.get("contrarian_mult", 1.0))

            rate = funding_data["rate"]

            if rate < neg_threshold:
                # Extreme negative funding → shorts are paying heavily → contrarian bullish
                intensity = min(abs(rate / neg_threshold), 3.0)
                prob_up = 0.5 + (0.10 * intensity * contrarian_mult)
                prob_up = min(prob_up, 0.85)
                confidence = min(int(50 + intensity * 15), 85)
                key_drivers = [f"funding={rate:.6f}", "extreme_negative", f"contrarian_long_x{intensity:.1f}"]
            elif rate > pos_threshold:
                # Extreme positive funding → longs are paying heavily → contrarian bearish
                intensity = min(abs(rate / pos_threshold), 3.0)
                prob_up = 0.5 - (0.10 * intensity * contrarian_mult)
                prob_up = max(prob_up, 0.15)
                confidence = min(int(50 + intensity * 15), 85)
                key_drivers = [f"funding={rate:.6f}", "extreme_positive", f"contrarian_short_x{intensity:.1f}"]
            else:
                # Neutral funding — weak signal
                prob_up = 0.50
                confidence = 20
                key_drivers = [f"funding={rate:.6f}", "neutral"]

            return ModelOutput(
                asset=asset,
                timeframe=timeframe,
                prob_up=prob_up,
                confidence=confidence,
                model_name=MODEL_NAME,
                param_version=self.params.version,
                key_drivers=key_drivers,
                raw_indicators={"funding_rate": rate},
            )

        except Exception as exc:
            logger.error("funding_basis_error", asset=asset, error=str(exc))
            return self._safe_output(asset, timeframe, MODEL_NAME)
