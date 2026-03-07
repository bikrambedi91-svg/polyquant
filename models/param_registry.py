"""Versioned parameter storage, constraint validation, and default initialization.

Central store for all model parameter sets — current, historical, and experimental.
Every param set has a model_name, timeframe, version, values, status, performance, and lineage.
"""

import copy
from datetime import datetime, timezone

import structlog

from models.base import ModelParams

logger = structlog.get_logger(__name__)

# ── Parameter Ranges & Constraints (from build spec) ──

PARAM_RANGES: dict[str, dict[str, tuple]] = {
    "MomRegime": {
        "adx_period": (6, 25),
        "ema_fast": (5, 30),
        "ema_slow": (15, 80),
        "adx_threshold": (15, 35),
        "lookback": (50, 250),
    },
    "FundBasis": {
        "neg_threshold": (-0.0005, -0.00005),
        "pos_threshold": (0.0002, 0.001),
        "rolling_periods": (2, 8),
        "contrarian_mult": (0.5, 2.0),
    },
    "ChainFlow": {
        "outflow_zscore": (0.8, 3.0),
        "inflow_zscore": (0.8, 3.0),
        "rolling_window_hrs": (1, 24),
        "decay_rate": (0.5, 1.0),
    },
    "VolSurf": {
        "skew_fear": (-15.0, -1.0),
        "skew_greed": (1.0, 15.0),
        "iv_lookback_days": (7, 90),
        "pc_ratio_threshold": (0.8, 2.0),
    },
    "SentComp": {
        "fear_threshold": (10, 35),
        "greed_threshold": (65, 90),
        "contrarian_mult": (1.0, 3.0),
        "social_weight": (0.0, 0.8),
    },
    "TechConf": {
        "rsi_period": (5, 25),
        "rsi_bull": (50, 65),
        "rsi_bear": (35, 50),
        "macd_fast": (5, 20),
        "macd_slow": (15, 40),
        "macd_signal": (3, 15),
        "bb_period": (10, 30),
        "bb_std": (1.5, 3.0),
        "volume_avg_period": (10, 40),
        "confluence_threshold": (2, 5),
    },
    "CLOBSignal": {
        "imbalance_threshold": (1.1, 2.0),
        "trade_size_threshold": (200, 2000),
        "boost_factor": (0.05, 0.20),
        "lookback_seconds": (60, 300),
    },
}

# ── Param Constraints (cross-field validation) ──

PARAM_CONSTRAINTS: dict[str, list[tuple[str, str, str]]] = {
    # (field_a, operator, field_b) — field_a must be {operator} field_b
    "MomRegime": [("ema_fast", "<", "ema_slow")],
    "TechConf": [
        ("rsi_bear", "<", "rsi_bull"),
        ("macd_fast", "<", "macd_slow"),
    ],
}

# ── Default Parameter Values (from build spec) ──

