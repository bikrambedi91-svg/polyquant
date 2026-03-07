# CLAUDE.md — PolyQuant Project Brain
# Claude Code reads this file automatically from the project root.
# It contains everything Claude needs to make smart decisions while building.

---

## WHAT WE ARE BUILDING

PolyQuant — a self-learning Python trading bot that:
1. Runs 7 quant models on BTC, ETH, SOL, XRP to predict price direction
2. Compares predictions against Polymarket crypto prediction market prices
3. Executes YES/NO bets when edge > 8%, with adaptive stop-loss/take-profit
4. Learns from every trade: evolves model parameters, optimizes SL/TP levels, retires broken models
5. Paper trades first, auto-graduates to live when proven profitable
6. Displays everything in a Streamlit dashboard

---

## POLYMARKET — HOW IT ACTUALLY WORKS (VERIFIED MARCH 2026)

### Market Types We Trade

| Duration | Structure | Resolution | Taker Fee (max at 50% prob) | Assets |
|----------|-----------|------------|----------------------------|--------|
| 5 min | UP/DOWN binary ("Will BTC go up?") | Chainlink oracle on Polygon | 1.56% | BTC, ETH, SOL, XRP |
| 15 min | UP/DOWN binary | Chainlink oracle | 3.0% | BTC, ETH, SOL, XRP |
| 1 hour | UP/DOWN binary | Chainlink oracle | 0% (free) | BTC, ETH, SOL, XRP |
| 4 hour | UP/DOWN binary | Chainlink oracle | 0% (free) | BTC, ETH, SOL, XRP |
| Daily+ | Price targets ("Will BTC be above $X?") | Varies | 0% (free) | Various |

**Fee curve formula:** `fee = max_fee_rate × 2 × price × (1 - price)`
Fee is highest at price=0.50, drops to ~0 at price extremes (near 0 or 1).
Maker orders are FREE and earn daily USDC rebates.

**5m/15m UP/DOWN resolution:** "UP" = Chainlink oracle price at interval END ≥ price at interval START. That's it. Simple binary.

**Market availability:** 5m markets are NOT always available. They appear and disappear. The bot must handle zero markets gracefully.

### API Architecture

| API | Base URL | Auth | Purpose |
|-----|----------|------|---------|
| Gamma API | https://gamma-api.polymarket.com | None | Market discovery, metadata |
| CLOB API | https://clob.polymarket.com | None for reads, EIP-712 for trades | Orderbook, prices, order placement |
| Data API | https://data-api.polymarket.com | None | User positions, trade history |
| WebSocket | wss://ws-subscriptions-clob.polymarket.com | None | Real-time book updates |
| RTDS | Real-Time Data Stream | None | Live crypto prices |

### Gamma API — Market Discovery (CORRECT endpoints)

```python
# CORRECT — filter crypto markets
GET https://gamma-api.polymarket.com/events?tag_id=21&active=true&closed=false&limit=50&offset=0

# WRONG (old spec had this):
# GET https://gamma-api.polymarket.com/markets?tag=crypto  ← THIS DOES NOT WORK
```

Tag IDs: politics=2, **crypto=21**, sports=100639, tech=1401

Response structure: Events contain nested Markets. Each Market has:
- `clobTokenIds`: `["YES_TOKEN_ID", "NO_TOKEN_ID"]`
- `outcomePrices`: `'["0.65","0.35"]'` (stringified JSON — must parse)
- `question`, `volume`, `liquidity`, `endDate`

Paginate with `limit` + `offset`.

### CLOB API — Order Book (using py_clob_client)

```python
from py_clob_client.client import ClobClient

# Public reads (no auth)
client = ClobClient("https://clob.polymarket.com")
book = client.get_order_book(token_id)     # bids[], asks[]
mid = client.get_midpoint(token_id)        # float
spread = client.get_spread(token_id)       # float
price = client.get_price(token_id, "BUY")  # float

# Authenticated trading (for live mode)
client = ClobClient(
    "https://clob.polymarket.com",
    key=PRIVATE_KEY,
    chain_id=137,
    signature_type=1,          # 0=EOA, 1=email/Magic, 2=browser wallet
    funder=PROXY_FUNDER_ADDRESS  # Your Polymarket deposit address
)
client.set_api_creds(client.create_or_derive_api_creds())

# Place order
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY
order = client.create_order(OrderArgs(
    token_id=TOKEN_ID,
    price=0.55,
    size=100,     # in shares
    side=BUY
))
resp = client.post_order(order, OrderType.GTC)
```

### Volume Thresholds (adjusted for market type)

