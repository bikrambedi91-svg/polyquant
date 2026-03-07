# PolyQuant v3.0 — Complete Build Specification
# Self-Learning Crypto Quant × Polymarket Execution System
# Code → Test → Paper → Validate → Go Live → Keep Evolving

---

## PRIME DIRECTIVE

You are a senior Python engineer building a production trading system from scratch. You will write every line of code, test every module before moving on, run full integration tests, paper trade with real market data, validate profitability, and only then enable live execution.

**You do not hand-wave. You do not stub. You do not say "implement this later." Every function you write must work when called.**

**Build rule: No module is complete until its tests pass. No next module starts until the current one is tested. No paper trading starts until all modules pass integration tests. No live trading starts until paper trading proves profitability.**

**Learning rule: This system is never "done." Every trade generates data. That data feeds back into model parameters, ensemble weights, stop-loss levels, and strategy selection. The bot gets smarter with every cycle.**

---

## SECTION 0 — PROJECT OVERVIEW

### What We Are Building

A Python trading bot that:
1. Runs quantitative models on BTC, ETH, SOL, XRP to generate directional probability signals
2. Scans Polymarket's 5-minute, 15-minute, 1-hour, and 4-hour crypto prediction markets
3. Calculates edge by comparing our quant probabilities against Polymarket's implied prices
4. Executes YES/NO bets when edge exceeds thresholds, with adaptive take-profit and stop-loss
5. Tracks everything in a Streamlit dashboard with real-time P&L, calibration, and model analytics
6. Starts in paper mode, auto-graduates to live when performance criteria are met
7. **Continuously learns from every trade outcome** — mutates model parameters, retires broken strategies, generates new strategy variants, and adapts stop-loss/take-profit levels based on what actually works

### Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| Data/Math | pandas, numpy, scipy, ta (technical analysis), scikit-learn (learning engine) |
| Optimization | optuna (hyperparameter tuning), scipy.optimize |
| API Clients | httpx (async), ccxt (price feeds), web3/py_clob_client (Polymarket) |
| Database | SQLite (local dev), PostgreSQL (VPS production) |
| Dashboard | Streamlit |
| Task Scheduling | APScheduler (in-process) |
| Testing | pytest, pytest-asyncio, pytest-mock |
| Logging | structlog (JSON structured logging) |
| Config | pydantic-settings (.env based) |
| Deployment | Docker + docker-compose (VPS) |
| Dev Environment | Local Windows (WSL2 or native Python) |

### Project Structure

```
polyquant/
├── config/
│   ├── settings.py              # Pydantic settings (loads .env)
│   └── constants.py             # Asset list, timeframes, thresholds
├── models/
│   ├── base.py                  # Abstract base model class
│   ├── momentum_regime.py       # Model 1: ADX + DI trend regime
│   ├── funding_basis.py         # Model 2: Perp funding + futures basis
│   ├── chain_flow.py            # Model 3: Exchange net flows
│   ├── vol_surface.py           # Model 4: IV skew + term structure
│   ├── sentiment.py             # Model 5: Fear/Greed + social NLP
│   ├── tech_confluence.py       # Model 6: RSI/MACD/BB/VWAP confluence
│   ├── ensemble.py              # Bayesian ensemble aggregator
│   └── param_registry.py        # Stores current + historical parameter sets per model
├── learning/                    # *** NEW IN v3 — THE ADAPTIVE BRAIN ***
│   ├── model_evolver.py         # Detects underperformers, mutates params, spawns variants
│   ├── param_optimizer.py       # Optuna-based hyperparameter search on recent trade data
│   ├── strategy_graveyard.py    # Retired strategies with death-cause logging
│   ├── strategy_nursery.py      # New strategy variants in probation (paper-only)
│   ├── regime_detector.py       # Macro regime classification (risk-on, risk-off, chop)
│   ├── sl_tp_learner.py         # Adaptive stop-loss and take-profit optimizer
│   ├── feedback_db.py           # Stores every prediction vs outcome for learning
│   └── evolution_report.py      # Generates human-readable report of what changed and why
├── market/
│   ├── scanner.py               # Polymarket market discovery
│   ├── orderbook.py             # CLOB order book analysis
│   ├── resolution.py            # Resolution rules parser + risk scorer
│   └── pricing.py               # Fee/slippage adjusted implied prob
├── execution/
│   ├── paper_engine.py          # Paper trading execution simulator
│   ├── live_engine.py           # Live Polymarket CLOB execution
│   ├── position_manager.py      # Adaptive TP/SL/exit logic for binary positions
│   └── risk_manager.py          # Kelly sizing, limits, correlation
├── data/
│   ├── price_feed.py            # Real-time + historical OHLCV
│   ├── funding_feed.py          # Funding rate data
│   ├── onchain_feed.py          # Exchange flow data
│   ├── sentiment_feed.py        # Fear & Greed + social data
│   └── cache.py                 # In-memory cache with TTL
├── database/
│   ├── models.py                # SQLAlchemy ORM models
│   ├── trades.py                # Trade CRUD operations
│   ├── signals.py               # Signal history storage
│   ├── learning_log.py          # Stores all learning decisions + parameter snapshots
│   └── migrations.py            # DB schema setup
├── dashboard/
│   ├── app.py                   # Streamlit main app
│   ├── pages/
│   │   ├── overview.py          # Portfolio overview + P&L
│   │   ├── active_positions.py  # Live positions table
│   │   ├── trade_history.py     # Full trade ledger
│   │   ├── analytics.py         # Calibration, model attribution
│   │   ├── risk_monitor.py      # Exposure limits, drawdown
│   │   ├── signal_health.py     # Model heatmap, freshness
│   │   └── learning_lab.py      # *** NEW — Learning & evolution dashboard ***
│   └── components/
│       ├── charts.py            # Reusable chart components
│       └── tables.py            # Reusable table components
├── orchestrator/
│   ├── main_loop.py             # Master scheduling + orchestration
│   ├── pipeline.py              # Signal → Edge → Size → Execute pipeline
│   └── graduation.py            # Paper → Live graduation logic
├── tests/
│   ├── unit/
│   │   ├── test_models/         # One test file per quant model
│   │   ├── test_market/         # Scanner, orderbook, pricing tests
│   │   ├── test_execution/      # Paper engine, risk manager tests
│   │   ├── test_data/           # Feed tests with mocked APIs
│   │   └── test_learning/       # *** NEW — Learning engine tests ***
│   ├── integration/
│   │   ├── test_pipeline.py     # Full signal-to-trade pipeline
│   │   ├── test_dashboard.py    # Dashboard renders without crash
│   │   ├── test_database.py     # DB read/write cycle
│   │   └── test_learning_cycle.py  # *** NEW — Full learning loop test ***
│   └── fixtures/
│       ├── mock_prices.json
│       ├── mock_orderbook.json
│       ├── mock_markets.json
│       └── mock_trade_history.json  # *** NEW — 200+ simulated trades for learning tests ***
├── scripts/
│   ├── seed_mock_data.py
│   ├── run_backtest.py
│   └── deploy.sh
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── pytest.ini
└── README.md
```

---

## SECTION 1 — BUILD PIPELINE (MANDATORY ORDER)

You MUST build in this exact sequence. Each phase has a gate — you cannot pass the gate until all tests in that phase are green.

### Phase 1: Foundation (config, data feeds, database)

**Build:**
1. `config/settings.py` — Load from `.env`: API keys, bankroll, mode (paper/live), risk params, learning params
2. `config/constants.py` — Define:
   ```python
   ASSETS = ["BTC", "ETH", "SOL", "XRP"]
   MARKET_TIMEFRAMES = ["5m", "15m", "1h", "4h"]  # Polymarket market durations
   MODEL_TIMEFRAMES = ["5m", "15m", "1h", "4h", "24h"]  # Quant model horizons
   ```
3. `data/price_feed.py` — Async OHLCV fetcher via ccxt (Binance primary, Coinbase fallback)
4. `data/funding_feed.py` — Binance Futures funding rate endpoint
5. `data/onchain_feed.py` — CryptoQuant or free alternative for exchange net flows
6. `data/sentiment_feed.py` — Alternative.me Fear & Greed API + optional social scoring
7. `data/cache.py` — In-memory TTL cache so we don't spam APIs
8. `database/models.py` — SQLAlchemy ORM models for trades, signals, portfolio state, learning logs
9. `database/trades.py` — CRUD: create_trade, update_trade, get_active, get_history
10. `database/signals.py` — Store and query historical signal snapshots
11. `database/learning_log.py` — Store parameter changes, model retirements, evolution events

