"""PolyQuant entry point — initialize all components and start the main loop.

Usage:
    python scripts/run_bot.py

Initializes:
1. Settings from .env
2. Database (SQLite WAL or PostgreSQL)
3. All 7 quant models with default params
4. Data providers, scanner, order book
5. Ensemble, pricing, risk, position manager
6. Paper/live execution engine
7. Learning engine components
8. Trading pipeline (13-step cycle)
9. Main loop (30s cycles)
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO+
)

logger = structlog.get_logger(__name__)


def build_pipeline():
    """Wire up all components and return a fully initialized TradingPipeline."""
    from config.settings import get_settings
    from config.constants import MODEL_NAMES, DEFAULT_MODEL_WEIGHTS
    from database.models import init_db

    # Models
    from models.base import ModelParams
    from models.param_registry import ParamRegistry, DEFAULT_PARAMS
    from models.momentum_regime import MomentumRegimeModel
    from models.funding_basis import FundingBasisModel
    from models.chain_flow import ChainFlowModel
    from models.vol_surface import VolSurfaceModel
    from models.sentiment import SentimentModel
    from models.tech_confluence import TechConfluenceModel
    from models.clob_signal import CLOBSignalModel
    from models.ensemble import EnsembleAggregator

    # Market
    from market.scanner import PolymarketScanner
    from market.orderbook import OrderBookAnalyzer
    from market.pricing import PricingEngine

    # Execution
    from execution.risk_manager import RiskManager
    from execution.position_manager import PositionManager, DefaultSLTPProvider
    from execution.paper_engine import PaperEngine

    # Learning
    from learning.feedback_db import FeedbackStore
    from learning.regime_detector import RegimeDetector
    from learning.sl_tp_learner import SLTPLearner, LearnedSLTPProvider

    # Orchestrator
    from orchestrator.pipeline import TradingPipeline

    # ── Settings ──
    settings = get_settings()
    logger.info("settings_loaded", mode=settings.MODE, bankroll=settings.BANKROLL_USDC)

    # ── Database ──
    engine, session_factory = init_db(settings.DB_URL)
    db_session = session_factory()
    logger.info("database_initialized", url=settings.DB_URL)

    # ── Param Registry ──
    param_registry = ParamRegistry()
    param_registry.initialize_defaults()

    # ── Models ──
    model_classes = {
        "MomRegime": MomentumRegimeModel,
        "FundBasis": FundingBasisModel,
        "ChainFlow": ChainFlowModel,
        "VolSurf": VolSurfaceModel,
        "SentComp": SentimentModel,
        "TechConf": TechConfluenceModel,
        "CLOBSignal": CLOBSignalModel,
    }

    # Build models with default 1h params (models handle per-timeframe internally)
    models = {}
    for name, cls in model_classes.items():
        default_tf = "1h"
        params = param_registry.get_active_params(name, default_tf)
        models[name] = cls(params)
    logger.info("models_initialized", count=len(models))

    # ── Signal Generator (adapter wrapping all models) ──
    class SignalGenerator:
        """Wraps individual models into the pipeline's expected interface."""

        def __init__(self, model_dict, registry):
            self._models = model_dict
            self._registry = registry

        async def generate_signals(self, asset, timeframe, ohlcv, **kwargs):
            signals = []
            for name, model in self._models.items():
                try:
                    # Update params for this timeframe
                    try:
                        params = self._registry.get_active_params(name, timeframe)
                        model.update_params(params)
                    except KeyError:
                        pass  # Use whatever params model has
                    sig = await model.generate_signal(asset, timeframe, ohlcv, **kwargs)
                    signals.append(sig)
                except Exception as exc:
                    logger.warning("signal_generation_error", model=name, error=str(exc))
            return signals

    signal_gen = SignalGenerator(models, param_registry)

    # ── Binance WebSocket Manager ──
    from data.binance_ws import BinanceWSManager
    ws_manager = BinanceWSManager(
        assets=["BTC", "ETH", "SOL", "XRP"],
        timeframes=["15m", "1h", "4h"],
    )

    # ── Data Provider (adapter wrapping price_feed functions) ──
    class DataProvider:
        """Wraps async data feed functions into the pipeline's expected interface.

        Checks WebSocket buffer first for sub-second data. Falls back to
        REST (Binance httpx → Coinbase ccxt) if WS has no data yet.

        Tracks consecutive feed failures per asset. After MAX_CONSECUTIVE_FAILURES,
        raises FeedHealthError to halt the bot — never trade blind.
        """

        MAX_CONSECUTIVE_FAILURES = 3

        def __init__(self, api_key="", api_secret="", ws_mgr=None):
            self._api_key = api_key
            self._api_secret = api_secret
            self._ws_mgr = ws_mgr
            self._consecutive_failures: dict[str, int] = {}

        async def get_ohlcv(self, asset, timeframe):
            # Fast path: WebSocket buffer
            if self._ws_mgr and self._ws_mgr.connected:
                ws_df = self._ws_mgr.get_cached_ohlcv(asset, timeframe)
                if ws_df is not None and len(ws_df) >= 10:
                    logger.debug("ohlcv_from_ws", asset=asset, timeframe=timeframe, rows=len(ws_df))
                    self._consecutive_failures[asset] = 0
                    return ws_df

            # Fallback: REST API
            from data.price_feed import get_ohlcv, FeedHealthError
            try:
                result = await get_ohlcv(
                    asset, timeframe, limit=100,
                    api_key=self._api_key, api_secret=self._api_secret,
                )
                self._consecutive_failures[asset] = 0  # Reset on success
                return result
            except Exception as exc:
                count = self._consecutive_failures.get(asset, 0) + 1
                self._consecutive_failures[asset] = count
                logger.error(
                    "data_fetch_error",
                    asset=asset,
                    timeframe=timeframe,
                    consecutive_failures=count,
                    max_allowed=self.MAX_CONSECUTIVE_FAILURES,
                    error=str(exc),
                )
                if count >= self.MAX_CONSECUTIVE_FAILURES:
                    raise FeedHealthError(
                        f"CRITICAL: {asset} price feed failed {count} consecutive times. "
                        f"Binance + Coinbase both down. Halting bot to prevent blind trading."
                    ) from exc
                return None

    data_provider = DataProvider(
        api_key=settings.BINANCE_API_KEY,
        api_secret=settings.BINANCE_API_SECRET,
        ws_mgr=ws_manager,
    )

    # ── Market Components ──
    scanner = PolymarketScanner()
    orderbook = OrderBookAnalyzer()
    pricing = PricingEngine()

    # ── Ensemble ──
    ensemble = EnsembleAggregator()

    # ── Risk Manager ──
    risk_manager = RiskManager(settings)

    # ── Position Manager ──
    feedback_store = FeedbackStore()
    sl_tp_learner = SLTPLearner()
    learned_provider = LearnedSLTPProvider(sl_tp_learner)
    position_manager = PositionManager(sl_tp_provider=learned_provider)

    # ── Execution Engine ──
    if settings.MODE == "live":
        from execution.live_engine import LiveEngine
        exec_engine = LiveEngine(
            db_session=db_session,
            private_key=settings.POLY_PRIVATE_KEY,
            funder_address=settings.POLY_FUNDER_ADDRESS,
            signature_type=settings.POLY_SIGNATURE_TYPE,
            chain_id=settings.POLY_CHAIN_ID,
        )
        logger.info("execution_engine", mode="LIVE")
    else:
        exec_engine = PaperEngine(
            db_session=db_session,
            orderbook_analyzer=orderbook,
        )
        logger.info("execution_engine", mode="PAPER")

    # ── Regime Detector ──
    regime_detector = RegimeDetector()

    # ── Decision Logger (for live dashboard visibility) ──
    from orchestrator.decision_logger import DecisionLogger
    decision_logger = DecisionLogger(session_factory)

    # ── Build Pipeline ──
    pipeline = TradingPipeline(
        regime_detector=regime_detector,
        data_provider=data_provider,
        signal_generator=signal_gen,
        ensemble=ensemble,
        scanner=scanner,
        orderbook=orderbook,
        pricing_engine=pricing,
        risk_manager=risk_manager,
        position_manager=position_manager,
        execution_engine=exec_engine,
        feedback_store=feedback_store,
        decision_logger=decision_logger,
    )

    logger.info("pipeline_built", mode=settings.MODE)
    return pipeline, settings, ws_manager