| Timeframe | Min Volume | Rationale |
|-----------|-----------|-----------|
| 5m | $5,000 | Individual 5m markets have low per-market volume |
| 15m | $15,000 | Moderate volume |
| 1h | $50,000 | Good volume |
| 4h | $100,000 | High volume |
| Daily+ | $150,000 | Must be liquid |

---

## THE 7 QUANT MODELS

### Model Weights by Timeframe

| Model | 5m | 15m | 1h | 4h | Why |
|-------|-----|------|-----|-----|-----|
| MomentumRegime | 0.20 | 0.20 | 0.18 | 0.16 | Fast-reacting, works at all TFs |
| FundingBasis | 0.05 | 0.10 | 0.18 | 0.22 | Slow data, more relevant on longer TFs |
| ChainFlow | **0.00** | **0.00** | 0.12 | 0.18 | Updates every 10+ min, useless on 5m/15m |
| VolSurface | 0.05 | 0.08 | 0.14 | 0.15 | Options data is slow-updating |
| SentimentComp | **0.00** | **0.00** | 0.08 | 0.13 | F&G updates ONCE PER DAY, useless on short TFs |
| TechConfluence | 0.35 | 0.32 | 0.20 | 0.16 | Noisy on short TFs but still useful |
| **CLOBSignal** | **0.35** | **0.30** | 0.10 | **0.00** | Reads Polymarket book as signal. Crucial on 5m. Noise on 4h. |

Models with confidence=0 automatically get zero effective weight in ensemble.

### CLOBSignal — The 7th Model (NEW, critical for short timeframes)

Reads the Polymarket order book itself as a directional signal:
- Bid/ask size imbalance > 1.3 → smart money buying YES → bullish boost
- Bid/ask size imbalance < 0.7 → smart money selling YES → bearish boost  
- Recent large trades (>$500 in last 2 min) → follow the direction
- Only active on 5m/15m (weighted 0 on 4h+ — too noisy on long horizons)

### All Parameters Are Learnable

Every model parameter has a defined range. The learning engine can mutate any parameter within its range. After mutation, constraints are validated:
- `ema_fast` must be < `ema_slow`
- `rsi_bull_threshold` must be > `rsi_bear_threshold`
- All values within their min/max range

---

## EDGE CALCULATION (must account for fees)

```
taker_fee = max_fee_rate × 2 × share_price × (1 - share_price)
effective_implied_prob = yes_price + taker_fee + expected_slippage
edge = |our_ensemble_prob - effective_implied_prob| - resolution_risk_penalty
```

**Trade qualifies only if ALL true:**
- Edge ≥ 8% (≥ 10% in CHOPPY or RISK_OFF regime)
- Ensemble confidence ≥ 55
- CLOB has enough depth for 0.5× Kelly without > 3% slippage
- Time to resolution > 2 min (5m) / > 5 min (15m) / > 15 min (1h)
- No unresolved model disagreement flags

**15-minute markets are the hardest to profit on** because 3% max fee eats most edges. The bot should be very selective on 15m — edge threshold should effectively be 11%+ to compensate.

---

## RISK MANAGEMENT — HARD LIMITS (NEVER EXCEED)

| Rule | Limit |
|------|-------|
| Max single position | 12% of bankroll |
| Max per asset (all markets) | 25% of bankroll |
| Max total exposure | 60% of bankroll |
| Daily drawdown halt | 8% → pause ALL new trades |
| Minimum position | $50 (fees eat edge below this) |
| Kelly fraction | 0.25× (conf < 75), 0.40× (75-85), 0.50× (> 85) |

---

## ADAPTIVE TP/SL — HOW EXITS WORK ON BINARY MARKETS

Polymarket positions are YES/NO tokens. "Stop-loss" = selling your position on the CLOB before resolution.

**Default levels (before learning engine has enough data):**

| Timeframe | Stop-Loss | Take-Profit Offset |
|-----------|-----------|-------------------|
| 5m | 8 cents below entry | +5 cents above our_prob |
| 15m | 10 cents | +5 cents |
| 1h | 12 cents | +5 cents |
| 4h | 15 cents | +5 cents |

**Regime adjustments:**
- RISK_OFF: tighten SL 20%, tighten TP 10%
- HIGH_VOL: widen SL 30%, widen TP 20%
- TRENDING: widen TP 25%, normal SL
- CHOPPY: tighten both 15%

**CRITICAL: Before any exit, check CLOB has enough liquidity to sell.** If book is too thin, log warning and skip exit. Don't assume you can always sell.