**Test (Gate 1):**
```
tests/unit/test_data/test_price_feed.py    — Mock ccxt, verify OHLCV parsing
tests/unit/test_data/test_funding_feed.py  — Mock API, verify rate parsing
tests/unit/test_data/test_cache.py         — TTL expiry works correctly
tests/unit/test_database/test_trades.py    — Full CRUD cycle on SQLite
tests/unit/test_database/test_signals.py   — Store and retrieve signals
tests/unit/test_database/test_learning_log.py — Store and retrieve learning events
```
**Gate 1 rule:** ALL test files pass. Data feeds return correctly structured DataFrames. DB reads back what it writes. Learning log stores and retrieves parameter snapshots.

---

### Phase 2: Quant Models (the signal brain)

**Build each model following this interface:**

```python
# models/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

@dataclass
class ModelParams:
    """Every model's tunable parameters live here. This is what the learning engine mutates."""
    values: dict          # e.g., {"adx_period": 14, "ema_fast": 20, "ema_slow": 50}
    version: int          # Incremented every time params are updated by learning engine
    created_at: str       # ISO timestamp of when this param set was created
    parent_version: int   # Which version these params evolved from (0 = original)
    performance: dict     # Rolling stats: {"brier_30d": 0.22, "trades": 45, "win_rate": 0.56}

@dataclass
class ModelOutput:
    asset: str
    timeframe: str
    prob_up: float        # 0.0 to 1.0
    confidence: int       # 0 to 100
    model_name: str
    param_version: int    # Which param set produced this signal (for attribution)
    key_drivers: list[str]
    raw_indicators: dict  # For debugging/dashboard

class BaseModel(ABC):
    def __init__(self, params: ModelParams):
        self.params = params

    @abstractmethod
    async def generate_signal(self, asset: str, timeframe: str, ohlcv: pd.DataFrame, **kwargs) -> ModelOutput:
        """Must return ModelOutput. Must not raise — return low confidence on failure."""
        pass

    def update_params(self, new_params: ModelParams):
        """Called by the learning engine when parameters are evolved."""
        self.params = new_params
```

**The 6 models and their timeframe-specific tuning:**

**Model 1 — MomentumRegime** (`models/momentum_regime.py`)
- Classifies market state: TRENDING_UP, TRENDING_DOWN, MEAN_REVERTING, CHOPPY
- In trending: prob_up follows trend direction. In mean-revert: prob_up fades recent move.

| Param | 5m (default) | 15m (default) | 1h (default) | 4h (default) | Learnable? |
|-------|------|-------|------|------|------------|
| ADX period | 10 | 12 | 14 | 14 | YES — range [6, 25] |
| EMA fast | 8 | 12 | 20 | 20 | YES — range [5, 30] |
| EMA slow | 21 | 26 | 50 | 50 | YES — range [15, 80] |
| ADX trending threshold | 20 | 22 | 25 | 25 | YES — range [15, 35] |
| Lookback candles | 100 | 100 | 100 | 100 | YES — range [50, 250] |

**Model 2 — FundingBasis** (`models/funding_basis.py`)
- Reads 8-hour funding rate and annualizes it
- Extreme negative funding (< threshold) → contrarian long signal
- Extreme positive funding (> threshold) → caution / contrarian short signal

| Param | Default | Learnable? |
|-------|---------|------------|
| Negative funding threshold | -0.01% | YES — range [-0.05%, -0.005%] |
| Positive funding threshold | 0.05% | YES — range [0.02%, 0.10%] |
| Rolling periods for trend | 3 | YES — range [2, 8] |
| Contrarian strength multiplier | 1.0 | YES — range [0.5, 2.0] |

**Model 3 — ChainFlow** (`models/chain_flow.py`)
- Exchange net flow (inflow minus outflow)
- Large outflows = accumulation = bullish, Large inflows = distribution = bearish

| Param | Default | Learnable? |
|-------|---------|------------|
| Outflow significance z-score | 1.5 | YES — range [0.8, 3.0] |
| Inflow significance z-score | 1.5 | YES — range [0.8, 3.0] |
| Rolling window (hours) | 4 | YES — range [1, 24] |
| Signal decay rate | 0.9 | YES — range [0.5, 1.0] |

**Model 4 — VolSurface** (`models/vol_surface.py`)
- BTC/ETH: Pull Deribit 25-delta risk reversal
- SOL/XRP: Use realized vol percentile + funding as proxy

| Param | Default | Learnable? |
|-------|---------|------------|
| Skew fear threshold | -5.0 | YES — range [-15.0, -1.0] |
| Skew greed threshold | 5.0 | YES — range [1.0, 15.0] |
| IV percentile lookback (days) | 30 | YES — range [7, 90] |
| Put/call OI ratio threshold | 1.2 | YES — range [0.8, 2.0] |

**Model 5 — SentimentComposite** (`models/sentiment.py`)
- Fear & Greed Index + optional social scoring
- Contrarian at extremes, confirming in mid-range

| Param | Default | Learnable? |
|-------|---------|------------|
| Extreme fear threshold | 25 | YES — range [10, 35] |
| Extreme greed threshold | 75 | YES — range [65, 90] |
| Contrarian multiplier at extremes | 1.5 | YES — range [1.0, 3.0] |
| Social sentiment weight | 0.3 | YES — range [0.0, 0.8] |

**Model 6 — TechConfluence** (`models/tech_confluence.py`)
- Counts how many of 5 indicators agree on direction

| Param | 5m (default) | 15m (default) | 1h (default) | 4h (default) | Learnable? |
|-------|------|-------|------|------|------------|
| RSI period | 10 | 12 | 14 | 14 | YES — range [5, 25] |
| RSI bullish threshold | 55 | 55 | 55 | 55 | YES — range [50, 65] |
| RSI bearish threshold | 45 | 45 | 45 | 45 | YES — range [35, 50] |
| MACD fast | 8 | 10 | 12 | 12 | YES — range [5, 20] |
| MACD slow | 21 | 22 | 26 | 26 | YES — range [15, 40] |
| MACD signal | 5 | 7 | 9 | 9 | YES — range [3, 15] |
| BB period | 15 | 18 | 20 | 20 | YES — range [10, 30] |
| BB std dev | 2.0 | 2.0 | 2.0 | 2.0 | YES — range [1.5, 3.0] |
| Volume avg period | 15 | 18 | 20 | 20 | YES — range [10, 40] |
| Confluence bullish threshold | 3/5 | 3/5 | 3/5 | 3/5 | YES — range [2/5, 5/5] |

**Parameter Registry** (`models/param_registry.py`)
```python
class ParamRegistry:
    """
    Central store for all model parameter sets — current, historical, and experimental.

    Every param set has:
    - model_name: which model it belongs to
    - timeframe: which timeframe it was tuned for
    - version: incrementing version number
    - values: the actual parameter dict
    - status: ACTIVE (in use), RETIRED (replaced by better version), PROBATION (experimental)
    - performance: rolling Brier score, win rate, trade count
    - lineage: parent_version → this version (tracks evolution chain)

    The learning engine reads from here, tests new params in PROBATION,
    and promotes/retires based on performance.
    """

    def get_active_params(self, model_name: str, timeframe: str) -> ModelParams:
        """Return the current active parameter set."""

    def save_new_version(self, model_name: str, timeframe: str, params: ModelParams, status: str):
        """Save a new parameter version (PROBATION or ACTIVE)."""

    def promote(self, model_name: str, timeframe: str, version: int):
        """Promote PROBATION params to ACTIVE, retire the old ACTIVE."""

    def retire(self, model_name: str, timeframe: str, version: int, reason: str):
        """Move params to RETIRED with death cause."""

    def get_lineage(self, model_name: str, timeframe: str) -> list[ModelParams]:
        """Return full evolution history of params for this model+timeframe."""
```

**Timeframe-Specific Model Weights (defaults — continuously updated by learning engine):**