async def main():
    """Entry point — build pipeline and start main loop."""
    from orchestrator.main_loop import MainLoop
    from data.price_feed import check_all_feeds, FeedHealthError

    pipeline, settings, ws_manager = build_pipeline()

    # ── Startup Health Check — verify ALL price feeds work before trading ──
    print("\n  Checking price feeds...")
    try:
        feed_status = await check_all_feeds()
        print(f"  All feeds OK: {list(feed_status.keys())}")
    except FeedHealthError as exc:
        logger.critical("startup_feed_check_failed", error=str(exc))
        print(f"\n  FATAL: {exc}")
        print("  Bot will NOT start. Fix Binance/Coinbase connectivity first.")
        return

    loop = MainLoop(
        pipeline=pipeline,
        cycle_interval=30,
        timeframes=["15m", "1h", "4h"],  # All 3 tiers: 15m (maker), 1h (free), 4h (free)
        ws_manager=ws_manager,
    )

    logger.info(
        "bot_starting",
        mode=settings.MODE,
        bankroll=settings.BANKROLL_USDC,
        edge_threshold=settings.MIN_EDGE_THRESHOLD,
    )

    print(f"\n{'='*60}")
    print(f"  PolyQuant — {settings.MODE.upper()} MODE")
    print(f"  Bankroll: ${settings.BANKROLL_USDC:,.0f}")
    print(f"  Edge threshold: {settings.MIN_EDGE_THRESHOLD:.0%}")
    print(f"  Cycle interval: 30s")
    print(f"  WebSocket: Binance klines + trades")
    print(f"  Dashboard: streamlit run dashboard/app.py")
    print(f"{'='*60}\n")

    await loop.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete.")