**The learning engine optimizes SL/TP** by analyzing max_adverse_excursion (worst price reached) and max_favorable_excursion (best price reached) across historical trades, per (asset, timeframe, regime) bucket. After 30+ trades in a bucket, learned levels replace defaults.

---

## LEARNING ENGINE — HOW THE BOT GETS SMARTER

### Feedback Loop (runs every 50 trades or weekly)

```
TRADE CLOSES → FeedbackRecord stored (signals, params, MAE, MFE, result, fees)
    ↓
RECALIBRATION CYCLE:
    ├── Model Evaluation → Brier scores → update ensemble weights
    │   WARNING (Brier > 0.28) → reduce weight 30%, flag for mutation
    │   CRITICAL (Brier > 0.35) → near-zero weight, force Optuna optimization
    │   RETIRED (2 cycles CRITICAL) → move to graveyard, set weight 0
    │
    ├── Parameter Optimization (Optuna, min 80 trades)
    │   Walk-forward: 60% train / 20% validate / 20% holdout
    │   Overfit check: validate Brier > train + 0.05 → reject
    │   New params → PROBATION (shadow mode, 30 trades before promotion)
    │
    ├── SL/TP Optimization
    │   Simulate SL levels 0.03–0.25 against actual MAE data
    │   Pick level maximizing total P&L per (asset, TF, regime) bucket
    │   Max change: 3 cents per cycle
    │
    ├── Calibration Check
    │   Predicted probs vs actual outcomes
    │   Overconfident → raise edge threshold
    │
    └── Evolution Report → Dashboard + Telegram/Discord alert
```

### Safety Rails (NEVER VIOLATE)

- Max 1 model mutated per recalibration cycle
- Max 1 model retired per cycle
- Minimum 4 active models at all times
- Max parameter change: 50% from default in one mutation
- Max SL/TP change: 3 cents per cycle
- Max ensemble weight change: 15% per cycle
- Optuna needs minimum 80 trades (not 50)
- All mutated params must pass constraint validation
- Learning engine is dormant for first 50 trades (cold start)

### Cold Start Behavior (first 50 trades)

- Use DEFAULT model weights, no Brier adjustment
- Use DEFAULT TP/SL levels from config
- Learning engine dormant (no recalibration)
- After trade 50: first recalibration cycle
- After trade 80: Optuna parameter optimization becomes available

---

## GRADUATION — PAPER → LIVE

**ALL criteria must be met simultaneously:**
1. ≥ 100 paper trades
2. Win rate > 54%
3. Total P&L > 0
4. Sharpe ratio > 0.8
5. Calibration error < 0.15
6. No single day drawdown > 6% in last 30 days
7. ≥ 14 calendar days of paper trading
8. ≥ 2 recalibration cycles completed
9. No model currently in CRITICAL state

**De-graduation (back to paper):**
- Live daily drawdown > 5%
- Win rate < 48% over 50+ live trades
- 2+ models in CRITICAL simultaneously

**Live safety:** First 48 hours at half-size (50% of normal Kelly).

---

## TECH STACK DECISIONS

| Choice | Reason |
|--------|--------|
| `ta` library (NOT `ta-lib`) | Pure Python, installs cleanly on Windows + Linux. Same indicators. |
| SQLite + WAL mode for dev | `PRAGMA journal_mode=WAL` prevents "database locked" when bot + dashboard access concurrently |
| PostgreSQL for production | Proper concurrent access on VPS |
| `httpx` (async) | Non-blocking API calls, better than requests for concurrent feeds |
| `py_clob_client` | Official Polymarket Python SDK for CLOB reads and order placement |
| `websockets` | For real-time CLOB book updates on 5m/15m markets |
| `optuna` | Hyperparameter optimization for model evolution |
| `structlog` | JSON structured logging for production debugging |

---

## PROJECT STRUCTURE

