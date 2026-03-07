"""Project-wide constants — assets, timeframes, API URLs, fees, weights, thresholds."""

# ── Tradeable Assets ──
ASSETS: list[str] = ["BTC", "ETH", "SOL", "XRP"]

# ── Timeframes ──
MARKET_TIMEFRAMES: list[str] = ["5m", "15m", "1h", "4h", "daily"]
MODEL_TIMEFRAMES: list[str] = ["5m", "15m", "1h", "4h", "24h"]

# ── Polymarket API Endpoints ──
POLYMARKET_CRYPTO_TAG_ID: int = 21
GAMMA_API_BASE: str = "https://gamma-api.polymarket.com"

# Timeframe-specific Gamma API tag IDs for UP/DOWN markets.
# These return ONLY the UP/DOWN binary markets for each timeframe,
# instead of all crypto markets (tag_id=21 returns price targets, monthly, etc.).
UP_DOWN_TAG_IDS: dict[str, int] = {
    "15m": 102467,
    "1h": 102175,
    "4h": 102531,
}
CLOB_API_BASE: str = "https://clob.polymarket.com"
DATA_API_BASE: str = "https://data-api.polymarket.com"
CLOB_WS_URL: str = "wss://ws-subscriptions-clob.polymarket.com"

# ── Taker Fee Model ──
# Max taker fee at 50% probability per market duration.
# Fee curve: fee = max_fee * 2 * price * (1 - price)
# Fee is highest at price=0.50, zero at price extremes (0 or 1).
# Maker orders are FREE and earn daily USDC rebates.
TAKER_FEE_MAX: dict[str, float] = {
    "5m": 0.0156,   # 1.56% max at 50% price
    "15m": 0.0156,  # 1.56% max (was 3.0%, updated March 2026)
    "1h": 0.0156,   # 1.56% max (was free, fees introduced March 2026)
    "4h": 0.0156,   # 1.56% max (was free, fees introduced March 2026)
    "daily": 0.0156,
    "weekly": 0.0156,
}

# Maker fee is always 0% on Polymarket + earns daily USDC rebates.
# All entries use maker orders (GTC limit at best_ask - 0.01).
# Only SL emergency exits use taker (market sell).
MAKER_FEE: float = 0.0


def calculate_taker_fee(timeframe: str, share_price: float) -> float:
    """Compute actual taker fee for a given timeframe and share price.

    fee = max_fee_rate × 2 × price × (1 - price)
    """
    max_fee = TAKER_FEE_MAX.get(timeframe, 0.0)
    return max_fee * 2.0 * share_price * (1.0 - share_price)


# ── Volume Thresholds ──
MIN_VOLUME: dict[str, int] = {
    "5m": 5_000,
    "15m": 15_000,
    "1h": 50_000,
    "4h": 100_000,
    "daily": 150_000,
    "weekly": 150_000,
}

# ── Default Model Weights by Timeframe ──
# From CLAUDE.md (authoritative source).
# NOTE: ChainFlow & SentimentComp are 0 on 5m/15m (stale data).
# NOTE: CLOBSignal is 0 on 4h (too noisy on long horizons).
DEFAULT_MODEL_WEIGHTS: dict[str, dict[str, float]] = {
    "5m": {
        "MomRegime": 0.20, "FundBasis": 0.05, "ChainFlow": 0.00,
        "VolSurf": 0.05, "SentComp": 0.00, "TechConf": 0.35, "CLOBSignal": 0.35,
    },
    "15m": {
        "MomRegime": 0.20, "FundBasis": 0.10, "ChainFlow": 0.00,
        "VolSurf": 0.08, "SentComp": 0.00, "TechConf": 0.32, "CLOBSignal": 0.30,
    },
    "1h": {
        "MomRegime": 0.18, "FundBasis": 0.18, "ChainFlow": 0.12,
        "VolSurf": 0.14, "SentComp": 0.08, "TechConf": 0.20, "CLOBSignal": 0.10,
    },
    "4h": {
        "MomRegime": 0.16, "FundBasis": 0.22, "ChainFlow": 0.18,
        "VolSurf": 0.15, "SentComp": 0.13, "TechConf": 0.16, "CLOBSignal": 0.00,
    },
    "daily": {
        "MomRegime": 0.14, "FundBasis": 0.24, "ChainFlow": 0.18,
        "VolSurf": 0.14, "SentComp": 0.16, "TechConf": 0.14, "CLOBSignal": 0.00,
    },
}

# ── Model Names (canonical) ──
MODEL_NAMES: list[str] = [
    "MomRegime", "FundBasis", "ChainFlow",
    "VolSurf", "SentComp", "TechConf", "CLOBSignal",
]

# ── Default TP/SL (FLAT 20:10 — 2:1 R:R, no tiering, no regime adjustments) ──
# TP 20% / SL 10% → 2:1 reward:risk.  With YES>0.58 filter (70%+ WR),
# expected PnL per trade: 0.70 × $4.00 − 0.30 × $2.30 ≈ +$2.11.
# Break-even WR is only 36.5%, far below our observed 70-100%.
# SL 10% = 3-5c room (absorbs gapping), TP 20% = 5-7c target (captures
# the full mean-reversion swing on high-YES binary options).
DEFAULT_SL_PCT: float = 0.10
DEFAULT_TP_PCT: float = 0.20

