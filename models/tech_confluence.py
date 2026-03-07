"""Model 6 — TechConfluence: RSI/MACD/BB/VWAP/Volume confluence.

Counts how many of 5 indicators agree on direction. High confluence → high confidence.
Uses `ta` library (NOT ta-lib).
Constraint: rsi_bull_threshold must be > rsi_bear_threshold.
"""

import structlog
import pandas as pd
import ta.momentum
import ta.trend
import ta.volatility
import ta.volume

from models.base import BaseModel, ModelParams, ModelOutput

logger = structlog.get_logger(__name__)
MODEL_NAME = "TechConf"


class TechConfluenceModel(BaseModel):
    async def generate_signal(
        self, asset: str, timeframe: str, ohlcv: pd.DataFrame = None, **kwargs
    ) -> ModelOutput:
        try:
            if ohlcv is None or len(ohlcv) < 30:
                return self._safe_output(asset, timeframe, MODEL_NAME)

            p = self.params.values
            rsi_period = int(p.get("rsi_period", 14))
            rsi_bull = float(p.get("rsi_bull", 55))
            rsi_bear = float(p.get("rsi_bear", 45))
            macd_fast = int(p.get("macd_fast", 12))
            macd_slow = int(p.get("macd_slow", 26))
            macd_signal = int(p.get("macd_signal", 9))
            bb_period = int(p.get("bb_period", 20))
            bb_std = float(p.get("bb_std", 2.0))
            vol_period = int(p.get("volume_avg_period", 20))
            confluence_thresh = int(p.get("confluence_threshold", 3))

            df = ohlcv.copy()
            close = df["close"]
            volume = df["volume"]

            # 1. RSI
            rsi = ta.momentum.RSIIndicator(close, window=rsi_period).rsi().iloc[-1]
            rsi_bullish = rsi > rsi_bull if not pd.isna(rsi) else None
            rsi_bearish = rsi < rsi_bear if not pd.isna(rsi) else None

            # 2. MACD
            macd_ind = ta.trend.MACD(close, window_fast=macd_fast, window_slow=macd_slow, window_sign=macd_signal)
            macd_line = macd_ind.macd().iloc[-1]
            macd_sig = macd_ind.macd_signal().iloc[-1]
            macd_bullish = macd_line > macd_sig if not (pd.isna(macd_line) or pd.isna(macd_sig)) else None

            # 3. Bollinger Bands
            bb = ta.volatility.BollingerBands(close, window=bb_period, window_dev=bb_std)
            bb_upper = bb.bollinger_hband().iloc[-1]
            bb_lower = bb.bollinger_lband().iloc[-1]
            bb_mid = bb.bollinger_mavg().iloc[-1]
            current_price = close.iloc[-1]
            bb_bullish = current_price > bb_mid if not pd.isna(bb_mid) else None

            # 4. VWAP proxy (volume-weighted close avg)
            if len(df) >= vol_period:
                vwap = (close.tail(vol_period) * volume.tail(vol_period)).sum() / volume.tail(vol_period).sum()
                vwap_bullish = current_price > vwap if not pd.isna(vwap) else None
            else:
                vwap = None
                vwap_bullish = None

            # 5. Volume confirmation
            vol_avg = volume.rolling(vol_period).mean().iloc[-1]
            current_vol = volume.iloc[-1]
            vol_above_avg = current_vol > vol_avg if not pd.isna(vol_avg) else None

            # Count bullish / bearish signals
            signals = [rsi_bullish, macd_bullish, bb_bullish, vwap_bullish, vol_above_avg]
            valid_signals = [s for s in signals if s is not None]
            if not valid_signals:
                return self._safe_output(asset, timeframe, MODEL_NAME)

            bullish_count = sum(1 for s in valid_signals if s)
            bearish_count = sum(1 for s in valid_signals if not s)
            total = len(valid_signals)

            # Probability based on confluence
            if bullish_count >= confluence_thresh:
                prob_up = 0.5 + (bullish_count / total) * 0.30
                confidence = min(int(40 + bullish_count * 12), 90)
            elif bearish_count >= confluence_thresh:
                prob_up = 0.5 - (bearish_count / total) * 0.30
                confidence = min(int(40 + bearish_count * 12), 90)
            else:
                prob_up = 0.50
                confidence = 25

            key_drivers = [
                f"RSI={rsi:.1f}" if not pd.isna(rsi) else "RSI=N/A",
                f"MACD={'bull' if macd_bullish else 'bear' if macd_bullish is not None else 'N/A'}",
                f"BB={'above' if bb_bullish else 'below' if bb_bullish is not None else 'N/A'}_mid",
                f"VWAP={'above' if vwap_bullish else 'below' if vwap_bullish is not None else 'N/A'}",
                f"Vol={'high' if vol_above_avg else 'low' if vol_above_avg is not None else 'N/A'}",
                f"confluence={bullish_count}B/{bearish_count}S/{total}T",
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
                    "rsi": float(rsi) if not pd.isna(rsi) else None,
                    "macd_line": float(macd_line) if not pd.isna(macd_line) else None,
                    "bb_upper": float(bb_upper) if not pd.isna(bb_upper) else None,
                    "bb_lower": float(bb_lower) if not pd.isna(bb_lower) else None,
                    "bullish_count": bullish_count,
                    "bearish_count": bearish_count,
                },
            )

        except Exception as exc:
            logger.error("tech_confluence_error", asset=asset, error=str(exc))
            return self._safe_output(asset, timeframe, MODEL_NAME)