| Model | 5m weight | 15m weight | 1h weight | 4h weight | Learnable? |
|-------|-----------|------------|-----------|-----------|------------|
| MomentumRegime | 0.25 | 0.22 | 0.18 | 0.16 | YES |
| FundingBasis | 0.10 | 0.14 | 0.20 | 0.22 | YES |
| ChainFlow | 0.05 | 0.08 | 0.15 | 0.18 | YES |
| VolSurface | 0.10 | 0.12 | 0.15 | 0.15 | YES |
| SentimentComposite | 0.05 | 0.08 | 0.12 | 0.13 | YES |
| TechConfluence | 0.45 | 0.36 | 0.20 | 0.16 | YES |

**Ensemble Aggregator** (`models/ensemble.py`)
```python
class EnsembleAggregator:
    def aggregate(self, signals: list[ModelOutput], timeframe: str) -> EnsembleOutput:
        """
        1. Look up CURRENT weight for each model at this timeframe (from ParamRegistry)
        2. Multiply by model's rolling Brier accuracy weight (from learning engine)
        3. Multiply by confidence_scalar = signal.confidence / 70 (normalized)
        4. Compute weighted average prob_up
        5. Compute ensemble_confidence, penalized by inter-model variance
        6. Flag disagreements where any model differs from ensemble by >12%
        7. Return EnsembleOutput with full breakdown including param_versions used
        """
```

**Test (Gate 2):**
```
tests/unit/test_models/test_momentum_regime.py        — Feed known trending data, verify classification
tests/unit/test_models/test_funding_basis.py          — Feed extreme negative funding, verify prob_up > 0.6
tests/unit/test_models/test_chain_flow.py             — Feed large outflow, verify bullish signal
tests/unit/test_models/test_vol_surface.py            — Feed steep put skew, verify fear detection
tests/unit/test_models/test_sentiment.py              — Feed Fear=15, verify contrarian bullish
tests/unit/test_models/test_tech_confluence.py        — Feed 4/5 bullish indicators, verify high prob_up
tests/unit/test_models/test_ensemble.py               — Verify weighted average matches hand calculation
tests/unit/test_models/test_ensemble_disagreement.py  — Inject outlier model, verify flag raised
tests/unit/test_models/test_param_registry.py         — Save, promote, retire params; verify lineage tracking
tests/unit/test_models/test_param_hot_swap.py         — Update model params at runtime, verify next signal uses new params
```
**Gate 2 rule:** ALL 10 test files pass. Each model respects its params from ParamRegistry. Hot-swapping params mid-run changes model behavior.

---

### Phase 3: Polymarket Integration (market discovery + order book)

**Build:**

1. `market/scanner.py`
   ```python
   class PolymarketScanner:
       async def discover_markets(self) -> list[CryptoMarket]:
           """
           1. Hit Gamma API: GET https://gamma-api.polymarket.com/markets?tag=crypto&active=true
           2. Filter to BTC/ETH/SOL/XRP markets
           3. Classify each market's timeframe:
              - Title contains "5 minute" or resolves within 5–6 min → 5m
              - Title contains "15 minute" or resolves within 14–16 min → 15m
              - Title contains "1 hour" or resolves within 55–65 min → 1h
              - Title contains "4 hour" or resolves within 3.5–4.5 hours → 4h
           4. Filter: volume > $150k (relax to $50k for 5m markets), time_to_resolution > 2 min
           5. Record: title, url, token_ids (YES and NO), resolution_source, resolution_datetime, resolution_criteria
           6. Return list sorted by volume descending
           """
   ```

2. `market/orderbook.py`
   ```python
   class OrderBookAnalyzer:
       async def analyze(self, token_id: str, intended_size_usd: float) -> OrderBookSnapshot:
           """
           1. Hit CLOB API: GET https://clob.polymarket.com/book?token_id={token_id}
           2. Parse top 10 bids and asks
           3. Calculate: spread (cents + bps), bid/ask imbalance, cumulative depth at 1%/2%/5% slippage
           4. Simulate walking the book for intended_size_usd → compute expected_slippage
           5. Detect whale trades: any single order > 2% of total book depth
           6. Return OrderBookSnapshot with all metrics
           """
   ```

3. `market/resolution.py`
   ```python
   class ResolutionAnalyzer:
       def assess_risk(self, market: CryptoMarket) -> ResolutionRisk:
           """
           Score resolution risk as LOW, MEDIUM, HIGH based on:
           - Is resolution source clearly defined?
           - Any timezone ambiguity?
           - Has this type of market had disputed resolutions before?
           - Could a flash crash cause misleading resolution?
           LOW = 0% penalty, MEDIUM = 1.5% penalty, HIGH = 3% penalty
           """
   ```

4. `market/pricing.py`
   ```python
   class PricingEngine:
       def effective_implied_prob(self, yes_price, fees_pct, expected_slippage) -> float:
           return yes_price + (fees_pct / 2) + expected_slippage

       def calculate_edge(self, our_prob, effective_implied, resolution_penalty) -> float:
           return abs(our_prob - effective_implied) - resolution_penalty

       def expected_value(self, our_prob, entry_price, action) -> float:
           if action == "BUY_YES":
               return our_prob - entry_price
           else:
               return (1 - our_prob) - (1 - entry_price)
   ```

**Test (Gate 3):**
```
tests/unit/test_market/test_scanner.py     — Mock Gamma API response, verify filtering + classification
tests/unit/test_market/test_orderbook.py   — Mock CLOB response, verify spread/depth/slippage calculations
tests/unit/test_market/test_resolution.py  — Feed markets with known ambiguities, verify risk scoring
tests/unit/test_market/test_pricing.py     — Hand-verify effective implied prob and edge calculations
```
**Gate 3 rule:** ALL 4 test files pass. Pricing math matches hand calculations exactly.

---

### Phase 4: Execution Engine (paper + live + ADAPTIVE TP/SL)

**Build:**

1. `execution/risk_manager.py`
   ```python
   class RiskManager:
       def __init__(self, settings):
           self.bankroll = settings.bankroll_usdc
           self.max_single_position_pct = 0.12
           self.max_per_asset_pct = 0.25
           self.max_total_exposure_pct = 0.60
           self.daily_drawdown_halt_pct = 0.08
           self.min_position_usd = 50

       def kelly_size(self, edge, odds, confidence) -> float:
           """
           kelly_fraction = edge / odds
           0.25x Kelly when confidence < 75
           0.40x Kelly when confidence 75-85
           0.50x Kelly when confidence > 85
           Cap at max_single_position_pct * bankroll
           Floor at min_position_usd
           """

       def check_limits(self, proposed_trade, active_positions) -> tuple[bool, str]:
           """Check ALL hard limits. Returns (allowed, reason)."""

       def detect_correlation(self, market_a, market_b) -> float:
           """Correlation scoring between two positions."""
   ```

