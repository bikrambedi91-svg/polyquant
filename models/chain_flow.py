"""Model 3 — ChainFlow: Exchange net flow signal.

Large outflows = accumulation = bullish. Large inflows = distribution = bearish.
When feed confidence=0 (no API key), returns prob_up=0.5, confidence=0.
The ensemble gives this zero effective weight automatically.

NOTE: Weight=0 on 5m/15m (data updates every 10+ min, useless on short TFs).
"""

import structlog

from models.base import BaseModel, ModelParams, ModelOutput

logger = structlog.get_logger(__name__)
MODEL_NAME = "ChainFlow"


class ChainFlowModel(BaseModel):
    async def generate_signal(
        self, asset: str, timeframe: str, ohlcv=None, **kwargs
    ) -> ModelOutput:
        try:
            flow_data = kwargs.get("flow_data")
            if not flow_data:
                return self._safe_output(asset, timeframe, MODEL_NAME)

            feed_confidence = flow_data.get("confidence", 0)
            if feed_confidence == 0:
                # No API key or no data — return neutral with zero confidence
                return ModelOutput(
                    asset=asset,
                    timeframe=timeframe,
                    prob_up=0.5,
                    confidence=0,
                    model_name=MODEL_NAME,
                    param_version=self.params.version,
                    key_drivers=["no_onchain_data"],
                    raw_indicators={"net_flow": 0.0, "feed_confidence": 0},
                )

            p = self.params.values
            outflow_zscore = float(p.get("outflow_zscore", 1.5))
            inflow_zscore = float(p.get("inflow_zscore", 1.5))
            decay_rate = float(p.get("decay_rate", 0.9))

            net_flow = flow_data.get("net_flow", 0.0)

            # Positive net_flow = more going into exchanges = distribution = bearish
            # Negative net_flow = more leaving exchanges = accumulation = bullish
            if net_flow < -outflow_zscore:
                # Significant outflow → bullish
                intensity = min(abs(net_flow) / outflow_zscore, 3.0)
                prob_up = 0.5 + (0.08 * intensity * decay_rate)
                prob_up = min(prob_up, 0.80)
                confidence = min(int(40 + intensity * 12), 75)
                key_drivers = [f"net_flow={net_flow:.2f}", "outflow_bullish"]
            elif net_flow > inflow_zscore:
                # Significant inflow → bearish
                intensity = min(abs(net_flow) / inflow_zscore, 3.0)
                prob_up = 0.5 - (0.08 * intensity * decay_rate)
                prob_up = max(prob_up, 0.20)
                confidence = min(int(40 + intensity * 12), 75)
                key_drivers = [f"net_flow={net_flow:.2f}", "inflow_bearish"]
            else:
                prob_up = 0.50
                confidence = 15
                key_drivers = [f"net_flow={net_flow:.2f}", "neutral"]

            return ModelOutput(
                asset=asset,
                timeframe=timeframe,
                prob_up=prob_up,
                confidence=confidence,
                model_name=MODEL_NAME,
                param_version=self.params.version,
                key_drivers=key_drivers,
                raw_indicators={"net_flow": net_flow, "feed_confidence": feed_confidence},
            )

        except Exception as exc:
            logger.error("chain_flow_error", asset=asset, error=str(exc))
            return self._safe_output(asset, timeframe, MODEL_NAME)
