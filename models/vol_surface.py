"""Model 4 — VolSurface: IV skew / realized vol signal.

BTC/ETH: Try Deribit for 25-delta risk reversal.
SOL/XRP: Use realized vol percentile as proxy.
No Deribit key → fall back to ATR percentile from OHLCV data for all assets.
"""

import structlog
import pandas as pd
import ta.volatility

from models.base import BaseModel, ModelParams, ModelOutput

logger = structlog.get_logger(__name__)
MODEL_NAME = "VolSurf"


class VolSurfaceModel(BaseModel):
    async def generate_signal(
        self, asset: str, timeframe: str, ohlcv: pd.DataFrame = None, **kwargs
    ) -> ModelOutput:
        try:
            if ohlcv is None or len(ohlcv) < 20:
                return self._safe_output(asset, timeframe, MODEL_NAME)

            p = self.params.values
            skew_fear = float(p.get("skew_fear", -5.0))
            skew_greed = float(p.get("skew_greed", 5.0))
            iv_lookback = int(p.get("iv_lookback_days", 30))

            deribit_data = kwargs.get("deribit_data")

            if deribit_data and asset in ("BTC", "ETH"):
                return self._from_deribit(asset, timeframe, deribit_data, skew_fear, skew_greed)

            # Fallback: ATR percentile from OHLCV
            return self._from_atr_percentile(asset, timeframe, ohlcv, iv_lookback)

        except Exception as exc:
            logger.error("vol_surface_error", asset=asset, error=str(exc))
            return self._safe_output(asset, timeframe, MODEL_NAME)

    def _from_deribit(
        self, asset: str, timeframe: str, data: dict, skew_fear: float, skew_greed: float
    ) -> ModelOutput:
        """Generate signal from Deribit IV skew data."""
        skew = data.get("skew_25d", 0.0)

        if skew < skew_fear:
            # Put skew steep → market pricing crash risk → contrarian bullish
            intensity = min(abs(skew / skew_fear), 2.5)
            prob_up = 0.5 + (0.08 * intensity)
            confidence = min(int(45 + intensity * 12), 80)
            key_drivers = [f"iv_skew={skew:.1f}", "put_skew_steep", "contrarian_bullish"]
        elif skew > skew_greed:
            # Call skew steep → market euphoric → contrarian bearish
            intensity = min(abs(skew / skew_greed), 2.5)
            prob_up = 0.5 - (0.08 * intensity)
            confidence = min(int(45 + intensity * 12), 80)
            key_drivers = [f"iv_skew={skew:.1f}", "call_skew_steep", "contrarian_bearish"]
        else:
            prob_up = 0.50
            confidence = 20
            key_drivers = [f"iv_skew={skew:.1f}", "neutral"]

        return ModelOutput(
            asset=asset, timeframe=timeframe, prob_up=prob_up,
            confidence=confidence, model_name=MODEL_NAME,
            param_version=self.params.version, key_drivers=key_drivers,
            raw_indicators={"iv_skew": skew, "source": "deribit"},
        )

    def _from_atr_percentile(
        self, asset: str, timeframe: str, ohlcv: pd.DataFrame, lookback_days: int
    ) -> ModelOutput:
        """Fallback: Use ATR percentile as vol surface proxy."""
        df = ohlcv.copy()
        atr_period = 14
        if len(df) < atr_period + 5:
            return self._safe_output(asset, timeframe, MODEL_NAME)

        atr_ind = ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=atr_period)
        atr_series = atr_ind.average_true_range()
        current_atr = atr_series.iloc[-1]

        if pd.isna(current_atr):
            return self._safe_output(asset, timeframe, MODEL_NAME)

        # Percentile of current ATR vs recent history
        lookback_bars = min(lookback_days * 6, len(atr_series))  # rough: 6 bars per day for 4h
        recent_atr = atr_series.tail(max(lookback_bars, 20))
        percentile = (recent_atr < current_atr).sum() / len(recent_atr)

        # High vol percentile → market fearful → slight contrarian bullish
        # Low vol percentile → market complacent → slight bearish (vol expansion risk)
        if percentile > 0.85:
            prob_up = 0.55  # High vol → slight bullish (fear overdone)
            confidence = 45
            key_drivers = [f"ATR_pct={percentile:.0%}", "high_vol_contrarian_bull"]
        elif percentile < 0.15:
            prob_up = 0.45  # Low vol → slight bearish (complacency)
            confidence = 40
            key_drivers = [f"ATR_pct={percentile:.0%}", "low_vol_complacent"]
        else:
            prob_up = 0.50
            confidence = 20
            key_drivers = [f"ATR_pct={percentile:.0%}", "vol_neutral"]

        return ModelOutput(
            asset=asset, timeframe=timeframe, prob_up=prob_up,
            confidence=confidence, model_name=MODEL_NAME,
            param_version=self.params.version, key_drivers=key_drivers,
            raw_indicators={"atr": current_atr, "atr_percentile": percentile, "source": "atr_fallback"},
        )