2. `execution/position_manager.py` — **NOW WITH ADAPTIVE TP/SL**
   ```python
   class PositionManager:
       """
       Polymarket positions are binary (YES/NO tokens).
       TP/SL means selling your position on the CLOB when price moves.

       CRITICAL: TP and SL levels are NOT static. They start with defaults
       and are continuously adjusted by the SL/TP learning engine (learning/sl_tp_learner.py).

       The learning engine feeds optimized levels into this manager every recalibration cycle.
       """

       def __init__(self, sl_tp_learner: SLTPLearner):
           self.learner = sl_tp_learner
           # Defaults — overridden by learned values once enough data exists
           self.default_tp_offset = 0.05
           self.default_sl = {"5m": 0.08, "15m": 0.10, "1h": 0.12, "4h": 0.15}

       def calculate_tp_sl(self, trade) -> TPSLLevels:
           """
           1. Ask the SL/TP learner for current optimized levels for this asset+timeframe+regime
           2. If learner has enough data (50+ trades in this bucket), use learned levels
           3. If not enough data yet, use defaults
           4. Apply regime adjustment (from regime_detector):
              - RISK_OFF regime: tighten SL by 20%, tighten TP by 10% (protect capital)
              - HIGH_VOL regime: widen SL by 30% (avoid noise stopouts), widen TP by 20%
              - TRENDING regime: widen TP significantly (let winners run), keep SL normal
              - CHOPPY regime: tighten both (take small wins, cut losses fast)

           TAKE PROFIT logic:
             TP trigger = min(your_prob + tp_offset, 0.92)
             When market price reaches TP, your edge is gone → sell to lock profit

           STOP LOSS logic:
             SL trigger = entry_price - learned_sl_distance
             When market price drops to SL, thesis may be wrong → sell to cut loss

           TIME DECAY EXIT:
             If time_remaining < time_decay_pct (learned, default 15%) AND losing → exit
             If time_remaining < force_exit_pct (learned, default 5%) → exit regardless

           EDGE EVAPORATION EXIT:
             Refresh quant signals. If new ensemble_prob flips or edge < 3% → exit

           PARTIAL EXIT (advanced, enabled after 200+ trades):
             If position is profitable but edge is shrinking → sell 50%, keep 50%
             Learned from historical data: positions that partially exited vs full hold
           """

       async def monitor_positions(self, active_positions: list) -> list[ExitSignal]:
           """
           Called every cycle. For each position:
           1. Fetch current YES/NO price from CLOB
           2. Get current regime from regime_detector
           3. Get adaptive TP/SL levels from learner (may differ from entry-time levels)
           4. Check TP hit → ExitSignal(reason="take_profit", learned=True/False)
           5. Check SL hit → ExitSignal(reason="stop_loss", learned=True/False)
           6. Check time decay → ExitSignal(reason="time_decay")
           7. Check edge evaporation (re-run quant signals) → ExitSignal(reason="edge_evaporated")
           8. Check partial exit conditions → ExitSignal(reason="partial_exit", pct=0.5)
           9. If none triggered → continue holding

           CRITICAL: Every exit decision and its outcome is logged to feedback_db
           so the learning engine can evaluate whether the exit was correct.
           """
   ```

3. `execution/paper_engine.py`
   ```python
   class PaperEngine:
       async def execute_buy(self, market, action, size_usd, limit_price) -> PaperFill:
           """
           1. Fetch current CLOB
           2. Simulate fill: walk the book for size_usd, compute avg fill price
           3. If avg fill > limit_price → REJECTED
           4. Create Trade record in DB with status=ACTIVE
           5. Store entry snapshot: all quant signals, param versions, regime, TP/SL levels
           6. Return PaperFill
           """

       async def execute_sell(self, trade_id, reason) -> PaperFill:
           """
           1. Simulate sell on CLOB
           2. Compute realized P&L
           3. Update Trade record: status=CLOSED, pnl, exit_reason
           4. *** CRITICAL: Log to feedback_db for learning engine ***
              - Record: entry signals vs exit outcome, was TP/SL the right call,
                which models were accurate, which weren't
           """

       async def check_resolution(self, trade) -> ResolutionResult | None:
           """If market resolved, compute final P&L and log to feedback_db."""
   ```

4. `execution/live_engine.py` — Same interface as PaperEngine but uses py_clob_client

**Test (Gate 4):**
```
tests/unit/test_execution/test_risk_manager.py        — Kelly math, limit checks, correlation detection
tests/unit/test_execution/test_position_manager.py    — Verify TP/SL triggers with BOTH default and learned levels
                                                       — Test regime-adjusted TP/SL (tighter in risk-off, wider in high-vol)
                                                       — Test time_decay exit
                                                       — Test edge_evaporation exit
                                                       — Test partial exit logic
tests/unit/test_execution/test_paper_engine.py        — Buy/sell/resolution simulation with feedback logging
tests/unit/test_execution/test_adaptive_sl.py         — Feed position manager with mock learned SL levels
                                                       — Verify it uses learned levels when available
                                                       — Verify it falls back to defaults when not enough data
```
**Gate 4 rule:** ALL test files pass. Adaptive TP/SL correctly uses learned levels when available and falls back to defaults otherwise.

---

### Phase 5: THE LEARNING ENGINE (the brain that evolves)

**This is the core differentiator. A static bot will lose edge as markets adapt. A learning bot stays ahead.**

**Build:**

1. `learning/feedback_db.py`
   ```python
   class FeedbackDB:
       """
       Every trade produces a feedback record. This is the raw material the learning engine consumes.

       FEEDBACK RECORD (stored on trade close or resolution):
       {
           trade_id: str,
           asset: str,
           timeframe: str,
           regime_at_entry: str,          # risk-on, risk-off, high-vol, trending, choppy
           ensemble_prob_at_entry: float,
           market_implied_at_entry: float,
           edge_at_entry: float,
           confidence_at_entry: int,
           model_signals_at_entry: {       # Each model's output + param version
               "MomRegime": {"prob_up": 0.62, "confidence": 70, "param_version": 3},
               "FundBasis": {"prob_up": 0.71, "confidence": 80, "param_version": 2},
               ...
           },
           action: str,                    # BUY_YES or BUY_NO
           entry_price: float,
           exit_price: float,
           exit_reason: str,              # resolution, take_profit, stop_loss, time_decay, edge_evaporated
           tp_level_used: float,
           sl_level_used: float,
           was_tp_sl_learned: bool,       # Were these learned or default levels?
           pnl_usd: float,
           result: str,                   # WON, LOST
           resolution_outcome: str,       # YES or NO
           actual_outcome_matched_prediction: bool,
           duration_seconds: int,
           max_favorable_excursion: float,   # Best price reached during hold (for TP optimization)
           max_adverse_excursion: float,     # Worst price reached during hold (for SL optimization)
           price_at_resolution: float,       # What was the final price at resolution (even if exited early)
           would_have_won_if_held: bool,     # If we exited early, would holding to resolution have won?
       }
       """
   ```

2. `learning/regime_detector.py`
   ```python
   class RegimeDetector:
       """
       Classifies the current macro regime. This affects model weights, TP/SL levels,
       and overall aggressiveness.

       REGIMES:
       - RISK_ON: BTC trending up, funding neutral/positive, F&G > 50, low realized vol
       - RISK_OFF: BTC trending down, negative sentiment, F&G < 30, correlations spiking
       - HIGH_VOL: ATR(14) > 90th percentile of last 30 days, large funding swings
       - TRENDING: ADX > 30 on 4h, clear directional bias across multiple indicators
       - CHOPPY: ADX < 18 on 4h, frequent direction changes, mean-reverting action

       Regime affects:
       1. Model weights (trending → boost MomentumRegime weight)
       2. TP/SL levels (high-vol → widen stops)
       3. Position sizing (risk-off → reduce Kelly multiplier)
       4. Edge threshold (choppy → increase min edge requirement to 10%)
       5. Which models to trust more (choppy → trust TechConfluence less, trust FundingBasis more)
       """

       def detect(self, price_data: dict, funding_data: dict, sentiment: dict) -> Regime:
           """Returns current Regime with classification + confidence."""

       def get_regime_adjustments(self, regime: Regime) -> RegimeAdjustments:
           """
           Returns specific adjustments to apply:
           {
               "kelly_multiplier": 0.8,       # Scale down in risk-off
               "edge_threshold_override": 0.10, # Raise in choppy
               "sl_multiplier": 1.3,           # Widen in high-vol
               "tp_multiplier": 1.2,           # Widen in trending
               "model_weight_overrides": {      # Boost/suppress specific models
                   "MomRegime": 1.3,            # Boost in trending
                   "TechConf": 0.7              # Suppress in choppy
               }
           }
           """
   ```

