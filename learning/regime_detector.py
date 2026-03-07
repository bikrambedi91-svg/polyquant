"""Regime detection — classifies macro conditions from BTC data.

5 regimes: RISK_ON, RISK_OFF, HIGH_VOL, TRENDING, CHOPPY.
BTC serves as macro proxy — BTC regime drives all crypto.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
import structlog

from config.constants import REGIME_ADJUSTMENTS

logger = structlog.get_logger(__name__)


@dataclass
class RegimeState:
    """Current market regime with adjustment parameters."""
    regime: str             # RISK_ON, RISK_OFF, HIGH_VOL, TRENDING, CHOPPY
    confidence: float       # 0.0-1.0
    kelly_mult: float       # Multiplier for Kelly sizing
    edge_threshold: float   # Min edge required (adjusted)
    sl_mult: float          # SL level multiplier
    tp_mult: float          # TP level multiplier
    model_weight_overrides: dict  # model_name -> weight override (empty = no override)
    indicators: dict        # Raw indicators that drove the classification


class RegimeDetector:
    """Classifies market regime using BTC as macro proxy.

    Uses:
    - Realized volatility (20-period)
    - ADX for trend strength
    - Simple returns for directional bias
    - Drawdown from recent high for risk-off detection
    """

    def __init__(
        self,
        vol_high_threshold: float = 0.04,
        vol_low_threshold: float = 0.015,
        adx_trending_threshold: float = 25.0,
        drawdown_risk_off: float = -0.05,
        lookback: int = 20,
    ):
        self._vol_high = vol_high_threshold
        self._vol_low = vol_low_threshold
        self._adx_trend = adx_trending_threshold
        self._dd_risk_off = drawdown_risk_off
        self._lookback = lookback

    def detect(self, btc_ohlcv: pd.DataFrame) -> RegimeState:
        """Classify regime from BTC OHLCV data.

        Args:
            btc_ohlcv: DataFrame with columns [open, high, low, close, volume].
                        Must have at least `lookback + 1` rows.

        Returns:
            RegimeState with all adjustment parameters.
        """
        if btc_ohlcv is None or len(btc_ohlcv) < self._lookback + 1:
            return self._default_regime("insufficient_data")

        try:
            close = btc_ohlcv["close"].values.astype(float)

            # Realized volatility: std of log returns
            log_returns = np.diff(np.log(close[-self._lookback - 1:]))
            realized_vol = float(np.std(log_returns))

            # ADX approximation: directional strength
            adx = self._approximate_adx(btc_ohlcv)

            # Recent drawdown from rolling high
            recent_high = float(np.max(close[-self._lookback:]))
            current = float(close[-1])
            drawdown = (current - recent_high) / recent_high if recent_high > 0 else 0.0

            # Simple return over lookback
            start_price = float(close[-self._lookback])
            simple_return = (current - start_price) / start_price if start_price > 0 else 0.0

            indicators = {
                "realized_vol": round(realized_vol, 6),
                "adx": round(adx, 2),
                "drawdown": round(drawdown, 4),
                "simple_return": round(simple_return, 4),
            }

            # Classification logic
            regime, confidence = self._classify(
                realized_vol, adx, drawdown, simple_return,
            )

            return self._build_state(regime, confidence, indicators)

        except Exception as exc:
            logger.error("regime_detection_error", error=str(exc))
            return self._default_regime("error")

    def _approximate_adx(self, df: pd.DataFrame) -> float:
        """Simplified ADX: ratio of net move to total absolute moves.

        High ratio → strong trend (directional). Low ratio → choppy.
        Scaled to 0-100 for compatibility with ADX thresholds.
        """
        close = df["close"].values.astype(float)
        if len(close) < self._lookback + 1:
            return 0.0
        segment = close[-self._lookback - 1:]
        abs_moves = np.abs(np.diff(segment))
        total_abs = float(np.sum(abs_moves))
        if total_abs == 0:
            return 0.0
        net_move = abs(float(segment[-1] - segment[0]))
        # Efficiency ratio: 1.0 = perfectly directional, 0.0 = perfectly choppy
        efficiency = net_move / total_abs
        return efficiency * 100.0

    def _classify(
        self,
        vol: float,
        adx: float,
        drawdown: float,
        simple_return: float,
    ) -> tuple[str, float]:
        """Return (regime, confidence) based on indicators."""
        # RISK_OFF: significant drawdown
        if drawdown <= self._dd_risk_off:
            confidence = min(abs(drawdown) / 0.10, 1.0)
            return "RISK_OFF", confidence

        # HIGH_VOL: very high realized volatility
        if vol >= self._vol_high:
            confidence = min(vol / (self._vol_high * 2), 1.0)
            return "HIGH_VOL", confidence

        # TRENDING: strong directional movement (high efficiency ratio or large return)
        if adx >= self._adx_trend or abs(simple_return) > 0.05:
            confidence = min(max(adx / 50.0, abs(simple_return) / 0.10), 1.0)
            return "TRENDING", confidence

        # CHOPPY: low ADX AND low absolute return — price going nowhere
        if adx < self._adx_trend * 0.4 and abs(simple_return) < 0.02:
            confidence = 0.6
            return "CHOPPY", confidence

        # Default: RISK_ON (normal conditions)
        return "RISK_ON", 0.7

    def _build_state(
        self, regime: str, confidence: float, indicators: dict,
    ) -> RegimeState:
        """Build RegimeState from regime classification."""
        adj = REGIME_ADJUSTMENTS.get(regime, {"sl_mult": 1.0, "tp_mult": 1.0})

        # Kelly multiplier: reduce sizing in adverse regimes
        kelly_mult_map = {
            "RISK_ON": 1.0,
            "RISK_OFF": 0.5,
            "HIGH_VOL": 0.7,
            "TRENDING": 1.1,
            "CHOPPY": 0.6,
        }

        # Edge threshold: require more edge in adverse regimes
        edge_threshold_map = {
            "RISK_ON": 0.08,
            "RISK_OFF": 0.10,
            "HIGH_VOL": 0.08,
            "TRENDING": 0.08,
            "CHOPPY": 0.10,
        }

        # Model weight overrides per regime (empty dict = use defaults)
        weight_overrides: dict = {}
        if regime == "TRENDING":
            weight_overrides = {"MomRegime": 1.2, "TechConf": 1.1}
        elif regime == "HIGH_VOL":
            weight_overrides = {"VolSurf": 1.3}
        elif regime == "RISK_OFF":
            weight_overrides = {"FundBasis": 1.2, "SentComp": 1.1}

        return RegimeState(
            regime=regime,
            confidence=confidence,
            kelly_mult=kelly_mult_map.get(regime, 1.0),
            edge_threshold=edge_threshold_map.get(regime, 0.08),
            sl_mult=adj["sl_mult"],
            tp_mult=adj["tp_mult"],
            model_weight_overrides=weight_overrides,
            indicators=indicators,
        )

    def _default_regime(self, reason: str) -> RegimeState:
        """Return conservative RISK_ON regime when detection fails."""
        logger.warning("regime_fallback", reason=reason)
        return RegimeState(
            regime="RISK_ON",
            confidence=0.0,
            kelly_mult=1.0,
            edge_threshold=0.08,
            sl_mult=1.0,
            tp_mult=1.0,
            model_weight_overrides={},
            indicators={"fallback_reason": reason},
        )

    @staticmethod
    def get_regime_adjustments(regime: str) -> dict:
        """Static lookup for regime adjustment multipliers."""
        return REGIME_ADJUSTMENTS.get(regime, {"sl_mult": 1.0, "tp_mult": 1.0})