```
polyquant/
├── CLAUDE.md                    ← THIS FILE (you are reading it)
├── config/
│   ├── settings.py              # Pydantic settings from .env
│   └── constants.py             # Assets, timeframes, weights, fees, thresholds
├── models/
│   ├── base.py                  # ABC + ModelParams + ModelOutput dataclasses
│   ├── momentum_regime.py       # Model 1: ADX + DI trend classification
│   ├── funding_basis.py         # Model 2: Perp funding rate (contrarian)
│   ├── chain_flow.py            # Model 3: Exchange net flows
│   ├── vol_surface.py           # Model 4: IV skew / realized vol
│   ├── sentiment.py             # Model 5: Fear & Greed (daily only)
│   ├── tech_confluence.py       # Model 6: RSI/MACD/BB/VWAP/Volume
│   ├── clob_signal.py           # Model 7: Polymarket book imbalance (5m/15m only)
│   ├── ensemble.py              # Bayesian weighted aggregator
│   └── param_registry.py        # Versioned parameter storage + constraint validation
├── learning/
│   ├── feedback_db.py           # Trade outcome records for learning
│   ├── regime_detector.py       # RISK_ON/OFF, HIGH_VOL, TRENDING, CHOPPY
│   ├── sl_tp_learner.py         # Adaptive stop-loss/take-profit optimizer
│   ├── model_evolver.py         # WARNING → CRITICAL → RETIRED pipeline
│   ├── param_optimizer.py       # Optuna walk-forward parameter search
│   ├── strategy_graveyard.py    # Retired models with death reports
│   ├── strategy_nursery.py      # Shadow/probation testing
│   └── evolution_report.py      # Human-readable recalibration summary
├── market/
│   ├── scanner.py               # Gamma API market discovery (tag_id=21)
│   ├── orderbook.py             # CLOB order book analysis + WebSocket
│   ├── resolution.py            # Resolution risk scoring
│   └── pricing.py               # Fee-aware edge calculation
├── execution/
│   ├── paper_engine.py          # Simulated execution with real CLOB prices
│   ├── live_engine.py           # Real execution via py_clob_client
│   ├── position_manager.py      # Adaptive TP/SL + liquidity-checked exits
│   └── risk_manager.py          # Kelly sizing + hard limits + correlation
├── data/
│   ├── price_feed.py            # OHLCV via ccxt (Binance/Coinbase)
│   ├── funding_feed.py          # Binance Futures funding rates
│   ├── onchain_feed.py          # Exchange flows (optional, default disabled)
│   ├── sentiment_feed.py        # Fear & Greed index (updates daily)
│   └── cache.py                 # In-memory TTL cache
├── database/
│   ├── models.py                # SQLAlchemy ORM (WAL mode for SQLite)
│   ├── trades.py                # Trade CRUD
│   ├── signals.py               # Signal storage
│   └── learning_log.py          # Learning event storage
├── dashboard/
│   ├── app.py                   # Streamlit main (7 tabs)
│   └── pages/                   # One file per tab
├── orchestrator/
│   ├── pipeline.py              # 13-step trading cycle
│   ├── main_loop.py             # APScheduler orchestration
│   └── graduation.py            # Paper → Live transition
├── tests/                       # Unit + integration tests
├── scripts/
│   ├── run_bot.py               # Entry point
│   ├── seed_mock_data.py        # Generate test data
│   ├── validate_paper.py        # Check graduation criteria
│   └── deploy.sh                # VPS deployment
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env
```

---

## BUILD ORDER (MANDATORY — PHASE GATES)

Phase 1: config/ + data/ + database/ → Gate: unit tests pass
Phase 2: models/ (all 7 + ensemble + registry) → Gate: unit tests pass
Phase 3: market/ (scanner + orderbook + pricing) → Gate: unit tests pass
Phase 4: execution/ (paper + TP/SL + risk) → Gate: unit tests pass
Phase 5: learning/ (feedback + SL learner + evolver + optimizer) → Gate: unit tests pass
Phase 6: orchestrator/ (pipeline + main loop + graduation) → Gate: integration tests pass
Phase 7: dashboard/ (Streamlit, 7 tabs) → Gate: all tabs render
Phase 8: Paper trading validation (14+ days, 100+ trades)
Phase 9: VPS deployment with Docker

**NEVER skip a gate. NEVER build Phase N+1 until Phase N tests pass.**

---

## COMMON MISTAKES TO AVOID

1. Do NOT use `ta-lib` — use `ta` (pure Python). `ta-lib` requires C compilation.
2. Do NOT use `?tag=crypto` on Gamma API — use `?tag_id=21`.
3. Do NOT assume flat fees — use the fee curve formula per timeframe.
4. Do NOT assume 5m/15m markets are price targets — they are UP/DOWN bets.
5. Do NOT forget SQLite WAL mode — bot and dashboard will deadlock without it.
6. Do NOT try to exit a position without checking CLOB liquidity first.
7. Do NOT run Optuna with fewer than 80 trades — results will be noise.
8. Do NOT let sentiment/chain_flow models have weight on 5m/15m — they're stale data.
9. Do NOT forget to call `client.set_api_creds(client.create_or_derive_api_creds())` before live trading.
10. Do NOT parse `outcomePrices` from Gamma API without JSON.loads() — it's a string, not a list.