3. `learning/sl_tp_learner.py` — **THE ADAPTIVE STOP-LOSS/TAKE-PROFIT BRAIN**
   ```python
   class SLTPLearner:
       """
       Learns optimal TP and SL levels from historical trade outcomes.
       This is one of the most important components in the entire system.

       HOW IT LEARNS:

       1. STOP-LOSS OPTIMIZATION
          For every closed trade, we recorded max_adverse_excursion (MAE) —
          the worst price the position hit before resolving.

          The question: "What SL level would have maximized P&L?"
          - Too tight: stops us out of winners that dip temporarily
          - Too loose: lets losers run too far before cutting

          Method:
          a. Group trades by (asset, timeframe, regime)
          b. For each group with 30+ trades:
             - Simulate different SL levels from 0.03 to 0.25 in 0.01 steps
             - For each SL level, replay all trades:
               * If MAE > SL → trade would have been stopped out at that SL → P&L = -(SL × size)
               * If MAE ≤ SL → trade survived → P&L = actual resolution P&L
             - Pick the SL level that maximizes total P&L across the group
          c. Smooth with exponential moving average to avoid overfitting to recent data
          d. Compare new optimal SL vs current SL. If difference > 1 cent → update.

       2. TAKE-PROFIT OPTIMIZATION
          For every closed trade, we recorded max_favorable_excursion (MFE) —
          the best price the position reached.

          The question: "What TP level would have captured the most profit?"
          - Too tight: takes small wins when bigger ones were available
          - Too loose: never triggers, price retraces before TP hits

          Method: Same as SL but optimizing on the profit side using MFE data.

       3. TIME DECAY EXIT OPTIMIZATION
          We also recorded: if we exited early due to time decay, would_have_won_if_held.
          - If > 60% of time-decay exits would have won if held → TIME DECAY IS TOO AGGRESSIVE → relax it
          - If < 30% of time-decay exits would have won → TIME DECAY IS CORRECT → keep or tighten

       4. REGIME-CONDITIONAL LEARNING
          SL and TP are learned separately for each regime.
          Example: In HIGH_VOL regime, optimal SL might be 0.18 (wide)
          while in CHOPPY regime, optimal SL might be 0.07 (tight).

       OUTPUT: A lookup table that the PositionManager queries at trade time:
       {
           ("BTC", "5m", "TRENDING"): {"sl": 0.09, "tp_offset": 0.06, "time_decay_pct": 0.12},
           ("BTC", "5m", "CHOPPY"):   {"sl": 0.06, "tp_offset": 0.04, "time_decay_pct": 0.18},
           ("BTC", "1h", "HIGH_VOL"): {"sl": 0.17, "tp_offset": 0.08, "time_decay_pct": 0.10},
           ...
       }
       """

       def get_levels(self, asset: str, timeframe: str, regime: str) -> TPSLLevels:
           """Returns learned levels if enough data, else defaults."""

       def optimize(self, feedback_records: list[FeedbackRecord]) -> dict:
           """Run full optimization. Called every recalibration cycle."""

       def evaluate_recent_exits(self, recent_trades: list) -> ExitQualityReport:
           """
           For the last N trades that hit TP or SL:
           - What % of SL exits would have won if held? (SL too tight?)
           - What % of TP exits left money on table? (TP too tight?)
           - What was avg P&L of TP exits vs hold-to-resolution? (Is TP adding value?)
           - What was avg P&L of SL exits vs hold-to-resolution? (Is SL adding value?)
           """
   ```

4. `learning/model_evolver.py` — **THE ENGINE THAT FIXES BROKEN MODELS**
   ```python
   class ModelEvolver:
       """
       Detects when a quant model is underperforming and takes action:
       1. Diagnose the problem
       2. Try to fix it by mutating parameters
       3. If mutation doesn't help, demote or retire the model
       4. Optionally spawn new strategy variants

       DETECTION (runs every recalibration cycle, ~50 trades or weekly):

       Tier 1 — WARNING (model is struggling):
         - Model's 30-day Brier score > 0.28 (poor accuracy)
         - Model's signal has been on the wrong side > 55% of the time in last 30 trades
         - Model's contribution to winning trades < 10% (it's dead weight)
         → ACTION: Log warning. Reduce ensemble weight by 30%. Flag for parameter mutation.

       Tier 2 — CRITICAL (model is actively hurting):
         - Model's 30-day Brier score > 0.35 (worse than random)
         - Model has been wrong > 65% of the time in last 50 trades
         - Trades where this model was the strongest signal have negative P&L
         → ACTION: Reduce ensemble weight to near-zero (0.02). Trigger immediate param optimization.
                   If optimization doesn't improve Brier below 0.28 in next 50 trades → RETIRE.

       Tier 3 — RETIREMENT (model is broken):
         - Model has been in CRITICAL state for 2+ consecutive recalibration cycles
         - Parameter optimization was attempted but Brier stayed > 0.30
         → ACTION: Move model to strategy_graveyard with full death report.
                   Set ensemble weight to 0. Log everything.
                   The ensemble now runs with N-1 models until a replacement is ready.

       PARAMETER MUTATION (how we try to fix a struggling model):

       When a model enters WARNING or CRITICAL state:
       1. Pull its current parameter set from ParamRegistry
       2. Identify which parameters might be causing the issue:
          - If model is wrong in trending markets → ADX threshold might be wrong
          - If model is wrong on short timeframes → lookback periods might be too long
          - If model flips direction too slowly → EMAs might be too slow
       3. Use Optuna to search the parameter space:
          - Objective: minimize Brier score on last 100 trade feedback records
          - Search space: each learnable parameter within its defined range
          - Trials: 50 (quick search) or 200 (deep search if Tier 2)
       4. Best params go into ParamRegistry with status=PROBATION
       5. PROBATION params run in SHADOW MODE:
          - They generate signals alongside the active params
          - Signals are logged but NOT used for trading
          - After 30 shadow trades, compare PROBATION Brier vs ACTIVE Brier
          - If PROBATION is better by > 0.03 → PROMOTE (swap to active)
          - If PROBATION is worse or insignificantly better → DISCARD

       STRATEGY NURSERY (experimental variants):

       Every 200 trades, the evolver can spawn ONE new model variant:
       - Take the best-performing model's parameters
       - Apply a "creative mutation": change 2-3 parameters by ±20-40% from current values
       - Run in PROBATION shadow mode
       - If it shows promise (Brier < 0.25 over 30 trades) → consider adding as Model 7
       - System can support up to 8 models in the ensemble (6 original + 2 nursery graduates)

       IMPORTANT SAFETY RAILS:
       - Never mutate more than 1 model at a time (avoid changing everything at once)
       - Never retire more than 1 model per recalibration cycle
       - Always keep at least 4 models active in the ensemble
       - All changes are logged with full reasoning to learning_log
       - Human can override any evolution decision via config flag
       """

       async def evaluate_models(self, feedback_records: list) -> list[EvolutionAction]:
           """Run full evaluation. Returns list of actions to take."""

       async def mutate_params(self, model_name: str, timeframe: str, feedback: list) -> ModelParams:
           """Use Optuna to find better params. Returns new ModelParams in PROBATION."""

       async def evaluate_probation(self, model_name: str, timeframe: str) -> PromotionDecision:
           """Compare PROBATION vs ACTIVE performance. Return PROMOTE, DISCARD, or CONTINUE."""

       def retire_model(self, model_name: str, timeframe: str, reason: str):
           """Move to graveyard. Log death report."""
   ```

5. `learning/param_optimizer.py`
   ```python
   class ParamOptimizer:
       """
       Optuna-based hyperparameter optimizer.
       Given a model, a parameter search space, and historical feedback data,
       finds the parameter set that would have produced the best signals.

       OBJECTIVE FUNCTION:
       For a given param set:
       1. Replay all recent feedback records
       2. For each record, re-compute what the model WOULD have predicted with these params
       3. Compare predictions to actual outcomes
       4. Score = Brier score (lower = better)

       ANTI-OVERFITTING:
       - Use walk-forward validation: optimize on trades 1-70, validate on trades 71-100
       - If validation Brier is > 0.05 worse than training Brier → overfitting → reject
       - Add regularization: penalize params that are far from defaults (prefer small changes)
       - Minimum 50 trades in dataset before optimization is allowed
       """

       def optimize(self, model_class, param_space: dict, feedback: list, n_trials: int) -> ModelParams:
           """Returns optimized ModelParams with validation score."""
   ```

6. `learning/strategy_graveyard.py`
   ```python
   class StrategyGraveyard:
       """
       Where retired strategies go. NOT deleted — stored with full death reports
       so we can learn from failures and potentially resurrect strategies if market conditions change.

       DEATH REPORT includes:
       - model_name, timeframe, param_version
       - date_retired, active_duration_days
       - reason: "Brier > 0.35 for 2 cycles", "wrong > 65% over 50 trades", etc.
       - regime_at_death: what was the market regime when this model failed?
       - final_brier, final_win_rate, total_trades
       - param_history: full lineage of parameter evolution attempts

       RESURRECTION CHECK (runs monthly):
       - If the regime that killed a strategy is no longer active
       - AND the strategy's original logic might work in the new regime
       - → Move to nursery for probation testing
       - Example: MomentumRegime was retired during CHOPPY market. Now market is TRENDING.
         Resurrect MomentumRegime with its best historical params from TRENDING periods.
       """
   ```

