"""Model 1 — MomentumRegime: ADX + DI trend classification.

Classifies market state: TRENDING_UP, TRENDING_DOWN, MEAN_REVERTING, CHOPPY.
In trending: prob_up follows trend direction. In mean-revert: prob_up fades recent move.
Uses `ta` library (NOT ta-lib).
"""

import structlog
import pandas as pd
import ta.trend

from models.base import BaseModel, ModelParams, ModelOutput

logger = structlog.get_logger(__name__)
MODEL_NAME = "MomRegime"


class MomentumRegimeModel(BaseModel):
    async def generate_signal(
        self, asset: str, timeframe: str, ohlcv: pd.DataFrame, **kwargs
    ) -> ModelOutput:
        try:
            p = self.params.values
            adx_period = int(p.get("adx_period", 14))
            ema_fast_period = int(p.get("ema_fast", 20))
            ema_slow_period = int(p.get("ema_slow", 50))
            adx_threshold = float(p.get("adx_threshold", 25))
            lookback = int(p.get("lookback", 100))

            df = ohlcv.tail(lookback).copy()
            if len(df) < max(adx_period, ema_slow_period) + 5:
                return self._safe_output(asset, timeframe, MODEL_NAME)

            high = df["high"]
            low = df["low"]
            close = df["close"]

            # ADX + directional indicators
            adx_ind = ta.trend.ADXIndicator(high, low, close, window=adx_period)
            adx_val = adx_ind.adx().iloc[-1]
            di_plus = adx_ind.adx_pos().iloc[-1]
            di_minus = adx_ind.adx_neg().iloc[-1]

            # EMAs
            ema_fast = ta.trend.EMAIndicator(close, window=ema_fast_period).ema_indicator().iloc[-1]
            ema_slow = ta.trend.EMAIndicator(close, window=ema_slow_period).ema_indicator().iloc[-1]

            # Classify regime
            if pd.isna(adx_val) or pd.isna(di_plus) or pd.isna(di_minus):
                return self._safe_output(asset, timeframe, MODEL_NAME)

            ema_bullish = ema_fast > ema_slow
            trending = adx_val > adx_threshold

            if trending and di_plus > di_minus and ema_bullish:
                regime = "TRENDING_UP"
                prob_up = 0.5 + min((adx_val - adx_threshold) / 40.0, 0.25) + 0.05
                confidence = min(int(40 + adx_val), 90)
            elif trending and di_minus > di_plus and not ema_bullish:
                regime = "TRENDING_DOWN"
                prob_up = 0.5 - min((adx_val - adx_threshold) / 40.0, 0.25) - 0.05
                confidence = min(int(40 + adx_val), 90)
            elif not trending:
                regime = "CHOPPY"
                # Mean-reversion: fade the recent move
                recent_return = (close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] if len(close) >= 5 else 0
                prob_up = 0.5 - (recent_return * 5.0)  # fade
                prob_up = max(0.30, min(0.70, prob_up))
                confidence = max(20, int(50 - adx_val))
            else:
                regime = "MEAN_REVERTING"
                prob_up = 0.50
                confidence = 30

            key_drivers = [
                f"ADX={adx_val:.1f}",
                f"DI+={di_plus:.1f}",
                f"DI-={di_minus:.1f}",
                f"EMA_fast={'above' if ema_bullish else 'below'}_slow",
                f"regime={regime}",
            ]

            return ModelOutput(
                asset=asset,
                timeframe=timeframe,
                prob_up=prob_up,
                confidence=confidence,
                model_name=MODEL_NAME,
                param_version=self.params.version,
                key_drivers=key_drivers,
                raw_indicators={
                    "adx": adx_val, "di_plus": di_plus, "di_minus": di_minus,
                    "ema_fast": ema_fast, "ema_slow": ema_slow, "regime": regime,
                },
            )

        except Exception as exc:
            logger.error("momentum_regime_error", asset=asset, error=str(exc))
            return self._safe_output(asset, timeframe, MODEL_NAME)
