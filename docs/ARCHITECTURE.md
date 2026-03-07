# PolyQuant Architecture Document

A comprehensive reference for the PolyQuant self-learning crypto trading bot.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [High-Level Architecture](#high-level-architecture)
3. [Module Reference](#module-reference)
   - [config/](#config)
   - [data/](#data)
   - [database/](#database)
   - [models/](#models)
   - [market/](#market)
   - [execution/](#execution)
   - [learning/](#learning)
   - [orchestrator/](#orchestrator)
   - [dashboard/](#dashboard)
4. [Data Flow](#data-flow)
5. [Trading Pipeline (13-Step Cycle)](#trading-pipeline-13-step-cycle)
6. [Quant Models](#quant-models)
7. [Ensemble Aggregation](#ensemble-aggregation)
8. [Risk Management](#risk-management)
9. [TP/SL System](#tpsl-system)
10. [Learning Engine](#learning-engine)
11. [Graduation System](#graduation-system)
12. [External API Integration](#external-api-integration)
13. [Database Schema](#database-schema)
14. [Deployment](#deployment)
15. [Key Design Decisions](#key-design-decisions)

---

## System Overview

PolyQuant is a self-learning Python trading bot that:

1. Runs 7 quant models on BTC, ETH, SOL, and XRP to predict price direction
2. Compares predictions against Polymarket crypto binary market prices
3. Executes YES/NO bets when edge exceeds 8%, with adaptive stop-loss/take-profit
4. Learns from every trade: evolves model parameters, optimizes SL/TP levels, retires broken models
5. Paper trades first, auto-graduates to live when proven profitable
6. Displays everything in a Streamlit dashboard

### Codebase Stats

| Metric              | Value                          |
|---------------------|--------------------------------|
| Source files         | 35+ Python modules             |
| Lines of code       | ~8,500 (excluding tests)       |
| Test count           | 386 passing                    |
| Modules              | 9 packages                     |
| Quant models         | 7 + ensemble aggregator        |
| Dashboard tabs       | 7                              |

### Tech Stack

| Component       | Technology                     | Reason                                           |
|-----------------|--------------------------------|--------------------------------------------------|
| Language        | Python 3.11+                   | Async support, data science ecosystem            |
| TA library      | `ta` (pure Python)             | No C compilation needed, cross-platform           |
| HTTP client     | `httpx` (async)                | Non-blocking concurrent API calls                 |
| Exchange data   | `ccxt` (async)                 | Unified exchange API, Binance/Coinbase             |
| Polymarket SDK  | `py_clob_client`               | Official CLOB reads and order placement            |
| Database        | SQLAlchemy + SQLite WAL (dev)  | WAL mode prevents deadlocks with concurrent access |
| Database (prod) | PostgreSQL                     | Proper concurrent access on VPS                    |
| Config          | Pydantic Settings              | Type-safe, .env file loading                       |
| Logging         | `structlog`                    | JSON structured logging                            |
| Dashboard       | Streamlit                      | Rapid prototyping, real-time refresh               |
| Optimization    | Optuna                         | Hyperparameter search for model evolution          |
| WebSocket       | `websockets`                   | Real-time CLOB book updates                        |
| Testing         | pytest + pytest-asyncio        | Async test support                                 |

---

## High-Level Architecture

```
+------------------------------------------------------------------+
|                        PolyQuant System                           |
+------------------------------------------------------------------+
|                                                                    |
|  +--------------------+    +-------------------+                   |
|  |   External APIs    |    |   Configuration    |                  |
|  |  Binance (ccxt)    |    |  settings.py (.env)|                  |
|  |  Coinbase (ccxt)   |    |  constants.py      |                  |
|  |  Gamma API         |    +-------------------+                   |
|  |  CLOB API          |              |                             |
|  |  Fear & Greed      |              v                             |
|  |  Deribit (opt)     |    +-------------------+                   |
|  |  CryptoQuant (opt) |    |    Data Layer      |                  |
|  +--------+-----------+    |  price_feed.py     |                  |
|           |                |  funding_feed.py   |                  |
|           +--------------->|  sentiment_feed.py |                  |
|                            |  onchain_feed.py   |                  |
|                            |  cache.py (TTL)    |                  |
|                            +--------+-----------+                  |
|                                     |                              |
|                                     v                              |
|  +----------------------------------------------------------+     |
|  |                    Orchestrator                            |     |
|  |  +---------------------------------------------------+   |     |
|  |  |            TradingPipeline (13 steps)               |   |     |
|  |  |                                                     |   |     |
|  |  |  1. RegimeDetector  --> regime classification       |   |     |
|  |  |  2. DataProvider    --> OHLCV for all assets        |   |     |
|  |  |  3. SignalGenerator --> 7 model outputs             |   |     |
|  |  |  4. Shadow signals  --> nursery/probation models    |   |     |
|  |  |  5. Scanner         --> Polymarket market discovery |   |     |
|  |  |  6. OrderBook       --> CLOB depth analysis         |   |     |
|  |  |  7. PricingEngine   --> fee-aware edge calc         |   |     |
|  |  |  8. RiskManager     --> sizing + limit checks       |   |     |
|  |  |  9. PositionManager --> TP/SL monitoring            |   |     |
|  |  |  10. ExecutionEngine--> buy/sell execution          |   |     |
|  |  |  11. FeedbackStore  --> outcome logging             |   |     |
|  |  |  12. LearningEngine --> recalibration               |   |     |
|  |  |  13. Dashboard push --> status update               |   |     |
|  |  +---------------------------------------------------+   |     |
|  |                                                            |     |
|  |  MainLoop: 30s cycle + 2s fast monitor                    |     |
|  |  GraduationManager: Paper --> Live transition             |     |
|  +----------------------------------------------------------+     |
|                      |                    |                         |
|                      v                    v                         |
|  +------------------+--+    +-------------------+                  |
|  |  Execution Layer     |    |   Learning Layer   |                 |
|  |  PaperEngine         |    |   FeedbackStore    |                 |
|  |  LiveEngine          |    |   ModelEvolver     |                 |
|  |  PositionManager     |    |   ParamOptimizer   |                 |
|  |  RiskManager         |    |   SLTPLearner      |                 |
|  +----------+-----------+    |   StrategyNursery  |                 |
|             |                |   StrategyGraveyard|                 |
|             v                +--------+----------+                  |
|  +---------------------+             |                              |
|  |    Database (SQLite) |<------------+                              |
|  |  Trade, Signal,      |                                           |
|  |  LearningEvent       |                                           |
|  +----------+-----------+                                           |
|             |                                                       |
|             v                                                       |
|  +---------------------+                                           |
|  | Streamlit Dashboard  |                                           |
|  | 7 tabs, auto-refresh |                                           |
|  +---------------------+                                           |
+------------------------------------------------------------------+
```

---

## Module Reference

### Project Structure

```
polyquant/
  config/
    __init__.py
    settings.py              # Pydantic settings from .env
    constants.py             # Assets, timeframes, weights, fees, thresholds
  data/
    __init__.py
    price_feed.py            # Async OHLCV via ccxt
    funding_feed.py          # Binance Futures funding rates
    sentiment_feed.py        # Fear & Greed Index
    onchain_feed.py          # Exchange flows (optional)
    cache.py                 # In-memory TTL cache
  database/
    __init__.py
    models.py                # SQLAlchemy ORM + WAL mode setup
    trades.py                # Trade CRUD operations
    signals.py               # Signal storage
    learning_log.py          # Learning event storage
  models/
    __init__.py
    base.py                  # ABC + ModelParams + ModelOutput dataclasses
    momentum_regime.py       # Model 1: ADX + DI trend
    funding_basis.py         # Model 2: Funding rate (contrarian)
    chain_flow.py            # Model 3: Exchange net flows
    vol_surface.py           # Model 4: IV skew / realized vol
    sentiment.py             # Model 5: Fear & Greed
    tech_confluence.py       # Model 6: RSI/MACD/BB/VWAP/Volume
    clob_signal.py           # Model 7: CLOB order book imbalance
    ensemble.py              # Bayesian weighted aggregator
    param_registry.py        # Versioned parameter storage
  market/
    __init__.py
    scanner.py               # Gamma API market discovery
    orderbook.py             # CLOB order book analysis
    pricing.py               # Fee-aware edge calculation
    resolution.py            # Resolution risk scoring
  execution/
    __init__.py
    paper_engine.py          # Simulated execution with real CLOB prices
    live_engine.py           # Real execution via py_clob_client
    position_manager.py      # TP/SL computation + monitoring
    risk_manager.py          # Fixed sizing + hard limits
  learning/
    __init__.py
    feedback_db.py           # Trade outcome records
    regime_detector.py       # Market regime classification
    sl_tp_learner.py         # Adaptive SL/TP optimizer
    model_evolver.py         # WARNING/CRITICAL/RETIRED pipeline
    param_optimizer.py       # Optuna walk-forward search
    strategy_graveyard.py    # Retired models with death reports
    strategy_nursery.py      # Shadow/probation testing
    evolution_report.py      # Human-readable recalibration summaries
  orchestrator/
    __init__.py
    pipeline.py              # 13-step trading cycle
    main_loop.py             # 30s cycle + 2s fast monitor
    graduation.py            # Paper to Live transition
  dashboard/
    __init__.py
    app.py                   # Streamlit main (7 tabs)
    pages/
      __init__.py
      tab_overview.py        # System overview + key metrics
      tab_positions.py       # Active positions
      tab_history.py         # Trade history
      tab_analytics.py       # Performance analytics
      tab_risk.py            # Risk monitor
      tab_signals.py         # Signal explorer
      tab_learning.py        # Learning engine status
  scripts/
    run_bot.py               # Entry point
    seed_mock_data.py        # Generate test data
    validate_paper.py        # Check graduation criteria
    check_trades.py          # Trade inspection utility
    risk_analysis.py         # Risk analysis utility
    check_4h_markets.py      # 4h market inspection
  tests/                     # Unit + integration tests (386 tests)
  requirements.txt
  .env                       # Environment variables (not committed)
```

---

### config/

**`settings.py`** -- Pydantic Settings loaded from `.env`.

| Setting                     | Default     | Description                           |
|-----------------------------|-------------|---------------------------------------|
| `MODE`                      | `"paper"`   | `"paper"` or `"live"`                 |
| `BANKROLL_USDC`             | `10000.0`   | Starting bankroll in USDC             |
| `BINANCE_API_KEY`           | `""`        | Binance API key for OHLCV data        |
| `POLY_PRIVATE_KEY`          | `""`        | Polymarket wallet private key         |
| `POLY_CHAIN_ID`             | `137`       | Polygon chain ID                      |
| `POSITION_SIZE_USD`         | `20.0`      | Fixed position size per trade         |
| `DAILY_LOSS_HALT_USD`       | `100.0`     | Daily loss halt threshold             |
| `MIN_EDGE_THRESHOLD`        | `0.08`      | Minimum edge (8%) to trade            |
| `MIN_CONFIDENCE`            | `55`        | Minimum ensemble confidence           |
| `DB_URL`                    | `sqlite:///polyquant.db` | Database connection string  |
| `LEARNING_ENABLED`          | `True`      | Enable/disable learning engine        |
| `RECALIBRATION_TRADE_INTERVAL` | `50`     | Trades between recalibration cycles   |
| `MIN_TRADES_FOR_SL_OPTIMIZATION` | `30`   | Min trades before SL/TP learning      |
| `MIN_TRADES_FOR_PARAM_MUTATION` | `80`     | Min trades before Optuna runs         |

**`constants.py`** -- Immutable constants.

Key constants:
- `ASSETS`: `["BTC", "ETH", "SOL", "XRP"]`
- `MARKET_TIMEFRAMES`: `["5m", "15m", "1h", "4h", "daily"]`
- `DEFAULT_SL_PCT`: `0.04` (4% flat)
- `DEFAULT_TP_PCT`: `0.07` (7% flat)
- `POSITION_SIZE_USD`: `$20` fixed
- `MAX_HOLD_SECONDS`: `600` (10 minutes)
- Fee curve function: `fee = max_fee * 2 * price * (1 - price)`
- Taker fee maxima: 5m=1.56%, 15m=3.0%, 1h/4h/daily=0%

---

### data/

**`price_feed.py`** -- Async OHLCV data via `ccxt`.

- Primary exchange: Binance (`BTC/USDT`, `ETH/USDT`, `SOL/USDT`, `XRP/USDT`)
- Fallback exchange: Coinbase
- Exponential backoff retries (3 attempts)
- Returns pandas DataFrame with columns: `[open, high, low, close, volume]`

**`funding_feed.py`** -- Binance Futures funding rate.

- Perp funding rate used by `FundingBasisModel`
- Contrarian signal: high positive funding = market overleveraged long

**`sentiment_feed.py`** -- Fear & Greed Index.

- API: `https://api.alternative.me/fng/`
- Updates once per day
- Used by `SentimentModel` (disabled on 5m/15m due to staleness)

**`onchain_feed.py`** -- Exchange net flows (optional).

- CryptoQuant API (requires API key)
- Disabled by default; provides data to `ChainFlowModel`

**`cache.py`** -- In-memory TTL cache.

| Data Type     | TTL      |
|---------------|----------|
| OHLCV 5m      | 30s      |
| OHLCV 15m     | 60s      |
| OHLCV 1h      | 120s     |
| OHLCV 4h      | 300s     |
| Funding       | 60s      |
| On-chain      | 300s     |
| Sentiment     | 300s     |
| Order book    | 10s      |

---

### database/

**`models.py`** -- SQLAlchemy ORM with SQLite WAL mode.

Three tables: `Trade`, `Signal`, `LearningEvent`.

WAL mode is enabled via a `connect` event listener on the SQLAlchemy engine:
```
PRAGMA journal_mode=WAL
```
This prevents "database locked" errors when the bot and Streamlit dashboard access the database concurrently.

**`trades.py`** -- Trade CRUD operations (`create_trade`, `update_trade`, `get_trade`, `get_active_trades`).

**`signals.py`** -- Signal storage for historical model outputs.

**`learning_log.py`** -- Learning event storage (mutations, retirements, SL updates).

---

### models/

All 7 models implement the `BaseModel` abstract class:

```python
class BaseModel(ABC):
    def __init__(self, params: ModelParams): ...

    @abstractmethod
    async def generate_signal(
        self, asset: str, timeframe: str, ohlcv: pd.DataFrame, **kwargs
    ) -> ModelOutput: ...

    def update_params(self, new_params: ModelParams) -> None: ...
```

**`ModelParams`** -- Mutable parameter container:
- `values: dict` -- tunable parameters (e.g., `{"adx_period": 14}`)
- `version: int` -- incremented on mutation
- `parent_version: int` -- tracks lineage
- `performance: dict` -- rolling Brier score, trade count, win rate

**`ModelOutput`** -- Standard output:
- `prob_up: float` -- probability of price going up (0.0 to 1.0)
- `confidence: int` -- model confidence (0 to 100)
- `model_name: str` -- canonical model identifier
- `key_drivers: list[str]` -- human-readable signal drivers
- `raw_indicators: dict` -- raw indicator values for debugging

**`EnsembleOutput`** -- Aggregated output:
- `prob_up`, `confidence` -- combined signal
- `model_outputs` -- list of individual model outputs
- `model_weights_used` -- effective weight per model
- `disagreement_flags` -- models diverging >12% from ensemble

See [Quant Models](#quant-models) for individual model details.

---

### market/

**`scanner.py`** -- Polymarket market discovery via Gamma API.

- Endpoint: `GET https://gamma-api.polymarket.com/events?tag_id=21&active=true&closed=false`
- Classifies market type (UP/DOWN binary vs price target) from question text
- Classifies timeframe from title patterns (time ranges like "12:00AM-12:15AM")
- Filters by:
  - Volume thresholds (per timeframe)
  - Time-to-resolution (`MIN_TTR` and `MAX_TTR` per timeframe)
  - Market age (`MAX_MARKET_AGE` -- don't enter markets too far into their window)
- Parses `outcomePrices` and `clobTokenIds` from Gamma API (both are stringified JSON)

**`orderbook.py`** -- CLOB order book analysis.

- Uses `py_clob_client` for REST reads (wrapped in `asyncio.to_thread()` to avoid blocking)
- Produces `OrderBookSnapshot` with: midpoint, spread, bid/ask imbalance, depth at 1%/2%/5%, walk-the-book fill price, expected slippage
- 5-second cache TTL for book data

**`pricing.py`** -- Fee-aware edge calculation.

- Fee curve: `fee = max_fee_rate * 2 * price * (1 - price)`
- Computes effective implied probability: `yes_price + taker_fee + slippage`
- Edge: `|our_prob - effective_implied| - resolution_penalty`
- Expected value calculation for BUY_YES vs BUY_NO

**`resolution.py`** -- Resolution risk scoring for markets near expiry.

---

### execution/

**`paper_engine.py`** -- Simulated execution.

- Uses real CLOB prices for fill simulation
- Tier-specific fill logic:
  - **15m**: Maker-only entry (GTC limit buy, 0% fee)
  - **1h/4h**: FOK taker entry (0% fee on these timeframes)
- Fill slippage rejection: rejects trades where fill deviates beyond per-timeframe thresholds (5m: 5c, 15m: 3c, 1h/4h: 5c)
- P&L calculation: share-based (`shares = size_usd / cost_per_share`)
- Handles market resolution with retroactive `would_have_won_if_held` tracking

**`live_engine.py`** -- Real execution via `py_clob_client`.

- EIP-712 signed orders on Polygon (chain_id=137)
- Supports signature types: EOA (0), email/Magic (1), browser wallet (2)
- Requires `client.set_api_creds(client.create_or_derive_api_creds())` before trading

**`position_manager.py`** -- TP/SL computation and position monitoring.

- `DefaultSLTPProvider`: Flat 4% SL, 7% TP (no tiering, no regime adjustments on defaults)
- TP/SL math (YES price levels stored in DB):
  - BUY_YES: `tp = entry * (1 + tp_pct)`, `sl = entry * (1 - sl_pct)`
  - BUY_NO: `tp = entry - tp_pct * (1 - entry)`, `sl = entry + sl_pct * (1 - entry)`
- Monitors positions for: take_profit, stop_loss, time_decay triggers
- **Liquidity check before every exit**: if CLOB depth < position size, skip exit and log warning
- Tracks max adverse/favorable excursion (MAE/MFE) per position

**`risk_manager.py`** -- Fixed sizing and hard limits.

| Rule                          | Limit                    |
|-------------------------------|--------------------------|
| Position size                  | $20 fixed per trade      |
| Max open positions             | 3 at once                |
| Max per asset                  | 25% of bankroll          |
| Max total exposure             | 60% of bankroll          |
| Max net directional            | 40% of bankroll          |
| Max same-direction per TF      | 3 positions              |
| Daily loss halt                | $100 USD                 |
| Min position size              | $5                       |

- Correlation detection heuristic: same asset + same TF = 1.0, same asset different TF = 0.7, different assets = 0.3

---

### learning/

**`feedback_db.py`** -- Records trade outcomes with full signal snapshots for learning.

**`regime_detector.py`** -- Classifies market regime using BTC as macro proxy.

Five regimes with TP/SL multipliers:

| Regime    | SL Mult | TP Mult | Description                         |
|-----------|---------|---------|-------------------------------------|
| RISK_ON   | 1.00    | 1.00    | Normal conditions                   |
| RISK_OFF  | 0.80    | 0.90    | Tighten SL 20%, TP 10%             |
| HIGH_VOL  | 1.30    | 1.20    | Widen SL 30%, TP 20%               |
| TRENDING  | 1.00    | 1.25    | Widen TP 25%, normal SL            |
| CHOPPY    | 0.85    | 0.85    | Tighten both 15%                   |

Detection uses: realized volatility (20-period), ADX trend strength, simple returns, drawdown from recent high.

**`sl_tp_learner.py`** -- Learns optimal SL/TP percentages from MAE/MFE data.

- Simulates SL levels 0.02-0.15 against actual MAE data
- Simulates TP levels 0.02-0.40 against actual MFE data
- Per (asset, timeframe, regime) bucket, min 30 trades
- Max SL/TP change: 3 percentage points per cycle
- `LearnedSLTPProvider`: Applies regime multipliers on top of learned levels
- Falls back to `DefaultSLTPProvider` when insufficient data

**`model_evolver.py`** -- Model lifecycle management.

```
ACTIVE  --(Brier > 0.28)-->  WARNING   --(Brier drops)-->  ACTIVE
WARNING --(Brier > 0.35)-->  CRITICAL  --(Brier drops)-->  WARNING
CRITICAL (2 consecutive) -->  RETIRED   --> StrategyGraveyard
```

Safety rails:
- Max 1 model mutated per recalibration cycle
- Max 1 model retired per cycle
- Minimum 4 active models at all times
- Max ensemble weight change: 15% per cycle

**`param_optimizer.py`** -- Optuna walk-forward parameter optimization.

- Walk-forward split: 60% train / 20% validate / 20% holdout
- Min 80 trades before optimization available
- Overfit check: if validate Brier > train Brier + 0.05, reject the result
- All optimized params validated through `param_registry.validate_params()`
- Constraint enforcement: `ema_fast < ema_slow`, all values within defined ranges

**`strategy_graveyard.py`** -- Death reports for retired models (full history, last params, Brier trajectory).

**`strategy_nursery.py`** -- Shadow/probation testing.

- Mutated models run in shadow mode (30 trades) before promotion
- Shadow models generate signals but do not influence trading decisions
- After probation period, promoted if performance improves over parent

**`evolution_report.py`** -- Human-readable recalibration summaries for dashboard and alerts.

---

### orchestrator/

**`pipeline.py`** -- 13-step async trading cycle.

Handles: empty scanner results, low-confidence models, API rate limiting, cycle errors (log and continue, never crash).

Protocol-based dependency injection for all major components (`DataProvider`, `MarketScanner`, `OrderBookAnalyzer`, `SignalGenerator`, `EnsembleAggregatorProtocol`).

Key features:
- `_ensemble_cache`: Stores latest ensemble per (asset, timeframe) for cross-timeframe confirmation
- `_trade_tokens`: Maps trade_id to token_id for fast monitor CLOB price lookups
- `_market_exits` / `_market_entry_count`: Re-entry tracking per market title
- `fast_monitor()`: Called every 2s, fetches fresh CLOB midpoint prices, checks TP/SL

**`main_loop.py`** -- Dual-loop orchestration.

```
MainLoop
  |
  +-- Main cycle (30s interval)
  |     For each timeframe (with cooldown):
  |       pipeline.run_cycle(timeframe)
  |
  +-- Fast monitor (2s interval, concurrent asyncio task)
        pipeline.fast_monitor()
        -> Checks CLOB prices for all active positions
        -> Executes TP/SL exits immediately
```

Per-timeframe cooldowns:

| Timeframe | Cooldown |
|-----------|----------|
| 5m        | 30s      |
| 15m       | 60s      |
| 1h        | 30s      |
| 4h        | 600s     |
| daily     | 1800s    |

Graceful shutdown on SIGINT/SIGTERM. Tracks cycle count, total trades, exits, fast exits, errors.

**`graduation.py`** -- Paper to Live transition. See [Graduation System](#graduation-system).

---

### dashboard/

Streamlit application with 7 tabs. Run with: `streamlit run dashboard/app.py`

| Tab             | Module              | Content                              |
|-----------------|---------------------|--------------------------------------|
| Overview        | `tab_overview.py`   | System status, key metrics, P&L      |
| Active Positions| `tab_positions.py`  | Open trades, current prices, TP/SL   |
| Trade History   | `tab_history.py`    | Closed trades, results, exit reasons |
| Analytics       | `tab_analytics.py`  | Win rate, Sharpe, drawdown charts    |
| Risk Monitor    | `tab_risk.py`       | Exposure, directional balance, limits|
| Signal Explorer | `tab_signals.py`    | Model outputs, ensemble breakdown    |
| Learning Engine | `tab_learning.py`   | Brier scores, mutations, evolution   |

Database access is cached via `@st.cache_resource` to avoid reinitializing on every rerun.

---

## Data Flow

The complete data flow from external APIs to trade execution:

```
  Binance/Coinbase        Gamma API           CLOB API          Fear & Greed
       |                     |                    |                   |
       v                     v                    v                   v
  +---------+        +------------+       +-------------+     +-----------+
  |  OHLCV  |        |  Markets   |       |  Order Book |     | Sentiment |
  | (ccxt)  |        | (tag_id=21)|       | (midpoint,  |     | (daily)   |
  +---------+        +------------+       |  depth,     |     +-----------+
       |                     |            |  imbalance) |           |
       v                     |            +-------------+           |
  +----------+               |                    |                 |
  | TTL Cache|               |                    |                 |
  +----------+               |                    |                 |
       |                     |                    |                 |
       +---------------------+--------------------+-----------------+
                             |
                             v
  +------------------------------------------------------------+
  |                  TradingPipeline                             |
  |                                                              |
  |  Step 1: RegimeDetector (BTC OHLCV --> regime)              |
  |  Step 2: DataProvider (OHLCV for BTC, ETH, SOL, XRP)       |
  |  Step 3: SignalGenerator (7 models --> ModelOutputs)        |
  |     +-- MomRegime:  OHLCV --> ADX/DI --> prob_up            |
  |     +-- FundBasis:  funding rate --> contrarian prob         |
  |     +-- ChainFlow:  exchange flows --> net flow signal      |
  |     +-- VolSurf:    ATR/Deribit IV --> vol signal           |
  |     +-- SentComp:   F&G index --> sentiment signal          |
  |     +-- TechConf:   RSI/MACD/BB/VWAP --> confluence score   |
  |     +-- CLOBSignal: book imbalance --> directional signal   |
  |  Step 4: EnsembleAggregator (weighted combination)          |
  |  Step 5: Scanner (Gamma API --> filtered markets)           |
  |  Step 6: OrderBookAnalyzer (CLOB --> depth/slippage)        |
  |  Step 7: PricingEngine (edge = |prob - effective_implied|)  |
  |  Step 8: RiskManager (sizing + limit checks)                |
  |  Step 9: PositionManager (monitor active positions)         |
  |  Step 10: ExecutionEngine (buy/sell)                        |
  |  Step 11: FeedbackStore (log outcomes)                      |
  |  Step 12: LearningEngine (recalibrate if due)              |
  |  Step 13: Dashboard push                                    |
  +------------------------------------------------------------+
                             |
                             v
                   +-------------------+
                   |   SQLite Database  |
                   |  (WAL mode)        |
                   +-------------------+
                             |
                             v
                   +-------------------+
                   | Streamlit Dashboard|
                   | (7 tabs, refresh)  |
                   +-------------------+
```

---

## Trading Pipeline (13-Step Cycle)

Each cycle runs for a single timeframe. The main loop iterates through configured timeframes with per-timeframe cooldowns.

```
Step  Description                          Key Component
----  -----------                          -------------
 1    Regime detection (BTC proxy)         RegimeDetector
 2    Data fetch (OHLCV for all assets)    DataProvider (ccxt)
 3    Active model signals + ensemble      SignalGenerator + EnsembleAggregator
 4    Shadow/probation model signals       StrategyNursery
 5    Market discovery (Polymarket)        PolymarketScanner (Gamma API)
 6    Order book analysis                  OrderBookAnalyzer (CLOB API)
 7    Edge calculation (fee-aware)         PricingEngine
 8    Position sizing + risk checks        RiskManager
 9    Position monitoring (TP/SL)          PositionManager
10    Execute trades / exits               PaperEngine or LiveEngine
11    Feedback logging                     FeedbackStore
12    Learning cycle (if due)              ModelEvolver + ParamOptimizer + SLTPLearner
13    Dashboard status push                Pipeline status dict
```

### Fast Monitor (2-Second Loop)

Independent from the 30s main cycle, a concurrent asyncio task runs every 2 seconds:

1. Iterates over all active positions
2. Fetches fresh CLOB midpoint price via `py_clob_client` (wrapped in `asyncio.to_thread()`)
3. Checks TP/SL triggers
4. Executes immediate exits if triggered
5. Records exit reason in `_market_exits` for re-entry tracking

This prevents SL gapping on fast-moving binary options. Before fast monitor implementation, 30s monitoring caused SL gapping of 10-30 cents. With 2s monitoring, gapping reduced to 0.1-4 cents.

---

## Quant Models

### Model Weight Matrix

Weights determine each model's influence in the ensemble, varying by timeframe:

```
                     5m     15m     1h     4h    Rationale
                   -----  -----  -----  -----   ---------
MomRegime          0.20   0.20   0.18   0.16    Fast-reacting at all TFs
FundBasis          0.05   0.10   0.18   0.22    Slow data, more relevant long TF
ChainFlow          0.00   0.00   0.12   0.18    Updates every 10+ min
VolSurf            0.05   0.08   0.14   0.15    Options data is slow-updating
SentComp           0.00   0.00   0.08   0.13    F&G updates ONCE per day
TechConf           0.35   0.32   0.20   0.16    Most useful on short TFs
CLOBSignal         0.35   0.30   0.10   0.00    CLOB book = noise on 4h
                   ----   ----   ----   ----
Total              1.00   1.00   1.00   1.00
```

Models with confidence=0 automatically receive zero effective weight in the ensemble.

### Individual Model Details

**1. MomentumRegimeModel** (`momentum_regime.py`)
- Indicators: ADX (trend strength), +DI/-DI (directional index)
- Classification: trending bullish, trending bearish, ranging
- Best on: all timeframes (fast-reacting)

**2. FundingBasisModel** (`funding_basis.py`)
- Data: Binance Futures perpetual funding rate
- Logic: contrarian -- high positive funding signals overleveraged longs
- Best on: 1h/4h (funding updates every 8h)

**3. ChainFlowModel** (`chain_flow.py`)
- Data: Exchange net flows (CryptoQuant, optional)
- Logic: large exchange inflows = selling pressure, outflows = accumulation
- Weight=0 on 5m/15m (data updates every 10+ minutes)
- Returns confidence=0 when no CryptoQuant data available

**4. VolSurfaceModel** (`vol_surface.py`)
- Data: Realized vol from ATR, Deribit IV (optional)
- Logic: IV skew / vol compression signals directional moves
- Returns neutral (prob=0.50, confidence=20) when no Deribit data

**5. SentimentModel** (`sentiment.py`)
- Data: Fear & Greed Index (updates once per day)
- Logic: extreme fear = contrarian bullish, extreme greed = contrarian bearish
- Weight=0 on 5m/15m (stale data at short timeframes)

**6. TechConfluenceModel** (`tech_confluence.py`)
- Indicators: RSI, MACD, Bollinger Bands, VWAP, Volume
- Logic: confluence scoring -- counts how many indicators align
- Highest weight on 5m (0.35) -- primary technical signal for short TFs
- Uses `ta` library (pure Python, not `ta-lib`)

**7. CLOBSignalModel** (`clob_signal.py`)
- Data: Polymarket CLOB order book (passed via `book_data` kwarg)
- Signals:
  - Bid/ask size imbalance > threshold (default 1.3) = bullish boost
  - Bid/ask size imbalance < 1/threshold = bearish boost
  - Large recent trades (>$500 in 2 min) = follow direction
- Weight=0 on 4h (too noisy on long horizons)
- Returns confidence=0 for noise timeframes (`4h`, `24h`)

---

## Ensemble Aggregation

The `EnsembleAggregator` combines all model signals using a three-factor weighting system:

```
effective_weight = default_weight * brier_weight * (confidence / 70)
```

Where:
- `default_weight`: Timeframe-specific weight from `DEFAULT_MODEL_WEIGHTS`
- `brier_weight`: Accuracy multiplier from Brier score evaluation (default 1.0 during cold start)
- `confidence / 70`: Confidence scalar (models returning confidence=0 get zero weight)

### Ensemble Probability

```
ensemble_prob = sum(prob_up_i * weight_i) / sum(weight_i)
```

### Ensemble Confidence

```
base_confidence = weighted_average(model_confidences)
agreement_penalty = min(inter_model_variance * 400, 30)  # capped at 30 points
ensemble_confidence = base_confidence - agreement_penalty
```

### Disagreement Detection

Any model diverging >12% from the ensemble probability triggers a disagreement flag. Disagreement flags are logged and stored with the ensemble output.

### Cold Start Behavior (First 50 Trades)

- Use DEFAULT model weights only (no Brier adjustment)
- Use DEFAULT TP/SL levels (flat 4% / 7%)
- Learning engine dormant
- After trade 50: first recalibration cycle
- After trade 80: Optuna parameter optimization becomes available

---

## Risk Management

### Position Sizing

Fixed $20 per trade. No Kelly sizing is used in the current implementation.

### Hard Limits

```
check_limits() validation order:

1. Daily loss halt           $100 total daily realized loss --> HALT all trading
2. Max open positions        3 concurrent positions max
3. Single position limit     12% of bankroll ($1,200)
4. Per-asset exposure        25% of bankroll ($2,500)
5. Total exposure            60% of bankroll ($6,000)
6. Net directional           40% of bankroll ($4,000 max net long/short)
7. Same-direction per TF     3 max (e.g., max 3 BUY_YES on 1h)
8. Minimum position          $5 floor
```

### Edge Requirements

| Direction | Base Edge | CHOPPY/RISK_OFF Edge |
|-----------|-----------|----------------------|
| BUY_NO    | >= 8%     | >= 10%               |
| BUY_YES   | >= 12%    | >= 14%               |

BUY_YES requires a 4% premium because empirical results showed BUY_YES trades were systematically overconfident (14% win rate vs BUY_NO at 100% win rate in early paper trading).

### Trade Qualification Criteria

All conditions must be true:
1. Edge >= threshold (direction-aware)
2. Ensemble confidence >= 55
3. CLOB has enough depth for position without >3% slippage
4. Time to resolution > minimum (5m: 2min, 15m: 5min, 1h: 15min)
5. No unresolved model disagreement flags
6. Risk manager approves (all limits pass)

---

## TP/SL System

### Default Levels (Percentage-Based)

| Parameter       | Value | Description                           |
|-----------------|-------|---------------------------------------|
| `DEFAULT_SL_PCT`| 4%    | Flat stop-loss percentage             |
| `DEFAULT_TP_PCT`| 7%    | Flat take-profit percentage           |

TP > SL ensures wins outpace losses even with SL gapping on binary options.

### Price Level Conversion

TP/SL percentages are converted to YES price levels for monitoring:

```
BUY_YES:
  tp_price = entry_price * (1 + tp_pct)     capped at 0.95
  sl_price = entry_price * (1 - sl_pct)     floored at 0.01

BUY_NO (inverted logic -- NO profits when YES price drops):
  tp_price = entry_price - tp_pct * (1 - entry_price)   floored at 0.05
  sl_price = entry_price + sl_pct * (1 - entry_price)   capped at 0.99
```

### Monitoring Flow

```
                     +------------------+
                     |  Active Position  |
                     +--------+---------+
                              |
                     +--------v---------+
                     | Fetch CLOB Price  |
                     | (every 2 seconds) |
                     +--------+---------+
                              |
                    +---------+---------+
                    |                   |
               BUY_YES?            BUY_NO?
                    |                   |
        +-----------+-+          +------+--------+
        | price >= TP  |         | price <= TP    |
        | -> take_profit|        | -> take_profit |
        |              |         |                |
        | price <= SL  |         | price >= SL    |
        | -> stop_loss |         | -> stop_loss   |
        +-----------+--+         +--------+-------+
                    |                      |
                    +----------+-----------+
                               |
                    +----------v-----------+
                    | Check CLOB liquidity  |
                    | depth >= position_size?|
                    +----------+-----------+
                               |
                    YES        |        NO
                    +----------+--------+
                    |                   |
            +-------v------+    +------v-------+
            | Execute exit  |   | Skip exit,    |
            | (sell on CLOB)|   | log warning   |
            +-------+------+   +--------------+
                    |
            +-------v------+
            | Update trade  |
            | in database   |
            +--------------+
```

### Re-Entry System (1h Markets)

After a TP exit, the bot can re-enter the same market:
- After TP: re-entry allowed (direction confirmed, ensemble must still agree)
- After SL: re-entry BLOCKED (direction was wrong)
- Max 3 entries per market title
- Natural safety: edge drops near zero as binary price approaches extremes

---

## Learning Engine

### Recalibration Cycle

Triggered every 50 trades or weekly (whichever comes first):

```
Trade closes --> FeedbackRecord stored
                     |
                     v
            RECALIBRATION CYCLE
                     |
    +----------------+------------------+------------------+
    |                |                  |                  |
    v                v                  v                  v
Model Eval      Param Optim        SL/TP Optim      Calibration
(Brier scores)  (Optuna, 80+      (MAE/MFE, 30+    (pred vs
                 trades)           trades/bucket)    actual)
    |                |                  |                  |
    v                v                  v                  v
Weight adjust   PROBATION           Learned levels   Edge threshold
WARNING/CRIT    (30 shadow          replace defaults  adjustment
RETIRED         trades)
    |                |                  |                  |
    +----------------+------------------+------------------+
                     |
                     v
              Evolution Report
              (dashboard + alerts)
```

### Model Lifecycle

```
                +--------+
                | ACTIVE |<----- Brier drops below threshold
                +---+----+
                    |
            Brier > 0.28
                    |
                    v
              +---------+
              | WARNING |<---- Weight reduced 30%
              +----+----+      Flagged for mutation
                   |
           Brier > 0.35
                   |
                   v
             +----------+
             | CRITICAL  |<--- Near-zero weight
             +-----+-----+    Force Optuna optimization
                   |
          2 consecutive CRITICAL
                   |
                   v
             +---------+
             | RETIRED  |---> StrategyGraveyard
             +---------+     (death report stored)
```

### Safety Rails (Inviolable)

| Rule                                       | Limit                           |
|--------------------------------------------|---------------------------------|
| Max models mutated per cycle               | 1                               |
| Max models retired per cycle               | 1                               |
| Min active models at all times             | 4                               |
| Max parameter change from default          | 50% in one mutation             |
| Max SL/TP change per cycle                 | 3 percentage points             |
| Max ensemble weight change per cycle       | 15%                             |
| Min trades for Optuna                      | 80                              |
| Min trades for SL/TP learning              | 30 per bucket                   |
| Min shadow trades for promotion            | 30                              |
| Learning engine dormant                    | First 50 trades (cold start)    |

### Optuna Walk-Forward Validation

```
Trade history (chronological):
|<-------- 60% train -------->|<-- 20% val -->|<-- 20% holdout -->|

1. Optuna optimizes params on TRAIN set
2. Evaluate on VALIDATE set
3. IF validate_brier > train_brier + 0.05  --> REJECT (overfit)
4. IF accepted --> evaluate on HOLDOUT for final score
5. Validated params enter PROBATION (30 shadow trades)
6. After probation, promoted if outperforms parent version
```

---

## Graduation System

### Paper to Live Criteria (ALL must be met simultaneously)

| # | Criterion                    | Threshold                |
|---|------------------------------|--------------------------|
| 1 | Minimum paper trades         | >= 100                   |
| 2 | Win rate                     | > 54%                    |
| 3 | Total P&L                   | > $0                     |
| 4 | Sharpe ratio                 | > 0.8                    |
| 5 | Calibration error            | < 0.15                   |
| 6 | Max daily drawdown (30d)     | <= 6%                    |
| 7 | Calendar days of paper       | >= 14                    |
| 8 | Recalibration cycles         | >= 2                     |
| 9 | No CRITICAL models           | 0 models in CRITICAL     |

### De-Graduation Triggers (Back to Paper)

| Trigger                              | Threshold              |
|--------------------------------------|------------------------|
| Live daily drawdown                  | > 5%                   |
| Live win rate (50+ trades)           | < 48%                  |
| Models in CRITICAL simultaneously    | >= 2                   |

### Live Safety

- First 48 hours after graduation: half-size positions (50% of normal)
- `size_multiplier` property returns 0.5 during ramp-up, 1.0 after

---

## External API Integration

### API Reference

```
+-------------------------------+------------------------------------------+-----------+
| API                           | Base URL                                  | Auth      |
+-------------------------------+------------------------------------------+-----------+
| Gamma API (Market Discovery)  | https://gamma-api.polymarket.com          | None      |
| CLOB API (Order Book/Trading) | https://clob.polymarket.com               | EIP-712*  |
| Data API (Positions)          | https://data-api.polymarket.com           | None      |
| CLOB WebSocket                | wss://ws-subscriptions-clob.polymarket.com| None      |
| Binance (OHLCV)              | via ccxt                                   | API key   |
| Coinbase (Fallback OHLCV)    | via ccxt                                   | None      |
| Fear & Greed                  | https://api.alternative.me/fng/           | None      |
| Deribit (Optional IV)         | https://www.deribit.com/api/v2            | API key   |
| CryptoQuant (Optional Flows)  | https://api.cryptoquant.com               | API key   |
+-------------------------------+------------------------------------------+-----------+

* EIP-712 auth required only for trading (writes). Reads are unauthenticated.
```

### Gamma API Usage

```
GET /events?tag_id=21&active=true&closed=false&limit=50&offset=0
```

Response structure: Events contain nested Markets. Each Market has:
- `clobTokenIds`: stringified JSON -- must `json.loads()` to parse
- `outcomePrices`: stringified JSON -- must `json.loads()` to parse
- `question`, `volume`, `liquidity`, `endDate`

### Polymarket Fee Model

```
Taker fee = max_fee_rate * 2 * price * (1 - price)

Max fee rates by timeframe:
  5m:    1.56%  (fee at 50% prob = 0.78 cents)
  15m:   3.00%  (fee at 50% prob = 1.50 cents)
  1h:    0.00%  (free)
  4h:    0.00%  (free)
  daily: 0.00%  (free)

Maker orders: always FREE + earn daily USDC rebates
```

The fee is highest at price=0.50 and drops to ~0 at price extremes (near 0 or 1).

### Market Tier Execution Strategy

| Timeframe | Strategy      | Fee    | Entry Method                     |
|-----------|---------------|--------|----------------------------------|
| 15m       | Maker-only    | 0%     | GTC limit buy below best ask     |
| 1h        | FOK taker     | 0%     | Fill-or-kill market order        |
| 4h        | FOK taker     | 0%     | Fill-or-kill market order        |

---

## Database Schema

### Trade Table

```
trades
+-------------------------+------------+----------------------------------------------+
| Column                  | Type       | Description                                  |
+-------------------------+------------+----------------------------------------------+
| id                      | Integer PK | Auto-increment                               |
| trade_id                | String(64) | Unique trade ID (e.g., "PAPER-A1B2C3D4E5F6") |
| asset                   | String(10) | BTC, ETH, SOL, XRP                           |
| timeframe               | String(10) | 5m, 15m, 1h, 4h, daily                       |
| market_title            | String(256)| Polymarket question text                     |
| market_url              | String(512)| Polymarket market URL                        |
| market_type             | String(20) | "up_down" or "price_target"                  |
| action                  | String(10) | "BUY_YES" or "BUY_NO"                       |
| entry_price             | Float      | YES token price at entry                     |
| exit_price              | Float      | YES token price at exit (null if active)     |
| size_usd                | Float      | Position size in USD                         |
| pnl_usd                 | Float      | Realized P&L in USD                          |
| result                  | String(10) | "WON", "LOST", or null                       |
| status                  | String(10) | "ACTIVE", "CLOSED", "RESOLVED"               |
| exit_reason             | String(30) | resolution, take_profit, stop_loss,          |
|                         |            | time_decay, edge_evaporated                  |
| your_prob               | Float      | Ensemble probability at entry                |
| market_implied          | Float      | Market's implied probability at entry        |
| edge_at_entry           | Float      | Calculated edge at entry                     |
| confidence              | Integer    | Ensemble confidence at entry                 |
| tp_level                | Float      | Take-profit price level                      |
| sl_level                | Float      | Stop-loss price level                        |
| was_sl_learned          | Boolean    | True if SL was from learning engine          |
| would_have_won_if_held  | Boolean    | Retroactive flag for early exits             |
| max_adverse_excursion   | Float      | Worst price move against position            |
| max_favorable_excursion | Float      | Best price move in favor of position         |
| regime_at_entry         | String(20) | Market regime at entry time                  |
| param_versions_json     | Text       | JSON of model param versions used            |
| oracle_start_price      | Float      | Chainlink oracle price at interval start     |
| oracle_end_price        | Float      | Chainlink oracle price at interval end       |
| taker_fee_paid          | Float      | Total taker fee in USD                       |
| created_at              | DateTime   | Trade creation timestamp (UTC)               |
| resolved_at             | DateTime   | Resolution/exit timestamp (UTC)              |
+-------------------------+------------+----------------------------------------------+
Indexes: trade_id (unique), asset, status
```

### Signal Table

```
signals
+------------------+------------+------------------------------------+
| Column           | Type       | Description                        |
+------------------+------------+------------------------------------+
| id               | Integer PK | Auto-increment                     |
| asset            | String(10) | Asset symbol                       |
| timeframe        | String(10) | Timeframe                          |
| model_name       | String(30) | Model that generated the signal    |
| prob_up          | Float      | Predicted probability of up move   |
| confidence       | Integer    | Model confidence (0-100)           |
| param_version    | Integer    | Param version used                 |
| ensemble_prob    | Float      | Ensemble probability (if available)|
| created_at       | DateTime   | Timestamp (UTC)                    |
+------------------+------------+------------------------------------+
Indexes: asset, timeframe
```

### LearningEvent Table

```
learning_events
+--------------------+------------+--------------------------------------+
| Column             | Type       | Description                          |
+--------------------+------------+--------------------------------------+
| id                 | Integer PK | Auto-increment                       |
| event_type         | String(50) | param_mutation, model_retired,       |
|                    |            | sl_updated, weight_changed, etc.     |
| model_name         | String(30) | Affected model (nullable)            |
| timeframe          | String(10) | Timeframe context (nullable)         |
| details_json       | Text       | JSON with event details              |
| param_before_json  | Text       | Parameters before change             |
| param_after_json   | Text       | Parameters after change              |
| created_at         | DateTime   | Timestamp (UTC)                      |
+--------------------+------------+--------------------------------------+
Indexes: event_type
```

---

## Deployment

### Entry Point

```
python scripts/run_bot.py
```

Initialization order:
1. Settings from `.env`
2. Database (SQLite WAL or PostgreSQL)
3. Param registry with default parameters
4. All 7 quant models
5. Data providers, scanner, order book analyzer
6. Ensemble, pricing, risk, position manager
7. Paper or Live execution engine (based on `MODE`)
8. Regime detector, feedback store, SL/TP learner
9. Trading pipeline (13-step cycle)
10. Main loop (30s cycles + 2s fast monitor)

### Dashboard

```
streamlit run dashboard/app.py
```

### Active Timeframes

The bot currently runs with `timeframes=["15m", "1h", "4h"]`:
- 15m: Maker-only entry (0% fee via GTC limit orders)
- 1h: FOK taker entry (0% fee -- taker fees are 0% on 1h)
- 4h: FOK taker entry (0% fee)

### Dependencies

Core runtime dependencies (from `requirements.txt`):

| Package            | Version  | Purpose                         |
|--------------------|----------|---------------------------------|
| pandas             | >= 2.0   | Data manipulation               |
| numpy              | >= 1.24  | Numerical computation           |
| scipy              | >= 1.11  | Statistical functions           |
| ta                 | >= 0.11  | Technical analysis indicators   |
| httpx              | >= 0.25  | Async HTTP client               |
| ccxt               | >= 4.0   | Exchange API (Binance/Coinbase) |
| py_clob_client     | >= 0.1   | Polymarket CLOB SDK             |
| sqlalchemy         | >= 2.0   | ORM / database                  |
| pydantic           | >= 2.0   | Data validation                 |
| pydantic-settings  | >= 2.0   | Settings management             |
| structlog          | >= 23.0  | Structured logging              |
| apscheduler        | >= 3.10  | Task scheduling                 |
| streamlit          | >= 1.30  | Dashboard                       |
| optuna             | >= 3.4   | Hyperparameter optimization     |
| websockets         | >= 12.0  | WebSocket client                |
| python-dotenv      | >= 1.0   | Environment variable loading    |

Test dependencies: `pytest`, `pytest-asyncio`, `pytest-mock`.

---

## Key Design Decisions

### 1. Protocol-Based Dependency Injection

The `TradingPipeline` depends on abstract protocols (`DataProvider`, `MarketScanner`, `OrderBookAnalyzer`, `SignalGenerator`, `EnsembleAggregatorProtocol`), not concrete implementations. This enables:
- Unit testing with mock implementations
- Swapping components without modifying the pipeline
- Clear interface contracts

### 2. Dual-Loop Architecture

The main loop uses two concurrent asyncio tasks:
- **30-second main cycle**: Full 13-step pipeline (data fetch, signals, market scan, edge calc, execution)
- **2-second fast monitor**: CLOB price checks and TP/SL exits only

This separation ensures position exits happen within 2 seconds of trigger, while the heavier pipeline runs at a sustainable pace.

### 3. Non-Blocking Order Book Access

`py_clob_client.get_order_book()` is synchronous. To prevent blocking the async event loop (which would freeze the fast monitor), all CLOB calls are wrapped in `asyncio.to_thread()`.

### 4. Fee-Aware Market Tier Strategy

Different timeframes have different fee structures, leading to different execution strategies:
- 15m (3% max fee): Maker-only orders avoid the entire fee
- 1h/4h (0% fee): Standard FOK taker orders, no fee concern

### 5. BUY_YES Edge Premium

Empirical paper trading showed BUY_YES trades were systematically overconfident. A 4% edge premium is added to all BUY_YES trades (12% threshold vs 8% for BUY_NO).

### 6. SQLite WAL Mode

WAL (Write-Ahead Logging) mode is mandatory for development. Without it, the bot and Streamlit dashboard accessing the database concurrently would cause "database locked" errors. WAL mode is set via a SQLAlchemy `connect` event listener.

### 7. Flat TP/SL (No Tiering)

After extensive paper trading, the system converged on flat 4% SL / 7% TP with no confidence tiering or regime adjustments on defaults. The learning engine can later discover optimal levels per (asset, timeframe, regime) bucket.

### 8. Re-Entry with Safety Guards

After a TP exit on 1h markets, the bot can re-enter the same market (up to 3 times). After a SL exit, re-entry is blocked. This captures multiple profit opportunities from a single directional move without doubling down after a wrong call.

### 9. Fill Slippage Rejection

Trades are rejected if the simulated fill deviates too far from the midpoint. This prevents entering positions on thin order books where the walk-the-book price is significantly worse than the quoted mid.

### 10. Cold Start Protection

For the first 50 trades, the learning engine is dormant. Default weights and TP/SL levels are used. This prevents the system from drawing incorrect conclusions from insufficient data. Optuna requires 80 trades, and SL/TP learning requires 30 trades per bucket.