DEFAULT_PARAMS: dict[str, dict[str, dict]] = {
    "MomRegime": {
        "5m": {"adx_period": 10, "ema_fast": 8, "ema_slow": 21, "adx_threshold": 20, "lookback": 100},
        "15m": {"adx_period": 12, "ema_fast": 12, "ema_slow": 26, "adx_threshold": 22, "lookback": 100},
        "1h": {"adx_period": 14, "ema_fast": 20, "ema_slow": 50, "adx_threshold": 25, "lookback": 100},
        "4h": {"adx_period": 14, "ema_fast": 20, "ema_slow": 50, "adx_threshold": 25, "lookback": 100},
        "daily": {"adx_period": 14, "ema_fast": 20, "ema_slow": 50, "adx_threshold": 25, "lookback": 100},
    },
    "FundBasis": {
        "5m": {"neg_threshold": -0.0001, "pos_threshold": 0.0005, "rolling_periods": 3, "contrarian_mult": 1.0},
        "15m": {"neg_threshold": -0.0001, "pos_threshold": 0.0005, "rolling_periods": 3, "contrarian_mult": 1.0},
        "1h": {"neg_threshold": -0.0001, "pos_threshold": 0.0005, "rolling_periods": 3, "contrarian_mult": 1.0},
        "4h": {"neg_threshold": -0.0001, "pos_threshold": 0.0005, "rolling_periods": 3, "contrarian_mult": 1.0},
        "daily": {"neg_threshold": -0.0001, "pos_threshold": 0.0005, "rolling_periods": 3, "contrarian_mult": 1.0},
    },
    "ChainFlow": {
        "5m": {"outflow_zscore": 1.5, "inflow_zscore": 1.5, "rolling_window_hrs": 4, "decay_rate": 0.9},
        "15m": {"outflow_zscore": 1.5, "inflow_zscore": 1.5, "rolling_window_hrs": 4, "decay_rate": 0.9},
        "1h": {"outflow_zscore": 1.5, "inflow_zscore": 1.5, "rolling_window_hrs": 4, "decay_rate": 0.9},
        "4h": {"outflow_zscore": 1.5, "inflow_zscore": 1.5, "rolling_window_hrs": 4, "decay_rate": 0.9},
        "daily": {"outflow_zscore": 1.5, "inflow_zscore": 1.5, "rolling_window_hrs": 12, "decay_rate": 0.9},
    },
    "VolSurf": {
        "5m": {"skew_fear": -5.0, "skew_greed": 5.0, "iv_lookback_days": 30, "pc_ratio_threshold": 1.2},
        "15m": {"skew_fear": -5.0, "skew_greed": 5.0, "iv_lookback_days": 30, "pc_ratio_threshold": 1.2},
        "1h": {"skew_fear": -5.0, "skew_greed": 5.0, "iv_lookback_days": 30, "pc_ratio_threshold": 1.2},
        "4h": {"skew_fear": -5.0, "skew_greed": 5.0, "iv_lookback_days": 30, "pc_ratio_threshold": 1.2},
        "daily": {"skew_fear": -5.0, "skew_greed": 5.0, "iv_lookback_days": 30, "pc_ratio_threshold": 1.2},
    },
    "SentComp": {
        "5m": {"fear_threshold": 25, "greed_threshold": 75, "contrarian_mult": 1.5, "social_weight": 0.3},
        "15m": {"fear_threshold": 25, "greed_threshold": 75, "contrarian_mult": 1.5, "social_weight": 0.3},
        "1h": {"fear_threshold": 25, "greed_threshold": 75, "contrarian_mult": 1.5, "social_weight": 0.3},
        "4h": {"fear_threshold": 25, "greed_threshold": 75, "contrarian_mult": 1.5, "social_weight": 0.3},
        "daily": {"fear_threshold": 25, "greed_threshold": 75, "contrarian_mult": 1.5, "social_weight": 0.3},
    },
    "TechConf": {
        "5m": {"rsi_period": 10, "rsi_bull": 55, "rsi_bear": 45, "macd_fast": 8, "macd_slow": 21,
               "macd_signal": 5, "bb_period": 15, "bb_std": 2.0, "volume_avg_period": 15, "confluence_threshold": 3},
        "15m": {"rsi_period": 12, "rsi_bull": 55, "rsi_bear": 45, "macd_fast": 10, "macd_slow": 22,
                "macd_signal": 7, "bb_period": 18, "bb_std": 2.0, "volume_avg_period": 18, "confluence_threshold": 3},
        "1h": {"rsi_period": 14, "rsi_bull": 55, "rsi_bear": 45, "macd_fast": 12, "macd_slow": 26,
               "macd_signal": 9, "bb_period": 20, "bb_std": 2.0, "volume_avg_period": 20, "confluence_threshold": 3},
        "4h": {"rsi_period": 14, "rsi_bull": 55, "rsi_bear": 45, "macd_fast": 12, "macd_slow": 26,
               "macd_signal": 9, "bb_period": 20, "bb_std": 2.0, "volume_avg_period": 20, "confluence_threshold": 3},
        "daily": {"rsi_period": 14, "rsi_bull": 55, "rsi_bear": 45, "macd_fast": 12, "macd_slow": 26,
                  "macd_signal": 9, "bb_period": 20, "bb_std": 2.0, "volume_avg_period": 20, "confluence_threshold": 3},
    },
    "CLOBSignal": {
        "5m": {"imbalance_threshold": 1.3, "trade_size_threshold": 500, "boost_factor": 0.10, "lookback_seconds": 120},
        "15m": {"imbalance_threshold": 1.3, "trade_size_threshold": 500, "boost_factor": 0.10, "lookback_seconds": 120},
        "1h": {"imbalance_threshold": 1.3, "trade_size_threshold": 500, "boost_factor": 0.10, "lookback_seconds": 120},
        "4h": {"imbalance_threshold": 1.3, "trade_size_threshold": 500, "boost_factor": 0.10, "lookback_seconds": 120},
        "daily": {"imbalance_threshold": 1.3, "trade_size_threshold": 500, "boost_factor": 0.10, "lookback_seconds": 120},
    },
}