7. `learning/strategy_nursery.py`
   ```python
   class StrategyNursery:
       """
       Incubator for experimental model variants.
       These run in shadow mode (signals generated but not traded) until proven.

       LIFECYCLE:
       BORN → SHADOW (30 trades) → EVALUATE → PROMOTE or DISCARD

       SHADOW MODE:
       - Model receives same inputs as production models
       - Generates ModelOutput like any other model
       - Output is stored in feedback_db with flag "shadow=True"
       - Not included in ensemble for actual trades

       EVALUATION AFTER 30 SHADOW TRADES:
       - Brier < 0.25 → PROMOTE (add to ensemble with initial weight 0.10)
       - Brier 0.25-0.30 → EXTEND shadow for 20 more trades
       - Brier > 0.30 → DISCARD
       """
   ```

8. `learning/evolution_report.py`
   ```python
   class EvolutionReport:
       """
       Human-readable report generated every recalibration cycle.
       Sent via Telegram/Discord alert and displayed in dashboard.

       REPORT INCLUDES:
       - Overall system health score (0-100)
       - Model rankings by current Brier score
       - Parameter changes made this cycle (with before/after values and reasoning)
       - TP/SL adjustments made (with before/after and supporting data)
       - Models in WARNING or CRITICAL state
       - Probation model performance
       - Graveyard activity (retirements, resurrection candidates)
       - Regime transitions detected
       - Recommendation: "System is healthy, no intervention needed" or
         "MomentumRegime is struggling on 5m BTC — Optuna mutation in progress"
       """
   ```

**Test (Gate 5):**
```
tests/unit/test_learning/test_feedback_db.py        — Store and query feedback records
tests/unit/test_learning/test_regime_detector.py    — Feed known conditions, verify regime classification
tests/unit/test_learning/test_sl_tp_learner.py      — Feed 100 mock trades with known MAE/MFE
                                                     — Verify optimal SL is found correctly
                                                     — Verify regime-conditional SL differs by regime
                                                     — Verify fallback to defaults when < 30 trades
tests/unit/test_learning/test_model_evolver.py      — Feed model with Brier=0.32 → verify WARNING triggered
                                                     — Feed model with Brier=0.38 → verify CRITICAL triggered
                                                     — Feed 2 cycles of CRITICAL → verify RETIREMENT triggered
                                                     — Verify only 1 model mutated at a time (safety rail)
tests/unit/test_learning/test_param_optimizer.py    — Run Optuna on mock data, verify output is valid ModelParams
                                                     — Verify walk-forward validation catches overfitting
tests/unit/test_learning/test_strategy_graveyard.py — Retire model, verify death report stored
                                                     — Change regime, verify resurrection candidate detected
tests/unit/test_learning/test_strategy_nursery.py   — Create shadow model, verify signals generated but not traded
                                                     — Feed Brier < 0.25 → verify PROMOTE recommendation
                                                     — Feed Brier > 0.30 → verify DISCARD recommendation
tests/integration/test_learning_cycle.py            — Full cycle: 100 mock trades → recalibration
                                                     → model evaluation → param mutation → shadow testing
                                                     → verify entire pipeline produces valid evolution actions
```
**Gate 5 rule:** ALL 8 test files pass. The learning engine correctly identifies underperformers, proposes fixes, and respects all safety rails.

---

### Phase 6: Orchestrator (ties everything together)

**Build:**

1. `orchestrator/pipeline.py`
   ```python
   class TradingPipeline:
       async def run_cycle(self) -> CycleResult:
           """
           ONE COMPLETE CYCLE:

           Step 1 — REGIME: Run regime_detector to classify current market state
           Step 2 — DATA: Fetch latest OHLCV, funding, chain flow, sentiment
           Step 3 — SIGNALS: Run all ACTIVE models (skip retired/probation) → ensemble aggregation
                    Apply regime-based weight adjustments to ensemble
           Step 4 — SHADOW: Run PROBATION models in shadow mode → log signals but don't trade
           Step 5 — MARKETS: Discover active Polymarket crypto markets, classify by timeframe
           Step 6 — BOOKS: For each qualifying market, pull order book + compute effective implied prob
           Step 7 — EDGE: Compare ensemble prob vs effective implied → compute edge
                    Apply regime-based edge threshold (higher in choppy)
           Step 8 — SIZE: RiskManager for Kelly sizing + limit checks
                    Apply regime-based Kelly multiplier (lower in risk-off)
           Step 9 — POSITIONS: Check active positions for adaptive TP/SL/time_decay/edge_evap exits
           Step 10 — EXECUTE: Submit new trades + exit orders via paper or live engine
           Step 11 — FEEDBACK: Log all outcomes to feedback_db
           Step 12 — LEARN: If recalibration is due (50 trades or weekly), trigger learning cycle
           Step 13 — DASHBOARD: Push updated state

           Return CycleResult with summary
           """
   ```

2. `orchestrator/main_loop.py`
   ```python
   class MainLoop:
       """
       Scheduling:
       - Fastest cycle (30s) runs everything, but each market type only
         re-evaluates when its interval has elapsed.
       - Learning cycle runs when triggered (every 50 trades or weekly)
       - Regime detection runs every 5 minutes
       - Dashboard refresh every 10 seconds

       LEARNING CYCLE (triggered by trade count or time):
       1. Pull all feedback records since last recalibration
       2. Run model_evolver.evaluate_models() → get list of evolution actions
       3. Execute actions: mutate params, start shadow tests, retire models
       4. Run sl_tp_learner.optimize() → update TP/SL lookup table
       5. Run param_optimizer if any model is in WARNING/CRITICAL
       6. Update ensemble weights based on fresh Brier scores
       7. Check nursery: any probation models ready to promote/discard?
       8. Check graveyard: any resurrection candidates given current regime?
       9. Generate evolution_report and send alert
       10. Log everything to learning_log
       """
   ```

3. `orchestrator/graduation.py`
   ```python
   class GraduationManager:
       """
       GRADUATION CRITERIA (ALL must be met):
       1. ≥ 100 paper trades completed
       2. Win rate > 54%
       3. Total paper P&L > 0
       4. Sharpe ratio > 0.8
       5. Calibration error < 0.15
       6. No single day drawdown > 6% in last 30 days
       7. At least 14 calendar days of paper trading
       8. *** NEW: Learning engine has run at least 2 recalibration cycles ***
       9. *** NEW: No model currently in CRITICAL state ***

       GRADUATION PROCESS:
       1. All criteria met → log "GRADUATION_READY"
       2. Send alert for human confirmation
       3. Human confirms → switch PaperEngine to LiveEngine
       4. First 48 hours: reduce all sizes by 50%
       5. After 48 hours with no issues: full sizing

       DE-GRADUATION:
       - Live daily drawdown hits 5% → auto-pause, alert human
       - Live win rate < 48% over 50+ trades → auto-pause
       - 2+ models enter CRITICAL state simultaneously → auto-pause
       - Human can always force paper mode
       """
   ```

**Test (Gate 6):**
```
tests/integration/test_pipeline.py          — Full cycle with mocked data, verify all 13 steps execute
tests/integration/test_learning_cycle.py    — Trigger learning mid-run, verify params update, SL adjusts
tests/integration/test_graduation.py        — Simulate 100 good trades → verify graduation triggers
                                             — Simulate model in CRITICAL → verify graduation blocked
tests/integration/test_regime_switch.py     — Switch regime mid-run → verify weights/thresholds adjust
```
**Gate 6 rule:** Full pipeline runs end-to-end. Learning cycle integrates cleanly. Graduation respects new criteria.

---

### Phase 7: Streamlit Dashboard

**Build:** `dashboard/app.py` and all page modules

The dashboard has **7 tabs** (6 from v2 + new Learning Lab). Auto-refreshes every 10 seconds.

**Tab 1 — Portfolio Overview** (`pages/overview.py`)
- Big numbers: Current Bankroll | Today P&L | All-Time P&L | Win Rate
- Equity curve (cumulative P&L over time)
- P&L by asset (bar chart), by timeframe, by action (YES vs NO)
- Current mode: 🟡 PAPER or 🟢 LIVE (with graduation progress bar)
- Current regime badge: 🟢 RISK-ON | 🔴 RISK-OFF | 🟠 HIGH-VOL | 🔵 TRENDING | ⚪ CHOPPY