# Fixed position size — no Kelly sizing
POSITION_SIZE_USD: float = 20.0

# Daily loss halt — fixed USD amount (stop trading for the day)
DAILY_LOSS_HALT_USD: float = 100.0

# Max hold time — exit regardless of P&L after this many seconds
MAX_HOLD_SECONDS: int = 600  # 10 minutes

# ── Trailing SL (Breakeven Trigger) ──
# When unrealized profit reaches this fraction of TP target, move SL to entry price.
# Raised from 0.50 to 0.75: 50% was too aggressive, caused whipsaw exits.
# BTC #2 would have hit TP (+$2.5) but trailing SL caused -$7.1 loss.
TRAILING_SL_TRIGGER: float = 0.75

# ── SL Slippage Simulation ──
# In paper mode, simulate taker slippage on SL exits.
# SL market sells fill worse than midpoint by this many cents.
# BUY_YES: exit_price = current - slippage (price drops further)
# BUY_NO: exit_price = current + slippage (YES price rises further, bad for NO holder)
SL_SLIPPAGE_CENTS: float = 0.015  # 1.5 cents

# ── Spread-Based Entry Filter ──
# Reject trades when bid-ask spread is too wide (maker fill unlikely in live).
# Spread = best_ask - best_bid. If > this threshold, skip trade.
MAX_ENTRY_SPREAD: float = 0.04  # 4 cents


def get_tp_pct_for_confidence(confidence: int) -> float:
    """Return flat TP percentage (20% regardless of confidence)."""
    return DEFAULT_TP_PCT


# ── DEPRECATED — old absolute TP/SL (kept for learning engine migration) ──
DEFAULT_SL: dict[str, float] = {
    "5m": 0.08, "15m": 0.10, "1h": 0.12, "4h": 0.15, "daily": 0.18,
}
DEFAULT_TP_OFFSET: float = 0.05

# ── Regime Types ──
REGIMES: list[str] = ["RISK_ON", "RISK_OFF", "HIGH_VOL", "TRENDING", "CHOPPY"]

# ── Regime Adjustments (multipliers applied to TP/SL) ──
REGIME_ADJUSTMENTS: dict[str, dict[str, float]] = {
    "RISK_OFF": {"sl_mult": 0.80, "tp_mult": 0.90},   # Tighten SL 20%, TP 10%
    "HIGH_VOL": {"sl_mult": 1.30, "tp_mult": 1.20},   # Widen SL 30%, TP 20%
    "TRENDING": {"sl_mult": 1.00, "tp_mult": 1.25},   # Widen TP 25%, SL normal
    "CHOPPY":   {"sl_mult": 0.85, "tp_mult": 0.85},   # Tighten both 15%
    "RISK_ON":  {"sl_mult": 1.00, "tp_mult": 1.00},   # No adjustment
}

# ── Learning Engine Safety Rails ──
LEARNING_SAFETY_RAILS: dict = {
    "max_models_mutated_per_cycle": 1,
    "max_models_retired_per_cycle": 1,
    "min_active_models": 4,
    "min_trades_for_sl_optimization": 30,
    "min_trades_for_param_mutation": 80,
    "min_shadow_trades_for_promotion": 30,
    "max_param_change_pct": 0.50,
    "max_sl_change_per_cycle": 0.03,
    "max_tp_change_per_cycle": 0.03,
    "max_weight_change_per_cycle": 0.15,
    "optuna_walk_forward_split": 0.30,
    "optuna_overfit_threshold": 0.05,
}

# ── Kelly Fraction by Confidence ──
KELLY_FRACTIONS: dict[str, float] = {
    "low": 0.25,     # confidence < 75
    "medium": 0.40,  # confidence 75-85
    "high": 0.50,    # confidence > 85
}

# ── CCXT Exchange Config ──
CCXT_PRIMARY_EXCHANGE: str = "binance"
CCXT_FALLBACK_EXCHANGE: str = "coinbasepro"

# Map our asset names to ccxt symbol format
ASSET_SYMBOLS: dict[str, str] = {
    "BTC": "BTC/USDT",
    "ETH": "ETH/USDT",
    "SOL": "SOL/USDT",
    "XRP": "XRP/USDT",
}

# Map our timeframes to ccxt timeframe format
CCXT_TIMEFRAMES: dict[str, str] = {
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "24h": "1d",
    "daily": "1d",
}

# ── Cache TTLs (seconds) ──
CACHE_TTL: dict[str, int] = {
    "ohlcv_5m": 30,
    "ohlcv_15m": 60,
    "ohlcv_1h": 120,
    "ohlcv_4h": 300,
    "ohlcv_24h": 600,
    "funding": 60,
    "onchain": 300,
    "sentiment": 300,
    "orderbook": 10,
}