def validate_params(model_name: str, values: dict) -> tuple[bool, str]:
    """Validate parameter values against defined ranges and constraints.

    Returns (True, "") if valid, (False, reason) if invalid.
    """
    ranges = PARAM_RANGES.get(model_name, {})
    for param_name, (lo, hi) in ranges.items():
        if param_name in values:
            val = values[param_name]
            if val < lo or val > hi:
                return False, f"{param_name}={val} out of range [{lo}, {hi}]"

    constraints = PARAM_CONSTRAINTS.get(model_name, [])
    for field_a, op, field_b in constraints:
        if field_a in values and field_b in values:
            va, vb = values[field_a], values[field_b]
            if op == "<" and not (va < vb):
                return False, f"Constraint violated: {field_a}({va}) must be < {field_b}({vb})"
            elif op == ">" and not (va > vb):
                return False, f"Constraint violated: {field_a}({va}) must be > {field_b}({vb})"

    return True, ""


class ParamRegistry:
    """Central store for all model parameter sets — current, historical, experimental.

    Stores in-memory for now (persisted to DB via learning_log in later phases).
    """

    def __init__(self):
        # (model_name, timeframe) -> list of ModelParams (ordered by version)
        self._store: dict[tuple[str, str], list[ModelParams]] = {}
        # (model_name, timeframe) -> index into _store for the active version
        self._active: dict[tuple[str, str], int] = {}

    def initialize_defaults(self) -> None:
        """Seed all 7 models with their default params for all timeframes."""
        for model_name, tf_params in DEFAULT_PARAMS.items():
            for timeframe, values in tf_params.items():
                key = (model_name, timeframe)
                params = ModelParams(
                    values=copy.deepcopy(values),
                    version=1,
                    parent_version=0,
                    performance={"brier_30d": 0.25, "trades": 0, "win_rate": 0.0},
                )
                self._store[key] = [params]
                self._active[key] = 0
        logger.info("param_registry_initialized", models=len(DEFAULT_PARAMS))

    def get_active_params(self, model_name: str, timeframe: str) -> ModelParams:
        """Return the current active parameter set."""
        key = (model_name, timeframe)
        if key not in self._store:
            raise KeyError(f"No params for {model_name}/{timeframe}")
        idx = self._active[key]
        return self._store[key][idx]

    def save_new_version(
        self,
        model_name: str,
        timeframe: str,
        params: ModelParams,
        status: str = "PROBATION",
    ) -> ModelParams:
        """Save a new parameter version. Status: PROBATION or ACTIVE."""
        key = (model_name, timeframe)
        if key not in self._store:
            self._store[key] = []
            self._active[key] = 0

        # Assign next version number
        existing = self._store[key]
        next_version = max((p.version for p in existing), default=0) + 1
        params.version = next_version
        params.created_at = datetime.now(timezone.utc).isoformat()

        # Validate before saving
        valid, reason = validate_params(model_name, params.values)
        if not valid:
            raise ValueError(f"Invalid params for {model_name}: {reason}")

        self._store[key].append(params)

        if status == "ACTIVE":
            self._active[key] = len(self._store[key]) - 1

        logger.info(
            "param_version_saved",
            model=model_name,
            timeframe=timeframe,
            version=next_version,
            status=status,
        )
        return params

    def promote(self, model_name: str, timeframe: str, version: int) -> None:
        """Promote a PROBATION param set to ACTIVE. Old ACTIVE becomes historical."""
        key = (model_name, timeframe)
        entries = self._store.get(key, [])
        for i, p in enumerate(entries):
            if p.version == version:
                self._active[key] = i
                logger.info("param_promoted", model=model_name, timeframe=timeframe, version=version)
                return
        raise KeyError(f"Version {version} not found for {model_name}/{timeframe}")

    def retire(self, model_name: str, timeframe: str, version: int, reason: str) -> None:
        """Mark a param version as retired. Does NOT delete — keeps for history."""
        key = (model_name, timeframe)
        entries = self._store.get(key, [])
        for p in entries:
            if p.version == version:
                p.performance["retired"] = True
                p.performance["retire_reason"] = reason
                logger.info("param_retired", model=model_name, timeframe=timeframe, version=version, reason=reason)
                # If this was the active version, leave active pointing to it
                # (caller should promote a replacement)
                return
        raise KeyError(f"Version {version} not found for {model_name}/{timeframe}")

    def get_lineage(self, model_name: str, timeframe: str) -> list[ModelParams]:
        """Return full evolution history of params for this model+timeframe."""
        key = (model_name, timeframe)
        return list(self._store.get(key, []))

    def get_all_active(self) -> dict[tuple[str, str], ModelParams]:
        """Return all active param sets keyed by (model_name, timeframe)."""
        result = {}
        for key, idx in self._active.items():
            result[key] = self._store[key][idx]
        return result