**Tab 2 — Active Positions** (`pages/active_positions.py`)
- Table: trade_id, asset, market, action, entry_price, current_price, unrealized_P&L, TP level (show if learned), SL level (show if learned), time remaining
- Color coding: green (profit), red (loss), yellow (near entry)
- TP/SL level badges: 🧠 = learned, 📏 = default
- Time-to-resolution countdown

**Tab 3 — Trade History** (`pages/trade_history.py`)
- Full scrollable ledger of all closed trades
- Columns: trade_id, asset, market, action, entry, exit, P&L ($), P&L (%), result, exit_reason, edge_at_entry, was_sl_learned, would_have_won_if_held
- Filters: asset, result, date range, exit_reason, timeframe, regime
- Summary stats at top
- NEW: "Exit Quality" column:
  - ✅ GOOD EXIT: SL triggered and would have lost if held, or TP triggered and price retraced after
  - ❌ BAD EXIT: SL triggered but would have won if held (premature stop)
  - ➖ NEUTRAL: Resolution exit (held to end)

**Tab 4 — Analytics** (`pages/analytics.py`)
- Calibration chart (predicted prob vs actual win rate)
- Model attribution (which models drive wins vs losses)
- Edge vs outcome by bucket
- Win rate by confidence bucket
- Best/worst timeframe
- Brier scores per model (line chart over time)
- NEW: P&L improvement over time (are learned TP/SL producing better exits than defaults did?)

**Tab 5 — Risk Monitor** (`pages/risk_monitor.py`)
- Exposure by asset (with limits), total exposure, daily drawdown gauge
- Position concentration, correlation matrix
- Alerts log
- NEW: Regime-adjusted limit display (show current effective limits based on regime)

**Tab 6 — Signal Health** (`pages/signal_health.py`)
- Signal heatmap: 4 assets × 5 timeframes
- Confidence overlay, freshness indicators
- Model agreement panel
- Ensemble weight table (now showing both DEFAULT and CURRENT learned weights)
- NEW: Model status badges: 🟢 ACTIVE | 🟡 WARNING | 🔴 CRITICAL | ⚫ RETIRED | 🔵 PROBATION

**Tab 7 — Learning Lab** (`pages/learning_lab.py`) *** NEW ***
- **Evolution Timeline:** Visual timeline of all learning events (param changes, retirements, promotions) with dates and reasons
- **Model Health Dashboard:**
  - Each model as a card showing: current Brier, trend (improving/declining), param version, last mutation date
  - Status badge (ACTIVE/WARNING/CRITICAL/RETIRED)
  - "Generations survived" count
- **TP/SL Optimization View:**
  - Table showing current learned TP/SL per (asset, timeframe, regime) bucket
  - Comparison: "Default SL" vs "Learned SL" vs "Optimal SL (backtest)"
  - Exit quality stats: "SL saved us from X losses but also stopped out Y winners"
  - Chart: Rolling average of "would have won if held" rate for SL exits (should decrease as SL learns)
- **Parameter Evolution Chart:** For any selected model, show how each parameter has changed over time (version history)
- **Strategy Graveyard:** Table of retired strategies with death cause, date, and resurrection eligibility
- **Strategy Nursery:** Active probation models with shadow performance so far
- **Regime History:** Timeline of regime transitions with overlay of P&L (did we adapt well to regime changes?)
- **Latest Evolution Report:** Full text of the most recent recalibration report
- **Manual Override Controls:**
  - Button: "Force recalibration now"
  - Button: "Reset model to default params"
  - Button: "Pause learning for model X"
  - Button: "Resurrect strategy Y from graveyard"
  - Toggle: "Learning engine ON/OFF" (emergency kill switch)

**Test (Gate 7):**
```
tests/integration/test_dashboard.py — Seed DB with mock data including learning events
                                    — Verify all 7 tabs render without errors
                                    — Verify Learning Lab shows evolution timeline, TP/SL comparison, model cards
                                    — Verify Exit Quality column populates correctly
```
**Gate 7 rule:** All 7 dashboard tabs render with test data. Learning Lab displays evolution data accurately.

---

### Phase 8: Paper Trading Validation

**This is running the actual bot with real market data in paper mode.**

```python
# scripts/run_paper_validation.py
"""
1. Start bot in PAPER mode
2. Let it run for minimum 14 days
3. It discovers real Polymarket markets, generates real signals, simulates real trades
4. Every trade logged to database
5. Learning engine runs on real data after every 50 trades

VALIDATION CRITERIA (ALL must pass):
- [ ] ≥ 100 trades executed
- [ ] Win rate > 54%
- [ ] Cumulative P&L > 0
- [ ] Sharpe > 0.8
- [ ] Calibration error < 0.15
- [ ] No single day drawdown > 6%
- [ ] TP/SL exits are triggering correctly (verify 10+ exits manually)
- [ ] Time decay exits are working
- [ ] Signal refresh is working (no stale signals)
- [ ] Dashboard is displaying accurate data
- [ ] *** Learning engine has run at least 2 recalibration cycles ***
- [ ] *** At least 1 parameter mutation has been tested in shadow mode ***
- [ ] *** SL/TP learner has produced non-default levels for at least 2 asset/timeframe combos ***
- [ ] *** No model currently in CRITICAL state ***
- [ ] *** Exit quality report shows learned exits are at least as good as default exits ***

POST-VALIDATION ANALYSIS:
1. Which models are carrying the ensemble? Any dead weight?
2. Have learned TP/SL levels improved P&L vs default levels? By how much?
3. What regime has the bot operated in? Is there regime diversity in the test period?
4. Are parameter mutations improving model accuracy?
5. Is slippage estimation accurate?
6. Should any thresholds be adjusted before going live?
"""
```

**Gate 8 rule:** All validation criteria pass including learning-specific criteria. Human has reviewed and approved.

---

### Phase 9: Live Deployment (VPS)

```yaml
# docker-compose.yml
services:
  bot:
    build: .
    env_file: .env
    environment:
      - MODE=live
      - DB_URL=postgresql://polyquant:pass@db:5432/polyquant
    restart: unless-stopped
    depends_on:
      - db

  dashboard:
    build: .
    command: streamlit run dashboard/app.py --server.port 8501 --server.address 0.0.0.0
    env_file: .env
    ports:
      - "8501:8501"
    depends_on:
      - db

  db:
    image: postgres:16-alpine
    environment:
      - POSTGRES_DB=polyquant
      - POSTGRES_USER=polyquant
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

```bash
# scripts/deploy.sh
#!/bin/bash
set -e
echo "=== PolyQuant v3 Deployment ==="
echo "Running tests..."
pytest tests/ -v --tb=short || { echo "TESTS FAILED"; exit 1; }
echo "Building..."
docker-compose build
echo "Migrating..."
docker-compose run --rm bot python -m database.migrations
echo "Starting..."
docker-compose up -d
sleep 10
curl -f http://localhost:8501/_stcore/health || { echo "Dashboard unhealthy"; exit 1; }
echo "=== Live at http://your-vps-ip:8501 ==="
```

---

## SECTION 2 — THE LEARNING LIFECYCLE (SUMMARY)

Here is the complete feedback loop in one view:

```
TRADE EXECUTED
    │
    ▼
OUTCOME RECORDED (feedback_db)
    │ Records: signals, params, regime, MAE, MFE, result, exit reason,
    │ would_have_won_if_held
    │
    ▼
