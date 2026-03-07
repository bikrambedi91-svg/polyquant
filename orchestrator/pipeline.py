"""TradingPipeline — 13-step async trading cycle.

Steps:
1. Regime detection (BTC proxy)
2. Data fetch (OHLCV for all assets)
3. Active model signals + ensemble aggregation
4. Shadow/probation model signals
5. Market discovery (Polymarket scanner)
6. Order book analysis
7. Edge calculation (fee-aware)
8. Kelly sizing + risk checks
9. Position monitoring (TP/SL + liquidity)
10. Execute trades / exits
11. Feedback logging
12. Learning cycle (if due)
13. Dashboard push

Handles:
- Empty scanner results → skip market analysis, just monitor positions
- All models low confidence → HOLD
- API rate limiting
- Cycle errors → log and continue
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

import structlog

from data.price_feed import FeedHealthError

from config.constants import ASSETS, MARKET_TIMEFRAMES

logger = structlog.get_logger(__name__)


class DataProvider(Protocol):
    """Interface for fetching OHLCV data."""
    async def get_ohlcv(self, asset: str, timeframe: str) -> Any: ...


class MarketScanner(Protocol):
    """Interface for market discovery."""
    async def discover_markets(self) -> list: ...


class OrderBookAnalyzer(Protocol):
    """Interface for order book analysis."""
    async def analyze(self, token_id: str, size_usd: float) -> Any: ...


class SignalGenerator(Protocol):
    """Interface for model signal generation."""
    async def generate_signals(self, asset: str, timeframe: str, ohlcv: Any, **kwargs) -> list: ...


class EnsembleAggregatorProtocol(Protocol):
    """Interface for ensemble aggregation."""
    def aggregate(self, signals: list, timeframe: str) -> Any: ...


@dataclass
class CycleResult:
    """Result of a single trading cycle."""
    timestamp: str = ""
    regime: str = "RISK_ON"
    markets_found: int = 0
    signals_generated: int = 0
    trades_opened: int = 0
    exits_executed: int = 0
    positions_monitored: int = 0
    action: str = "HOLD"          # "TRADE", "HOLD", "EXIT_ONLY"
    errors: list[str] = field(default_factory=list)
    step_times: dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class TradingPipeline:
    """Orchestrates the 13-step trading cycle.

    All dependencies are injected for testability. Each step is isolated
    so failures in one step don't crash the whole cycle.
    """

    def __init__(
        self,
        regime_detector=None,
        data_provider=None,
        signal_generator=None,
        ensemble=None,
        scanner=None,
        orderbook=None,
        pricing_engine=None,
        risk_manager=None,
        position_manager=None,
        execution_engine=None,
        feedback_store=None,
        model_evolver=None,
        nursery=None,
        sl_tp_learner=None,
        report_generator=None,
        settings=None,
        decision_logger=None,
    ):
        self._regime = regime_detector
        self._data = data_provider
        self._signals = signal_generator
        self._ensemble = ensemble
        self._scanner = scanner
        self._orderbook = orderbook
        self._pricing = pricing_engine
        self._risk = risk_manager
        self._positions = position_manager
        self._engine = execution_engine
        self._feedback = feedback_store
        self._evolver = model_evolver
        self._nursery = nursery
        self._sl_tp = sl_tp_learner
        self._reports = report_generator
        self._settings = settings
        self._dlog = decision_logger  # DecisionLogger for live dashboard visibility

        self._api_calls = 0
        self._last_cycle_time: datetime | None = None
        self._cycle_count = 0
        self._trade_count_at_last_recal = 0
        self._last_markets: list = []  # Cached for position monitoring
        self._no_price_cycles: dict[str, int] = {}  # trade_id -> consecutive no-price count
        self._last_known_price: dict[str, float] = {}  # trade_id -> last seen YES price
        self._trade_tokens: dict[str, str] = {}  # trade_id -> CLOB token_id (for fast monitor)
        self._http_client = None  # Lazy-init httpx.AsyncClient for fast CLOB fetches

        # Multi-timeframe confirmation: cache ensemble results across TF cycles
        # Used to gate 5m/15m trades with 1h directional agreement
        self._ensemble_cache: dict[str, dict] = {}  # {asset: {timeframe: ensemble_obj}}

        # Re-entry safety tracking: market_title -> [(exit_reason, exit_time), ...]
        # Allows re-entry after TP (direction confirmed), blocks after SL (direction wrong).
        # Max 3 entries per market title per hour window.
        self._market_exits: dict[str, list[tuple[str, datetime]]] = {}
        # Count total entries per market title (including initial)
        self._market_entry_count: dict[str, int] = {}
        MAX_ENTRIES_PER_MARKET = 3  # Cap total entries per 1h market window

        # Fill tracking: attempted trades vs actually filled (for live readiness)
        self._trades_attempted = 0
        self._trades_filled = 0
        self._trades_rejected_spread = 0
        self._trades_rejected_slippage = 0
        self._trailing_sl_triggers = 0

    def _default_tp(self, trade: dict) -> float:
        """Default take-profit level (YES price) based on action and confidence."""
        from config.constants import DEFAULT_SL_PCT, get_tp_pct_for_confidence
        confidence = trade.get("confidence", 65)
        tp_pct = get_tp_pct_for_confidence(confidence)
        entry = trade["market_implied"]
        if trade["action"] == "BUY_YES":
            return min(entry * (1.0 + tp_pct), 0.95)
        else:
            no_cost = 1.0 - entry
            return max(entry - tp_pct * no_cost, 0.05)

    def _default_sl(self, trade: dict) -> float:
        """Default stop-loss level (YES price) based on action."""
        from config.constants import DEFAULT_SL_PCT
        entry = trade["market_implied"]
        if trade["action"] == "BUY_YES":
            return max(entry * (1.0 - DEFAULT_SL_PCT), 0.01)
        else:
            no_cost = 1.0 - entry
            return min(entry + DEFAULT_SL_PCT * no_cost, 0.99)

    async def run_cycle(self, timeframe: str = "1h") -> CycleResult:
        """Execute one full 13-step trading cycle.

        Returns CycleResult summarizing what happened.
        """
        result = CycleResult()
        self._cycle_count += 1

        # Start decision logging for this cycle
        if self._dlog:
            self._dlog.start_cycle(timeframe)

        try:
            # Step 1: Regime detection
            regime_state = await self._step_regime()
            result.regime = regime_state.get("regime", "RISK_ON") if regime_state else "RISK_ON"

            # Step 2: Data fetch
            ohlcv_data = await self._step_data_fetch(timeframe)

            # Step 2b: Market discovery (moved before signals so CLOBSignal has book data)
            markets = await self._step_discover_markets()
            result.markets_found = len(markets)

            # Log market scan results
            if self._dlog:
                self._dlog.log_market_scan(markets, timeframe)

            # Step 2c: Fetch orderbooks for assets we have OHLCV for
            asset_matched = self._match_markets_by_asset(
                list(ohlcv_data.keys()), markets, timeframe,
            )
            book_data = {}
            if asset_matched:
                book_data = await self._step_orderbooks_selective(asset_matched)

            # Build per-asset book_data dict for CLOBSignal model
            clob_book_per_asset = self._build_clob_book_per_asset(
                asset_matched, book_data,
            )

            # Step 3: Active model signals + ensemble (with book_data for CLOBSignal)
            ensemble_results = await self._step_signals(
                ohlcv_data, timeframe, clob_book_per_asset,
            )
            result.signals_generated = len(ensemble_results)

            # Cache ensemble results for multi-timeframe confirmation
            for ens_res in ensemble_results:
                a = ens_res["asset"]
                if a not in self._ensemble_cache:
                    self._ensemble_cache[a] = {}
                self._ensemble_cache[a][timeframe] = ens_res["ensemble"]

                # Log signals + ensemble for each asset
                if self._dlog:
                    self._dlog.log_signals(
                        a, ens_res["signals"], ens_res["ensemble"], timeframe,
                    )

            # Step 4: Shadow/probation signals
            await self._step_shadow_signals(ohlcv_data, timeframe)

            # Step 7b: Edge calculation (uses pre-matched markets)
            trade_candidates = await self._step_edge_calc(
                ensemble_results, markets, book_data, timeframe, result.regime,
            )

            # Step 8: Kelly sizing + risk checks
            sized_trades = await self._step_kelly_sizing(
                trade_candidates, result.regime,
            )

            # Step 9: Position monitoring (always runs, even with no new markets)
            exit_signals = await self._step_monitor_positions()
            result.positions_monitored = len(exit_signals.get("monitored", []))

            # Step 10: Execute trades and exits (with dedup check)
            exec_result = await self._step_execute(sized_trades, exit_signals)
            result.trades_opened = exec_result.get("opened", 0)
            result.exits_executed = exec_result.get("exited", 0)

            # Step 11: Feedback logging
            await self._step_feedback(exec_result)

            # Step 12: Learning cycle (if due)
            await self._step_learning()

            # Step 13: Dashboard push (placeholder)
            await self._step_dashboard_push(result)

            # Determine overall action
            if result.trades_opened > 0:
                result.action = "TRADE"
            elif result.exits_executed > 0:
                result.action = "EXIT_ONLY"
            else:
                result.action = "HOLD"

            # Log cycle summary
            if self._dlog:
                self._dlog.log_cycle_summary(
                    regime=result.regime,
                    markets_found=result.markets_found,
                    signals_generated=result.signals_generated,
                    trades_opened=result.trades_opened,
                    action=result.action,
                )

        except FeedHealthError:
            raise  # Must propagate — halt the bot, never trade blind
        except Exception as exc:
            result.errors.append(f"Cycle error: {str(exc)}")
            logger.error("pipeline_cycle_error", error=str(exc), cycle=self._cycle_count)

        self._last_cycle_time = datetime.now(timezone.utc)

        logger.info(
            "pipeline_cycle_complete",
            cycle=self._cycle_count,
            action=result.action,
            regime=result.regime,
            markets=result.markets_found,
            trades=result.trades_opened,
            exits=result.exits_executed,
            errors=len(result.errors),
        )

        return result

    # ── Step implementations ──

    async def _step_regime(self) -> dict | None:
        """Step 1: Detect market regime from BTC data."""
        if not self._regime or not self._data:
            return None
        try:
            btc_ohlcv = await self._data.get_ohlcv("BTC", "1h")
            if btc_ohlcv is None:
                return None
            state = self._regime.detect(btc_ohlcv)
            return {
                "regime": state.regime,
                "confidence": state.confidence,
                "kelly_mult": state.kelly_mult,
                "edge_threshold": state.edge_threshold,
                "sl_mult": state.sl_mult,
                "tp_mult": state.tp_mult,
            }
        except FeedHealthError:
            raise  # Must propagate — halt the bot
        except Exception as exc:
            logger.error("step_regime_error", error=str(exc))
            return None

    async def _step_data_fetch(self, timeframe: str) -> dict:
        """Step 2: Fetch OHLCV for all assets.

        FeedHealthError propagates up to halt the bot — never trade blind.
        """
        if not self._data:
            return {}
        data = {}
        for asset in ASSETS:
            try:
                ohlcv = await self._data.get_ohlcv(asset, timeframe)
                if ohlcv is not None:
                    data[asset] = ohlcv
            except FeedHealthError:
                raise  # Must propagate — halt the bot
            except Exception as exc:
                logger.error("step_data_error", asset=asset, error=str(exc))
        return data

    async def _step_signals(
        self, ohlcv_data: dict, timeframe: str,
        clob_book_per_asset: dict | None = None,
    ) -> list[dict]:
        """Step 3: Generate model signals and ensemble aggregation."""
        if not self._signals or not self._ensemble:
            return []

        clob_book_per_asset = clob_book_per_asset or {}
        results = []
        for asset, ohlcv in ohlcv_data.items():
            try:
                kwargs = {}
                book = clob_book_per_asset.get(asset)
                if book:
                    kwargs["book_data"] = book
                signals = await self._signals.generate_signals(
                    asset, timeframe, ohlcv, **kwargs,
                )
                ensemble = self._ensemble.aggregate(signals, timeframe)
                results.append({
                    "asset": asset,
                    "timeframe": timeframe,
                    "ensemble": ensemble,
                    "signals": signals,
                })
            except Exception as exc:
                logger.error("step_signals_error", asset=asset, error=str(exc))
        return results

    async def _step_shadow_signals(self, ohlcv_data: dict, timeframe: str) -> None:
        """Step 4: Run shadow/probation model signals."""
        if not self._nursery:
            return
        # Shadow signals are recorded but don't affect trading
        # Implementation deferred to nursery integration

    async def _step_discover_markets(self) -> list:
        """Step 5: Discover active crypto markets."""
        if not self._scanner:
            return []
        try:
            markets = await self._scanner.discover_markets()
            self._last_markets = markets  # Cache for position monitoring
            return markets
        except Exception as exc:
            logger.error("step_discover_error", error=str(exc))
            return []

    def _match_markets_by_asset(
        self, assets: list[str], markets: list, timeframe: str,
    ) -> list:
        """Match markets by asset list + timeframe (no ensemble needed).

        Used early in the pipeline to fetch orderbooks for CLOBSignal.
        """
        compatible_tfs = {timeframe}
        if timeframe == "daily":
            compatible_tfs |= {"weekly", "monthly"}

        tradeable_types = {"up_down", "price_target"}
        asset_set = set(assets)

        matched = []
        for m in markets:
            asset = getattr(m, "asset", None) or m.get("asset", "")
            tf = getattr(m, "timeframe", None) or m.get("timeframe", "")
            mtype = getattr(m, "market_type", None) or m.get("market_type", "")
            yes_price = getattr(m, "current_yes_price", 0.5)
            if (
                asset in asset_set
                and tf in compatible_tfs
                and mtype in tradeable_types
                and 0.15 <= yes_price <= 0.85
            ):
                matched.append(m)
        return matched

    def _build_clob_book_per_asset(
        self, matched_markets: list, book_data: dict,
    ) -> dict:
        """Build per-asset book_data dict for CLOBSignal model.

        Returns: {"BTC": {"total_bid_size": ..., "total_ask_size": ..., ...}, ...}
        """
        result = {}
        for m in matched_markets:
            asset = getattr(m, "asset", None) or m.get("asset", "")
            token_id = getattr(m, "token_id_yes", None) or m.get("token_id_yes", "")
            if asset in result:
                continue  # One book per asset is enough
            snap = book_data.get(token_id)
            if snap:
                try:
                    result[asset] = {
                        "total_bid_size": getattr(snap, "total_bid_size", 0),
                        "total_ask_size": getattr(snap, "total_ask_size", 0),
                        "bid_ask_imbalance": getattr(snap, "bid_ask_imbalance", 1.0),
                        "recent_large_trades": [],
                    }
                except Exception:
                    pass  # Skip if snap doesn't have expected attrs
        return result

    def _match_markets_to_assets(
        self, ensemble_results: list, markets: list, timeframe: str,
    ) -> list:
        """Pre-filter markets to only those matching our assets and timeframe.

        Returns a small list of markets we actually need orderbooks for.
        """
        compatible_tfs = {timeframe}
        if timeframe == "daily":
            compatible_tfs |= {"weekly", "monthly"}

        tradeable_types = {"up_down", "price_target"}
        signal_assets = {r["asset"] for r in ensemble_results}

        matched = []
        for m in markets:
            asset = getattr(m, "asset", None) or m.get("asset", "")
            tf = getattr(m, "timeframe", None) or m.get("timeframe", "")
            mtype = getattr(m, "market_type", None) or m.get("market_type", "")
            yes_price = getattr(m, "current_yes_price", 0.5)
            if (
                asset in signal_assets
                and tf in compatible_tfs
                and mtype in tradeable_types
                and 0.15 <= yes_price <= 0.85
            ):
                matched.append(m)
        return matched

    async def _step_orderbooks_selective(self, matched_markets: list) -> dict:
        """Step 6: Analyze order books ONLY for markets matching our assets."""
        if not self._orderbook:
            return {}
        books = {}
        for market in matched_markets:
            try:
                token_id = getattr(market, "token_id_yes", None) or market.get("token_id_yes", "")
                if token_id:
                    snap = await self._orderbook.analyze(token_id)
                    books[token_id] = snap
            except Exception as exc:
                logger.warning("step_orderbook_error", error=str(exc))
        logger.info("orderbooks_fetched", count=len(books), requested=len(matched_markets))
        return books

    async def _step_orderbooks(self, markets: list) -> dict:
        """Step 6: Analyze order books for discovered markets (legacy, unused)."""
        return await self._step_orderbooks_selective(markets)

    async def _step_edge_calc(
        self, ensemble_results: list, markets: list,
        book_data: dict, timeframe: str, regime: str,
    ) -> list[dict]:
        """Step 7: Calculate edge for each ensemble signal vs market."""
        if not self._pricing or not ensemble_results or not markets:
            return []

        candidates = []
        # Build lookup: asset -> market
        # For "daily" cycle, also match weekly/monthly markets (same OHLCV signals)
        compatible_tfs = {timeframe}
        if timeframe == "daily":
            compatible_tfs |= {"weekly", "monthly"}

        # Only trade markets our models can actually answer
        tradeable_types = {"up_down", "price_target"}

        market_lookup = {}
        for m in markets:
            asset = getattr(m, "asset", None) or m.get("asset", "")
            tf = getattr(m, "timeframe", None) or m.get("timeframe", "")
            mtype = getattr(m, "market_type", None) or m.get("market_type", "")
            yes_price = getattr(m, "current_yes_price", 0.5)
            if tf in compatible_tfs and mtype in tradeable_types:
                # Skip extreme-probability markets where our signal adds no value
                if yes_price < 0.15 or yes_price > 0.85:
                    continue
                # Prefer markets closest to 0.50 (highest uncertainty = most edge potential)
                if asset not in market_lookup:
                    market_lookup[asset] = m
                else:
                    existing_price = getattr(market_lookup[asset], "current_yes_price", 0.5)
                    if abs(yes_price - 0.5) < abs(existing_price - 0.5):
                        market_lookup[asset] = m

        logger.info(
            "edge_calc_markets",
            timeframe=timeframe,
            matched_assets=list(market_lookup.keys()),
            total_markets=len(markets),
        )

        # ── Edge thresholds ──
        # Base 10% edge (lowered from 12% to increase trade volume while
        # still ensuring profitability after fees). Quality gated by model
        # agreement + contrarian price filters.
        edge_threshold = 0.10
        if regime in ("CHOPPY", "RISK_OFF"):
            edge_threshold = 0.12

        # BUY_YES premium: model's bullish predictions have been less
        # reliable historically. Require modest extra edge for BUY_YES.
        BUY_YES_EDGE_PREMIUM = 0.02  # +2% extra edge required (total 12%)

        for ens_result in ensemble_results:
            asset = ens_result["asset"]
            ensemble = ens_result["ensemble"]

            if asset not in market_lookup:
                if self._dlog:
                    self._dlog.log_filter(asset, "market_match", False,
                                          f"No {timeframe} market found for {asset}",
                                          {"available_markets": list(market_lookup.keys())})
                continue

            market = market_lookup[asset]
            yes_price = getattr(market, "current_yes_price", 0.5)

            # ── Asset exclusion (data-driven) ──
            # ETH previously excluded (0W/5L on old models). Re-enabled with
            # tighter edge requirement (+2%) to validate current model performance.
            # Will re-exclude if WR < 40% after 20+ trades.
            _EXCLUDED_ASSETS = set()  # Empty — all assets enabled
            _TIGHTER_EDGE_ASSETS = {"ETH"}  # Assets requiring extra edge
            if asset in _EXCLUDED_ASSETS:
                logger.info("edge_skip_excluded_asset", asset=asset)
                if self._dlog:
                    self._dlog.log_filter(asset, "excluded_asset", False,
                                          f"{asset} in excluded list",
                                          {"excluded_assets": list(_EXCLUDED_ASSETS)})
                continue

            # ── Minimum confidence 50 for all assets ──
            # Lowered from 52→50: Ensemble conf is structurally depressed when
            # neutral models (VolSurf=0.50, Sentiment=0.50) cause agreement penalty.
            # Quality gated by: model agreement (2+ directional models),
            # contrarian price filter, and 10% edge threshold.
            MIN_CONFIDENCE = 50
            if ensemble.confidence < MIN_CONFIDENCE:
                logger.info("edge_skip_low_confidence", asset=asset, confidence=ensemble.confidence, min_conf=MIN_CONFIDENCE, prob_up=round(ensemble.prob_up, 3))
                if self._dlog:
                    self._dlog.log_filter(asset, "confidence", False,
                                          f"confidence {ensemble.confidence} < {MIN_CONFIDENCE}",
                                          {"confidence": ensemble.confidence,
                                           "min_required": MIN_CONFIDENCE,
                                           "prob_up": round(ensemble.prob_up, 4)})
                continue

            # Compute effective implied
            token_id = getattr(market, "token_id_yes", "")
            slippage = 0.0
            if token_id in book_data:
                snap = book_data[token_id]
                slippage = getattr(snap, "expected_slippage_cents", 0.0) if snap else 0.0

                # Use CLOB midpoint as yes_price when available — Gamma API
                # outcomePrices can be very stale for markets 15+ min into window.
                # CLOB midpoint reflects actual current market price.
                clob_mid = getattr(snap, "midpoint", 0.0) if snap else 0.0
                if 0.05 < clob_mid < 0.95:
                    gamma_price = yes_price
                    yes_price = clob_mid
                    if abs(gamma_price - clob_mid) > 0.03:
                        logger.info(
                            "using_clob_midpoint",
                            asset=asset,
                            gamma_price=round(gamma_price, 3),
                            clob_mid=round(clob_mid, 3),
                            delta=round(abs(gamma_price - clob_mid), 3),
                        )

            # After CLOB midpoint override, re-check price bounds
            # (Gamma price may pass 0.15-0.85 filter but CLOB may be extreme)
            if yes_price < 0.15 or yes_price > 0.85:
                logger.debug("edge_skip_clob_extreme", asset=asset, clob_price=round(yes_price, 3))
                continue

            effective_yes = self._pricing.effective_implied_prob(
                yes_price, timeframe, expected_slippage=slippage,
            )

            # Direction-aware edge: maker entry = 0% fee on both sides
            if ensemble.prob_up >= effective_yes:
                # BUY_YES candidate: our prob > market's effective YES cost
                action = "BUY_YES"
                edge = ensemble.prob_up - effective_yes
            else:
                # BUY_NO candidate: our NO prob > market's effective NO cost
                # Maker entry: effective_no = (1 - yes_price) + slippage (0% fee)
                effective_no = (1.0 - yes_price) + slippage
                edge = (1.0 - ensemble.prob_up) - effective_no
                action = "BUY_NO"

            # ── Directional alignment check (relaxed from 0.60 to 0.55) ──
            # Data from 18 v3 trades shows YES 0.55-0.60 = 50% WR.
            # At 50% WR with 10%+ edge, still profitable after fees.
            # Relaxing to generate more paper trades for learning engine data.
            # Will tighten back to 0.60 if WR drops below 55% after 50+ trades.
            MIN_YES_FOR_BUY_NO = 0.55
            MAX_YES_FOR_BUY_YES = 0.45
            if action == "BUY_NO" and yes_price < MIN_YES_FOR_BUY_NO:
                logger.info(
                    "edge_skip_not_contrarian",
                    asset=asset,
                    action=action,
                    yes_price=round(yes_price, 3),
                    min_required=MIN_YES_FOR_BUY_NO,
                    reason="BUY_NO needs bullish market (YES>=0.60) for contrarian edge",
                )
                if self._dlog:
                    self._dlog.log_filter(asset, "yes_price", False,
                                          f"BUY_NO: YES={yes_price:.3f} < {MIN_YES_FOR_BUY_NO} (market not bullish enough)",
                                          {"action": action, "yes_price": round(yes_price, 4),
                                           "threshold": MIN_YES_FOR_BUY_NO},
                                          market_title=getattr(market, "title", ""))
                continue
            if action == "BUY_YES" and yes_price > MAX_YES_FOR_BUY_YES:
                logger.info(
                    "edge_skip_not_contrarian",
                    asset=asset,
                    action=action,
                    yes_price=round(yes_price, 3),
                    max_allowed=MAX_YES_FOR_BUY_YES,
                    reason="BUY_YES needs bearish market (YES<=0.40) for contrarian edge",
                )
                if self._dlog:
                    self._dlog.log_filter(asset, "yes_price", False,
                                          f"BUY_YES: YES={yes_price:.3f} > {MAX_YES_FOR_BUY_YES} (market not bearish enough)",
                                          {"action": action, "yes_price": round(yes_price, 4),
                                           "threshold": MAX_YES_FOR_BUY_YES},
                                          market_title=getattr(market, "title", ""))
                continue

            # YES price passed — log it
            if self._dlog:
                threshold_used = MIN_YES_FOR_BUY_NO if action == "BUY_NO" else MAX_YES_FOR_BUY_YES
                self._dlog.log_filter(asset, "yes_price", True,
                                      f"{action}: YES={yes_price:.3f} passed threshold {threshold_used}",
                                      {"action": action, "yes_price": round(yes_price, 4),
                                       "threshold": threshold_used},
                                      market_title=getattr(market, "title", ""))

            # ── Model agreement filter — require 2+ models to agree with trade direction ──
            # Ensures signal isn't driven by just one noisy model.
            # Checks agreement with the TRADE ACTION (BUY_YES needs bullish models,
            # BUY_NO needs bearish models), not just raw ensemble direction.
            model_outputs = getattr(ensemble, "model_outputs", [])
            if model_outputs:
                bearish_models = sum(
                    1 for m in model_outputs
                    if m.confidence >= 30 and m.prob_up < 0.45
                )
                bullish_models = sum(
                    1 for m in model_outputs
                    if m.confidence >= 30 and m.prob_up > 0.55
                )
                if action == "BUY_NO" and bearish_models < 2:
                    logger.info(
                        "edge_skip_insufficient_model_agreement",
                        asset=asset,
                        action=action,
                        bearish_models=bearish_models,
                        bullish_models=bullish_models,
                        required=2,
                        prob_up=round(ensemble.prob_up, 3),
                    )
                    if self._dlog:
                        self._dlog.log_filter(asset, "model_agreement", False,
                                              f"BUY_NO: only {bearish_models} bearish models (need 2+)",
                                              {"action": action, "bearish_models": bearish_models,
                                               "bullish_models": bullish_models, "required": 2,
                                               "prob_up": round(ensemble.prob_up, 4)},
                                              market_title=getattr(market, "title", ""))
                    continue
                if action == "BUY_YES" and bullish_models < 2:
                    logger.info(
                        "edge_skip_insufficient_model_agreement",
                        asset=asset,
                        action=action,
                        bearish_models=bearish_models,
                        bullish_models=bullish_models,
                        required=2,
                        prob_up=round(ensemble.prob_up, 3),
                    )
                    if self._dlog:
                        self._dlog.log_filter(asset, "model_agreement", False,
                                              f"BUY_YES: only {bullish_models} bullish models (need 2+)",
                                              {"action": action, "bearish_models": bearish_models,
                                               "bullish_models": bullish_models, "required": 2,
                                               "prob_up": round(ensemble.prob_up, 4)},
                                              market_title=getattr(market, "title", ""))
                    continue

            # NOTE: Ensemble disagreement block REMOVED.
            # Neutral models (VolSurface conf=20, MomRegime when choppy) always
            # return ~0.50, which "disagrees" with any directional ensemble by >12%.
            # This caused false positives blocking every trade. The model agreement
            # filter (2+ models must agree directionally) is the proper quality gate.
            # Disagreement flags still logged at ensemble level for monitoring.

            effective_threshold_for_log = (
                edge_threshold + BUY_YES_EDGE_PREMIUM
                if action == "BUY_YES"
                else edge_threshold
            )
            logger.info(
                "edge_evaluation",
                asset=asset,
                our_prob=round(ensemble.prob_up, 3),
                yes_price=yes_price,
                effective_yes=round(effective_yes, 3),
                edge=round(edge, 3),
                action=action,
                threshold=effective_threshold_for_log,
                confidence=ensemble.confidence,
                has_book=token_id in book_data,
            )

            effective_threshold = (
                edge_threshold + BUY_YES_EDGE_PREMIUM
                if action == "BUY_YES"
                else edge_threshold
            )
            # Tighter edge for historically weak assets (ETH)
            if asset in _TIGHTER_EDGE_ASSETS:
                effective_threshold += 0.02

            # Log the edge calculation result
            if self._dlog:
                self._dlog.log_edge_check(
                    asset=asset, action=action,
                    yes_price=yes_price, our_prob=ensemble.prob_up,
                    effective_yes=effective_yes, edge=edge,
                    threshold=effective_threshold, confidence=ensemble.confidence,
                    market_title=getattr(market, "title", ""),
                    extra={"slippage": slippage, "has_book": token_id in book_data},
                )

            if edge >= effective_threshold:
                # Multi-timeframe confirmation: 5m/15m trades require 1h agreement
                if timeframe in ("5m", "15m"):
                    mtf_ok, mtf_reason = self._check_higher_tf_agreement(
                        asset, action,
                    )
                    if not mtf_ok:
                        logger.info(
                            "edge_skip_no_1h_confirmation",
                            asset=asset,
                            timeframe=timeframe,
                            action=action,
                            edge=round(edge, 3),
                            reason=mtf_reason,
                        )
                        if self._dlog:
                            self._dlog.log_filter(asset, "mtf_confirmation", False,
                                                  f"1h timeframe disagrees: {mtf_reason}",
                                                  {"action": action, "edge": round(edge, 4),
                                                   "reason": mtf_reason},
                                                  market_title=getattr(market, "title", ""))
                        continue

                # All filters passed! Log and add to candidates
                if self._dlog:
                    self._dlog.log_filter(asset, "all_passed", True,
                                          f"{action} edge={edge:.3f} conf={ensemble.confidence} - QUALIFIED",
                                          {"action": action, "edge": round(edge, 4),
                                           "confidence": ensemble.confidence,
                                           "yes_price": round(yes_price, 4)},
                                          market_title=getattr(market, "title", ""))

                candidates.append({
                    "asset": asset,
                    "timeframe": timeframe,
                    "action": action,
                    "our_prob": ensemble.prob_up,
                    "market_implied": yes_price,
                    "edge": edge,
                    "confidence": ensemble.confidence,
                    "market": market,
                    "ensemble": ensemble,
                    "token_id": token_id,
                })

        return candidates

    def _check_higher_tf_agreement(
        self, asset: str, action: str,
    ) -> tuple[bool, str]:
        """Check if 1h ensemble agrees with direction of a 5m/15m trade.

        BUY_YES requires 1h prob_up >= 0.50 (not bearish).
        BUY_NO requires 1h prob_up <= 0.50 (not bullish).
        If 1h data isn't cached yet, allow trade (don't block on cold start).
        """
        if asset not in self._ensemble_cache:
            return True, "no_cache_yet"

        hourly = self._ensemble_cache[asset].get("1h")
        if hourly is None:
            return True, "no_1h_data_yet"

        # If 1h confidence is very low, don't use it as filter
        if hourly.confidence < 40:
            return True, "1h_low_confidence"

        if action == "BUY_YES" and hourly.prob_up < 0.45:
            return False, f"1h_bearish_{hourly.prob_up:.2f}"
        if action == "BUY_NO" and hourly.prob_up > 0.55:
            return False, f"1h_bullish_{hourly.prob_up:.2f}"

        return True, "ok"

    async def _step_kelly_sizing(
        self, candidates: list, regime: str,
    ) -> list[dict]:
        """Step 8: Size positions with Kelly and check risk limits."""
        if not self._risk or not candidates:
            return []

        # Get real active positions from DB for risk checks
        active_positions = []
        if hasattr(self._engine, "_db"):
            from database.trades import get_active_trades
            try:
                active = get_active_trades(self._engine._db)
                active_positions = [
                    {
                        "asset": t.asset,
                        "size_usd": t.size_usd,
                        "status": t.status,
                        "action": t.action,
                        "timeframe": t.timeframe,
                    }
                    for t in active
                ]
            except Exception:
                pass

        # Get daily P&L for drawdown check
        daily_pnl = 0.0
        if hasattr(self._engine, "_db"):
            from database.trades import get_daily_pnl
            try:
                daily_pnl = get_daily_pnl(self._engine._db)
            except Exception:
                pass

        sized = []
        for cand in candidates:
            try:
                # Fixed position size — no Kelly sizing
                size = self._risk.get_position_size()

                # Check risk limits with REAL active positions
                ok, reason = self._risk.check_limits(
                    cand["asset"], size, active_positions, daily_pnl,
                    action=cand["action"], timeframe=cand["timeframe"],
                )
                if not ok:
                    logger.info("risk_limit_blocked", asset=cand["asset"], reason=reason)
                    if self._dlog:
                        self._dlog.log_risk_check(cand["asset"], False, reason,
                                                  {"size_usd": size, "daily_pnl": daily_pnl})
                    continue
                if self._dlog:
                    self._dlog.log_risk_check(cand["asset"], True, "Risk limits OK",
                                              {"size_usd": size, "daily_pnl": daily_pnl})

                cand["size_usd"] = size
                sized.append(cand)
                # Track this new position for subsequent checks in same cycle
                active_positions.append({
                    "asset": cand["asset"],
                    "size_usd": size,
                    "status": "ACTIVE",
                    "action": cand["action"],
                    "timeframe": cand["timeframe"],
                })
            except Exception as exc:
                logger.error("step_sizing_error", asset=cand.get("asset"), error=str(exc))

        return sized

    async def _step_monitor_positions(self) -> dict:
        """Step 9: Monitor active positions for TP/SL/time triggers.

        Checks current CLOB prices against each trade's TP/SL levels.
        Returns exit signals for trades that should be closed.
        """
        if not self._engine or not hasattr(self._engine, "_db"):
            return {"monitored": [], "exits": []}

        from database.trades import get_active_trades

        try:
            active = get_active_trades(self._engine._db)
        except Exception as exc:
            logger.error("monitor_db_error", error=str(exc))
            return {"monitored": [], "exits": []}

        if not active:
            return {"monitored": [], "exits": []}

        logger.info("monitoring_positions", count=len(active))

        # Build title->market lookup from cached scanner data
        title_lookup = {}
        if self._last_markets:
            for m in self._last_markets:
                mtitle = getattr(m, "title", "")
                if mtitle:
                    title_lookup[mtitle] = m

        exits = []
        monitored = []

        for trade in active:
            try:
                current_price = None

                # Match against last-discovered markets by title
                if trade.market_title and trade.market_title in title_lookup:
                    m = title_lookup[trade.market_title]
                    current_price = getattr(m, "current_yes_price", None)

                if current_price is None:
                    # Track consecutive no-price cycles for stale detection
                    count = self._no_price_cycles.get(trade.trade_id, 0) + 1
                    self._no_price_cycles[trade.trade_id] = count
                    logger.info("monitor_no_price", trade_id=trade.trade_id[-8:],
                                asset=trade.asset, no_price_cycles=count,
                                title=trade.market_title[:50] if trade.market_title else "?")
                    # After 5 cycles (~2-3 min) with no price, try resolution
                    if count >= 5:
                        exit_price = await self._resolve_expired_trade(trade)
                        exits.append({
                            "trade_id": trade.trade_id,
                            "current_price": exit_price,
                            "reason": "market_expired",
                        })
                        logger.warning("stale_trade_expired", trade_id=trade.trade_id,
                                       action=trade.action, exit_price=exit_price,
                                       no_price_cycles=count)
                    monitored.append({"trade_id": trade.trade_id, "status": "no_price"})
                    continue

                # Reset no-price counter when price found
                self._no_price_cycles.pop(trade.trade_id, None)
                # Cache the last known price for use on expiry
                self._last_known_price[trade.trade_id] = current_price

                # Track MAE/MFE for learning engine — use USD P&L
                if trade.action == "BUY_YES":
                    shares = trade.size_usd / trade.entry_price if trade.entry_price > 0 else 0
                    unrealized = (current_price - trade.entry_price) * shares
                else:
                    no_entry = 1.0 - trade.entry_price
                    shares = trade.size_usd / no_entry if no_entry > 0 else 0
                    unrealized = (trade.entry_price - current_price) * shares

                logger.info(
                    "position_check",
                    trade_id=trade.trade_id[-8:],
                    asset=trade.asset,
                    entry=round(trade.entry_price, 3),
                    current=round(current_price, 3),
                    unrealized=round(unrealized, 4),
                    tp=trade.tp_level,
                    sl=trade.sl_level,
                )

                monitored.append({
                    "trade_id": trade.trade_id,
                    "current_price": current_price,
                    "entry_price": trade.entry_price,
                    "tp": trade.tp_level,
                    "sl": trade.sl_level,
                })

                # TP/SL active on ALL markets (including UP/DOWN binary).
                # has_tp/has_sl guards handle edge case of legacy zero-level trades.
                has_tp = trade.tp_level and trade.tp_level > 0
                has_sl = trade.sl_level and trade.sl_level > 0

                # ── Trailing SL: move SL to breakeven when 50% of TP target reached ──
                from config.constants import TRAILING_SL_TRIGGER, SL_SLIPPAGE_CENTS
                if has_tp and has_sl:
                    if trade.action == "BUY_YES":
                        tp_dist = trade.tp_level - trade.entry_price
                        prog = current_price - trade.entry_price
                        if tp_dist > 0 and prog >= TRAILING_SL_TRIGGER * tp_dist:
                            if trade.sl_level < trade.entry_price:
                                prev_sl = trade.sl_level
                                from database.trades import update_trade
                                update_trade(self._engine._db, trade.trade_id, sl_level=trade.entry_price)
                                trade.sl_level = trade.entry_price
                                self._trailing_sl_triggers += 1
                                logger.info("trailing_sl_breakeven",
                                            trade_id=trade.trade_id[-8:],
                                            old_sl=round(prev_sl, 4),
                                            new_sl=round(trade.entry_price, 4))
                    else:  # BUY_NO
                        tp_dist = trade.entry_price - trade.tp_level
                        prog = trade.entry_price - current_price
                        if tp_dist > 0 and prog >= TRAILING_SL_TRIGGER * tp_dist:
                            if trade.sl_level > trade.entry_price:
                                prev_sl = trade.sl_level
                                from database.trades import update_trade
                                update_trade(self._engine._db, trade.trade_id, sl_level=trade.entry_price)
                                trade.sl_level = trade.entry_price
                                self._trailing_sl_triggers += 1
                                logger.info("trailing_sl_breakeven",
                                            trade_id=trade.trade_id[-8:],
                                            old_sl=round(prev_sl, 4),
                                            new_sl=round(trade.entry_price, 4))

                # Check TP/SL for BUY_YES: price going up = good
                # TP exits use TP price (simulates pre-placed limit sell order)
                # SL exits use current price (market sell for emergency exit + slippage)
                if trade.action == "BUY_YES":
                    if has_tp and current_price >= trade.tp_level:
                        exits.append({
                            "trade_id": trade.trade_id,
                            "current_price": trade.tp_level,  # Limit sell at TP
                            "reason": "take_profit",
                        })
                        logger.info("tp_hit", trade_id=trade.trade_id,
                                    price=current_price, exit_at=trade.tp_level, tp=trade.tp_level)
                    elif has_sl and current_price <= trade.sl_level:
                        exits.append({
                            "trade_id": trade.trade_id,
                            "current_price": current_price - SL_SLIPPAGE_CENTS,
                            "reason": "stop_loss",
                        })
                        logger.info("sl_hit", trade_id=trade.trade_id,
                                    price=current_price, sl=trade.sl_level,
                                    exit_with_slippage=round(current_price - SL_SLIPPAGE_CENTS, 3))
                else:  # BUY_NO: YES price going down = good for us
                    # TP/SL stored as YES prices: TP is low (YES drops), SL is high (YES rises)
                    if has_tp and current_price <= trade.tp_level:
                        exits.append({
                            "trade_id": trade.trade_id,
                            "current_price": trade.tp_level,  # Limit sell at TP
                            "reason": "take_profit",
                        })
                        logger.info("tp_hit_no", trade_id=trade.trade_id,
                                    price=current_price, tp=trade.tp_level)
                    elif has_sl and current_price >= trade.sl_level:
                        exits.append({
                            "trade_id": trade.trade_id,
                            "current_price": current_price + SL_SLIPPAGE_CENTS,
                            "reason": "stop_loss",
                        })
                        logger.info("sl_hit_no", trade_id=trade.trade_id,
                                    price=current_price, sl=trade.sl_level,
                                    exit_with_slippage=round(current_price + SL_SLIPPAGE_CENTS, 3))

            except Exception as exc:
                logger.error("monitor_position_error",
                             trade_id=trade.trade_id, error=str(exc))

        if exits:
            logger.info("position_exits_triggered", count=len(exits))

        return {"monitored": monitored, "exits": exits}

    async def _resolve_expired_trade(self, trade) -> float:
        """Determine exit price for an expired market.

        Priority:
        1. Try CLOB API for resolved price (should be ~0 or ~1)
        2. Use last known market price
        3. Worst-case assumption
        """
        # Try CLOB API — resolved markets often show price near 0 or 1
        if self._orderbook:
            try:
                from database.models import Trade
                # Get token_id from cached scanner data — search by market_title
                token_id = None
                # Try to get price directly from CLOB client
                if hasattr(self._orderbook, '_client'):
                    clob = self._orderbook._client
                    # We need the token_id — check if stored on trade
                    # For now, skip direct CLOB lookup
                    pass
            except Exception:
                pass

        # Use last known price (much better than worst-case)
        last_price = self._last_known_price.pop(trade.trade_id, None)
        if last_price is not None:
            logger.info("expired_using_last_price", trade_id=trade.trade_id[-8:],
                        last_price=round(last_price, 3), action=trade.action)
            return last_price

        # Worst-case fallback: BUY_YES loses if YES→0, BUY_NO loses if YES→1
        logger.warning("expired_worst_case", trade_id=trade.trade_id[-8:],
                        action=trade.action)
        return 0.0 if trade.action == "BUY_YES" else 1.0

    async def _step_execute(self, sized_trades: list, exit_signals: dict) -> dict:
        """Step 10: Execute new trades and exits."""
        if not self._engine:
            return {"opened": 0, "exited": 0, "trades": []}

        opened = 0
        exited = 0
        trades = []

        # Build trade_id -> market_title lookup for exit recording
        exit_title_lookup = {}
        if hasattr(self._engine, "_db"):
            from database.trades import get_trade
            for exit_sig in exit_signals.get("exits", []):
                try:
                    t = get_trade(self._engine._db, exit_sig["trade_id"])
                    if t and t.market_title:
                        exit_title_lookup[exit_sig["trade_id"]] = t.market_title
                except Exception:
                    pass

        # Execute exits first
        for exit_sig in exit_signals.get("exits", []):
            try:
                result = await self._engine.execute_sell(
                    exit_sig["trade_id"],
                    exit_sig["current_price"],
                    exit_sig["reason"],
                )
                if result:
                    exited += 1
                    trades.append(result)
                    # Clean up stale counter + token cache
                    self._no_price_cycles.pop(exit_sig["trade_id"], None)
                    self._trade_tokens.pop(exit_sig["trade_id"], None)

                    # Record exit reason for re-entry safety tracking
                    exit_title = exit_title_lookup.get(exit_sig["trade_id"], "")
                    if exit_title:
                        if exit_title not in self._market_exits:
                            self._market_exits[exit_title] = []
                        self._market_exits[exit_title].append(
                            (exit_sig["reason"], datetime.now(timezone.utc))
                        )
                        logger.info(
                            "exit_recorded_for_reentry",
                            title=exit_title[:60],
                            reason=exit_sig["reason"],
                            total_exits=len(self._market_exits[exit_title]),
                        )
            except Exception as exc:
                logger.error("execute_exit_error", error=str(exc))

        # Dedup check: get active trades to avoid opening duplicates
        active_titles = set()
        if hasattr(self._engine, "_db"):
            from database.trades import get_active_trades
            try:
                active = get_active_trades(self._engine._db)
                active_titles = {t.market_title for t in active if t.market_title}
            except Exception:
                pass

        # Execute new buys
        for trade in sized_trades:
            try:
                market = trade.get("market")
                market_title = getattr(market, "title", "") if market else ""
                market_type = getattr(market, "market_type", "up_down") if market else "up_down"

                # Dedup: skip if we already have an active trade on this market
                if market_title and market_title in active_titles:
                    logger.info("trade_dedup_skipped", asset=trade.get("asset"),
                                market_title=market_title[:60])
                    continue

                # Re-entry safety: check exit history for this market
                if market_title and market_title in self._market_exits:
                    exit_history = self._market_exits[market_title]
                    entry_count = self._market_entry_count.get(market_title, 0)

                    # Cap total entries per market window (default 3)
                    if entry_count >= 3:
                        logger.info("reentry_max_entries_reached",
                                    asset=trade.get("asset"),
                                    entries=entry_count,
                                    title=market_title[:60])
                        continue

                    # Block re-entry after SL (direction was wrong)
                    last_exit_reason = exit_history[-1][0] if exit_history else ""
                    if last_exit_reason == "stop_loss":
                        logger.info("reentry_blocked_after_sl",
                                    asset=trade.get("asset"),
                                    action=trade.get("action"),
                                    title=market_title[:60])
                        continue

                    # Allow re-entry after TP (direction confirmed, ensemble rechecked)
                    if last_exit_reason == "take_profit":
                        logger.info("reentry_after_tp",
                                    asset=trade.get("asset"),
                                    action=trade.get("action"),
                                    entry_num=entry_count + 1,
                                    title=market_title[:60])

                # Percentage-based TP/SL for ALL markets.
                # SL=5% of cost basis. TP=5-30% by confidence.
                # Computed from market_implied initially, recalculated from fill below.
                tp_sl = None
                if self._positions:
                    tp_sl = self._positions.calculate_tp_sl(
                        trade["asset"], trade["timeframe"],
                        "RISK_ON",
                        trade["market_implied"],
                        trade["our_prob"],
                        trade["action"],
                        confidence=trade["confidence"],
                    )
                tp_level = tp_sl.tp_price if tp_sl else self._default_tp(trade)
                sl_level = tp_sl.sl_price if tp_sl else self._default_sl(trade)
                was_sl_learned = tp_sl.was_learned if tp_sl else False

                self._trades_attempted += 1
                result = await self._engine.execute_buy(
                    asset=trade["asset"],
                    timeframe=trade["timeframe"],
                    action=trade["action"],
                    size_usd=trade["size_usd"],
                    our_prob=trade["our_prob"],
                    market_implied=trade["market_implied"],
                    edge=trade["edge"],
                    confidence=trade["confidence"],
                    tp_level=tp_level,
                    sl_level=sl_level,
                    regime="RISK_ON",
                    token_id=trade.get("token_id", ""),
                    market_title=market_title,
                    market_url=getattr(market, "url", "") if market else "",
                    market_type=market_type,
                    param_versions=trade["ensemble"].param_versions if trade.get("ensemble") else None,
                    was_sl_learned=was_sl_learned,
                )
                if result:
                    self._trades_filled += 1
                    opened += 1
                    trades.append(result)

                    # Log trade execution
                    if self._dlog:
                        self._dlog.log_trade_executed(
                            asset=trade["asset"], action=trade["action"],
                            entry_price=result.get("fill_price", trade["market_implied"]),
                            size_usd=trade["size_usd"],
                            tp=tp_level, sl=sl_level,
                            market_title=market_title,
                        )

                    if market_title:
                        active_titles.add(market_title)
                        # Track entry count for re-entry cap
                        self._market_entry_count[market_title] = (
                            self._market_entry_count.get(market_title, 0) + 1
                        )

                    # Cache token_id for fast monitoring (2s CLOB price checks)
                    token_id = trade.get("token_id", "")
                    if token_id:
                        self._trade_tokens[result["trade_id"]] = token_id

                    # Always recalculate TP/SL from actual fill price (ALL markets)
                    if self._positions:
                        fill_price = result.get("fill_price", trade["market_implied"])
                        real_tp_sl = self._positions.calculate_tp_sl(
                            trade["asset"], trade["timeframe"],
                            "RISK_ON",
                            fill_price,
                            trade["our_prob"],
                            trade["action"],
                            confidence=trade["confidence"],
                        )
                        if hasattr(self._engine, "_db"):
                            from database.trades import update_trade
                            update_trade(
                                self._engine._db,
                                result["trade_id"],
                                tp_level=real_tp_sl.tp_price,
                                sl_level=real_tp_sl.sl_price,
                            )
                            logger.info(
                                "tp_sl_from_fill",
                                trade_id=result["trade_id"],
                                fill_price=fill_price,
                                tp=real_tp_sl.tp_price,
                                sl=real_tp_sl.sl_price,
                            )
                else:
                    # Trade rejected by engine (spread too wide, slippage too high, etc.)
                    logger.info("trade_rejected_by_engine",
                                asset=trade.get("asset"), action=trade.get("action"))
            except Exception as exc:
                logger.error("execute_buy_error", asset=trade.get("asset"), error=str(exc))

        # Log fill rate metrics every cycle that had attempts
        if self._trades_attempted > 0:
            fill_rate = self._trades_filled / self._trades_attempted * 100
            logger.info(
                "fill_rate_metrics",
                attempted=self._trades_attempted,
                filled=self._trades_filled,
                fill_rate=round(fill_rate, 1),
                rejected_spread=self._trades_rejected_spread,
                rejected_slippage=self._trades_rejected_slippage,
                trailing_sl_triggers=self._trailing_sl_triggers,
            )

        return {"opened": opened, "exited": exited, "trades": trades}

    async def _step_feedback(self, exec_result: dict) -> None:
        """Step 11: Log feedback for closed trades."""
        # Feedback logging deferred to when trades close
        pass

    async def _step_learning(self) -> None:
        """Step 12: Run learning cycle if due."""
        if not self._feedback:
            return

        total = self._feedback.total_trades
        if self._feedback.is_cold_start():
            return  # Dormant for first 50 trades

        interval = 50  # from settings
        if total - self._trade_count_at_last_recal >= interval:
            self._trade_count_at_last_recal = total
            logger.info("learning_cycle_triggered", total_trades=total)
            # Full recalibration would run here

    async def _step_dashboard_push(self, result: CycleResult) -> None:
        """Step 13: Push data to dashboard (placeholder)."""
        pass

    # ------------------------------------------------------------------
    # Fast monitor — 2-second CLOB price checks for 5m/15m positions
    # ------------------------------------------------------------------

    async def _get_clob_price(self, token_id: str) -> float | None:
        """Fetch fresh midpoint from CLOB API (single lightweight call)."""
        import httpx

        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=5.0)

        try:
            resp = await self._http_client.get(
                "https://clob.polymarket.com/midpoint",
                params={"token_id": token_id},
            )
            resp.raise_for_status()
            data = resp.json()
            mid = data.get("mid")
            return float(mid) if mid else None
        except Exception as exc:
            logger.warning("clob_price_error", token_id=token_id[:16], error=str(exc))
            return None

    async def fast_monitor(self) -> int:
        """Fast 2-second monitoring for 5m/15m positions.

        Fetches fresh CLOB prices directly (not from scanner cache)
        and checks TP/SL. Executes exits immediately.
        Returns number of exits executed.
        """
        if not self._engine or not hasattr(self._engine, "_db"):
            return 0

        from database.trades import get_active_trades

        try:
            active = get_active_trades(self._engine._db)
        except Exception:
            return 0

        # Fast-monitor all active trades for precise TP/SL + timeout execution
        short_term = [t for t in active if t.timeframe in ("5m", "15m", "1h", "4h")]
        if not short_term:
            return 0

        exits = []
        skipped_no_token = 0
        skipped_no_price = 0

        for trade in short_term:
            token_id = self._trade_tokens.get(trade.trade_id)
            if not token_id:
                skipped_no_token += 1
                continue

            # Fetch fresh CLOB price
            current_price = await self._get_clob_price(token_id)
            if current_price is None or current_price <= 0:
                skipped_no_price += 1
                continue

            # Cache last known price
            self._last_known_price[trade.trade_id] = current_price

            has_tp = trade.tp_level and trade.tp_level > 0
            has_sl = trade.sl_level and trade.sl_level > 0

            # ── Trailing SL: move SL to breakeven when 50% of TP target reached ──
            from config.constants import TRAILING_SL_TRIGGER, SL_SLIPPAGE_CENTS
            if has_tp and has_sl:
                if trade.action == "BUY_YES":
                    tp_distance = trade.tp_level - trade.entry_price
                    price_progress = current_price - trade.entry_price
                    if tp_distance > 0 and price_progress >= TRAILING_SL_TRIGGER * tp_distance:
                        if trade.sl_level < trade.entry_price:
                            prev_sl = trade.sl_level
                            from database.trades import update_trade
                            update_trade(self._engine._db, trade.trade_id, sl_level=trade.entry_price)
                            trade.sl_level = trade.entry_price
                            self._trailing_sl_triggers += 1
                            logger.info("trailing_sl_breakeven",
                                        trade_id=trade.trade_id[-8:],
                                        old_sl=round(prev_sl, 4),
                                        new_sl=round(trade.entry_price, 4),
                                        current=round(current_price, 3))
                else:  # BUY_NO: TP is lower YES price, SL is higher YES price
                    tp_distance = trade.entry_price - trade.tp_level
                    price_progress = trade.entry_price - current_price
                    if tp_distance > 0 and price_progress >= TRAILING_SL_TRIGGER * tp_distance:
                        if trade.sl_level > trade.entry_price:
                            prev_sl = trade.sl_level
                            from database.trades import update_trade
                            update_trade(self._engine._db, trade.trade_id, sl_level=trade.entry_price)
                            trade.sl_level = trade.entry_price
                            self._trailing_sl_triggers += 1
                            logger.info("trailing_sl_breakeven",
                                        trade_id=trade.trade_id[-8:],
                                        old_sl=round(prev_sl, 4),
                                        new_sl=round(trade.entry_price, 4),
                                        current=round(current_price, 3))

            reason = None
            exit_price = current_price  # default: market sell at current midpoint

            if trade.action == "BUY_YES":
                if has_tp and current_price >= trade.tp_level:
                    reason = "take_profit"
                    exit_price = trade.tp_level
                elif has_sl and current_price <= trade.sl_level:
                    reason = "stop_loss"
                    # SL slippage: taker market sell fills worse than midpoint
                    exit_price = current_price - SL_SLIPPAGE_CENTS
            else:  # BUY_NO
                if has_tp and current_price <= trade.tp_level:
                    reason = "take_profit"
                    exit_price = trade.tp_level  # Limit sell at TP
                elif has_sl and current_price >= trade.sl_level:
                    reason = "stop_loss"
                    # SL slippage: YES price rises further (bad for NO)
                    exit_price = current_price + SL_SLIPPAGE_CENTS

            # Max hold timeout — exit regardless of P&L
            if not reason:
                from config.constants import MAX_HOLD_SECONDS
                if trade.created_at:
                    created = trade.created_at
                    if not created.tzinfo:
                        created = created.replace(tzinfo=timezone.utc)
                    hold_secs = (datetime.now(timezone.utc) - created).total_seconds()
                    if hold_secs >= MAX_HOLD_SECONDS:
                        reason = "timeout"
                        exit_price = current_price

            if reason:
                logger.info(
                    "fast_monitor_exit",
                    trade_id=trade.trade_id[-8:],
                    asset=trade.asset,
                    timeframe=trade.timeframe,
                    action=trade.action,
                    entry=round(trade.entry_price, 3),
                    current=round(current_price, 3),
                    exit_at=round(exit_price, 3),
                    reason=reason,
                    tp=trade.tp_level,
                    sl=trade.sl_level,
                )
                exits.append({
                    "trade_id": trade.trade_id,
                    "current_price": exit_price,
                    "reason": reason,
                })

        if skipped_no_token or skipped_no_price:
            logger.info(
                "fast_monitor_skips",
                total_short=len(short_term),
                no_token=skipped_no_token,
                no_price=skipped_no_price,
                checked=len(short_term) - skipped_no_token - skipped_no_price,
                cached_tokens=len(self._trade_tokens),
            )

        # Build trade_id -> market_title lookup for exit recording
        trade_titles = {t.trade_id: (t.market_title or "") for t in short_term}

        # Execute exits
        exited = 0
        for exit_sig in exits:
            try:
                result = await self._engine.execute_sell(
                    exit_sig["trade_id"],
                    exit_sig["current_price"],
                    exit_sig["reason"],
                )
                if result:
                    exited += 1
                    self._trade_tokens.pop(exit_sig["trade_id"], None)
                    self._no_price_cycles.pop(exit_sig["trade_id"], None)

                    # Record exit reason for re-entry safety tracking
                    exit_title = trade_titles.get(exit_sig["trade_id"], "")
                    if exit_title:
                        if exit_title not in self._market_exits:
                            self._market_exits[exit_title] = []
                        self._market_exits[exit_title].append(
                            (exit_sig["reason"], datetime.now(timezone.utc))
                        )
                        logger.info(
                            "fast_exit_recorded_for_reentry",
                            title=exit_title[:60],
                            reason=exit_sig["reason"],
                            total_exits=len(self._market_exits[exit_title]),
                        )
            except Exception as exc:
                logger.error("fast_monitor_exit_error", error=str(exc))

        return exited