EVERY 50 TRADES OR WEEKLY → RECALIBRATION CYCLE
    │
    ├──▶ MODEL EVALUATION (model_evolver.py)
    │       │
    │       ├── Brier score per model → update ensemble weights
    │       ├── WARNING models → reduce weight 30%, flag for mutation
    │       ├── CRITICAL models → weight near-zero, trigger Optuna optimization
    │       ├── RETIRED models → move to graveyard, log death report
    │       └── Probation check → promote, extend, or discard shadow models
    │
    ├──▶ PARAMETER OPTIMIZATION (param_optimizer.py)
    │       │
    │       ├── Optuna search on struggling model's param space
    │       ├── Walk-forward validation to prevent overfitting
    │       ├── New params → PROBATION in shadow mode
    │       └── After 30 shadow trades → promote or discard
    │
    ├──▶ TP/SL LEARNING (sl_tp_learner.py)
    │       │
    │       ├── Analyze MAE distribution → optimize SL per (asset, timeframe, regime)
    │       ├── Analyze MFE distribution → optimize TP per (asset, timeframe, regime)
    │       ├── Evaluate time-decay exits → adjust timing threshold
    │       └── Exit quality report: are learned exits better than defaults?
    │
    ├──▶ REGIME UPDATE (regime_detector.py)
    │       │
    │       ├── Classify current regime
    │       ├── Apply regime adjustments to weights, thresholds, sizing
    │       └── Check graveyard for resurrection candidates in new regime
    │
    ├──▶ CALIBRATION CHECK
    │       │
    │       ├── Predicted probs vs actual outcomes by bucket
    │       ├── If overconfident → raise edge threshold
    │       └── If underconfident → can be more aggressive
    │
    └──▶ EVOLUTION REPORT
            │
            ├── Generate human-readable summary of all changes
            ├── Display in dashboard Learning Lab tab
            └── Send via Telegram/Discord alert

NEXT TRADE USES UPDATED:
    - Model parameters (mutated or promoted)
    - Ensemble weights (Brier-adjusted)
    - TP/SL levels (learned from MAE/MFE)
    - Regime adjustments (weights, thresholds, sizing)
    - Edge thresholds (calibration-adjusted)
```

---

## SECTION 3 — SAFETY RAILS FOR LEARNING

The learning engine is powerful but can be dangerous if unconstrained. These rails are non-negotiable:

```python
LEARNING_SAFETY_RAILS = {
    # Never change too much at once
    "max_models_mutated_per_cycle": 1,
    "max_models_retired_per_cycle": 1,
    "min_active_models": 4,               # Always keep at least 4 running

    # Never trust small samples
    "min_trades_for_sl_optimization": 30,  # Per (asset, timeframe, regime) bucket
    "min_trades_for_param_mutation": 50,   # Before Optuna can run
    "min_shadow_trades_for_promotion": 30, # Before a probation model can be promoted

    # Never stray too far from proven defaults
    "max_param_change_pct": 0.50,          # No parameter can change more than 50% from default in one mutation
    "max_sl_change_per_cycle": 0.03,       # SL can't move more than 3 cents per cycle
    "max_tp_change_per_cycle": 0.03,       # TP can't move more than 3 cents per cycle
    "max_weight_change_per_cycle": 0.15,   # Ensemble weight can't change by more than 15% per cycle

    # Overfitting protection
    "optuna_walk_forward_split": 0.30,     # 30% of data held out for validation
    "optuna_overfit_threshold": 0.05,      # If validation Brier > train Brier + 0.05, reject

    # Emergency kill switches
    "learning_enabled": True,              # Global on/off
    "per_model_learning_enabled": {        # Per-model on/off
        "MomRegime": True, "FundBasis": True, "ChainFlow": True,
        "VolSurface": True, "SentComp": True, "TechConf": True
    },
    "auto_pause_on_live_drawdown_pct": 0.05,  # Pause learning if live drawdown > 5%
}
```

---

## SECTION 4 — ALERTS & NOTIFICATIONS

```python
class AlertManager:
    """
    Levels: INFO, WARNING, CRITICAL, LEARNING

    AUTO-ALERTS:
    - INFO: Trade placed, trade closed (with P&L), daily summary
    - WARNING: Approaching drawdown limit (>5%), signal staleness, high slippage
    - CRITICAL: Drawdown halt triggered, de-graduation, API errors
    - LEARNING: Model entered WARNING/CRITICAL state, parameter mutation started,
                model promoted/retired, TP/SL levels updated, recalibration complete
    """
```

---

## SECTION 5 — CONFIGURATION (.env)

```bash
# .env.example

# Mode
MODE=paper  # paper or live

# Polymarket
POLY_PRIVATE_KEY=
POLY_CHAIN_ID=137

# Data Sources
BINANCE_API_KEY=
BINANCE_API_SECRET=
CRYPTOQUANT_API_KEY=
DERIBIT_CLIENT_ID=
DERIBIT_CLIENT_SECRET=

# Risk Parameters
BANKROLL_USDC=10000
MAX_SINGLE_POSITION_PCT=0.12
MAX_PER_ASSET_PCT=0.25
MAX_TOTAL_EXPOSURE_PCT=0.60
DAILY_DRAWDOWN_HALT_PCT=0.08
MIN_EDGE_THRESHOLD=0.08
MIN_CONFIDENCE=55
KELLY_FRACTION_DEFAULT=0.25

# TP/SL Defaults (overridden by learned values once enough data)
TP_OFFSET_DEFAULT=0.05
SL_5M_DEFAULT=0.08
SL_15M_DEFAULT=0.10
SL_1H_DEFAULT=0.12
SL_4H_DEFAULT=0.15
TIME_DECAY_EXIT_PCT=0.15
TIME_DECAY_FORCE_EXIT_PCT=0.05

# Learning Engine
LEARNING_ENABLED=true
RECALIBRATION_TRADE_INTERVAL=50
RECALIBRATION_TIME_INTERVAL_HOURS=168  # Weekly
MIN_TRADES_FOR_SL_OPTIMIZATION=30
MIN_TRADES_FOR_PARAM_MUTATION=50
MIN_SHADOW_TRADES=30
MAX_PARAM_CHANGE_PCT=0.50
OPTUNA_QUICK_TRIALS=50
OPTUNA_DEEP_TRIALS=200
BRIER_WARNING_THRESHOLD=0.28
BRIER_CRITICAL_THRESHOLD=0.35
MAX_ENSEMBLE_MODELS=8

# Database
DB_URL=sqlite:///polyquant.db
# DB_URL=postgresql://polyquant:pass@db:5432/polyquant

# Alerts
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
DISCORD_WEBHOOK_URL=

# Dashboard
STREAMLIT_PORT=8501
DASHBOARD_REFRESH_SECONDS=10

# Graduation
MIN_PAPER_TRADES=100
MIN_PAPER_WIN_RATE=0.54
MIN_PAPER_SHARPE=0.8
MAX_CALIBRATION_ERROR=0.15
MIN_PAPER_DAYS=14
MIN_RECALIBRATION_CYCLES=2
```

---

## SECTION 6 — TESTING PHILOSOPHY

### Rules

1. **No mocking the math.** Test arithmetic with hand-calculated expected values.
2. **Mock all external APIs.** Use pytest fixtures with saved JSON responses.
3. **Test the learning engine aggressively.** It can break the system if buggy.
4. **Edge cases:** empty order book, stale data, zero liquidity, all models disagreeing, bankroll = $0, learning engine tries to retire all models, Optuna finds params identical to current.
5. **Every bug in paper trading gets a regression test.** Fix forward.
6. **Test the unhappy path.** API timeout → graceful fallback. Bad data → skip with warning.

### Test Commands

```bash
pytest tests/ -v                              # All tests
pytest tests/unit/ -v                         # Unit only (fast)
pytest tests/unit/test_learning/ -v           # Learning engine only
pytest tests/integration/ -v                  # Integration (needs DB)
pytest tests/ --cov=polyquant --cov-report=html  # Coverage report
```

---

## FINAL CHECKLIST BEFORE GOING LIVE

```
[ ] All 8 gate phases passed (unit + integration tests green)
[ ] Paper traded for ≥ 14 days
[ ] ≥ 100 paper trades completed
[ ] Paper win rate > 54%
[ ] Paper P&L is positive
[ ] Paper Sharpe > 0.8
[ ] Calibration error < 0.15
[ ] No single day drawdown > 6%
[ ] TP/SL exits verified (10+ manual spot checks)
[ ] Adaptive TP/SL is producing non-default levels for at least 2 buckets
[ ] Learning engine ran ≥ 2 recalibration cycles
[ ] At least 1 parameter mutation tested in shadow mode
[ ] No model currently in CRITICAL state
[ ] Exit quality report shows learned exits ≥ default exits
[ ] Streamlit dashboard accurate (cross-check 5 trades)
[ ] VPS deployed and stable 24 hours
[ ] Alerts working (Telegram/Discord)
[ ] Polygon wallet funded with USDC
[ ] Human typed "GRADUATE" to confirm
```

---

*End of PolyQuant v3.0 — Self-Learning Build Specification*
