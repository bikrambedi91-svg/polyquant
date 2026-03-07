"""Integration tests for orchestrator/pipeline.py — Full 13-step cycle with mocks."""

import pytest
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

from orchestrator.pipeline import TradingPipeline, CycleResult
from models.base import ModelOutput, EnsembleOutput
from market.pricing import PricingEngine
from learning.feedback_db import FeedbackStore
from learning.regime_detector import RegimeDetector, RegimeState

import numpy as np
import pandas as pd


# ── Mock helpers ──

def _make_btc_ohlcv(n=30, trend=0.001):
    np.random.seed(42)
    close = 100.0 * np.cumprod(1 + np.random.normal(trend, 0.005, n))
    return pd.DataFrame({
        "open": close * 0.999, "high": close * 1.005,
        "low": close * 0.995, "close": close,
        "volume": np.random.uniform(100, 1000, n),
    })


@dataclass
class MockMarket:
    title: str = "Will BTC go up in the next 1 hour?"
    url: str = "https://polymarket.com/event/btc-1h"
    token_id_yes: str = "TOK_YES_1"
    token_id_no: str = "TOK_NO_1"
    asset: str = "BTC"
    market_type: str = "up_down"
    timeframe: str = "1h"
    volume: float = 100000
    end_datetime: str = ""
    current_yes_price: float = 0.65
    condition_id: str = "COND_1"
    question: str = "Will BTC go up in the next 1 hour?"


@dataclass
class MockOrderBookSnap:
    avg_fill_price: float = 0.66
    expected_slippage_cents: float = 0.01
    spread: float = 0.02
    midpoint: float = 0.65


class MockDataProvider:
    def __init__(self, ohlcv=None):
        self._ohlcv = ohlcv or _make_btc_ohlcv()

    async def get_ohlcv(self, asset, timeframe):
        return self._ohlcv


class MockSignalGenerator:
    def __init__(self, prob_up=0.30, confidence=75):
        self._prob = prob_up
        self._conf = confidence

    async def generate_signals(self, asset, timeframe, ohlcv, **kwargs):
        # Must provide enough models for the model agreement filter (2+ agree).
        # Models: MomRegime, TechConf, FundBasis all return similar prob_up.
        return [
            ModelOutput(
                asset=asset, timeframe=timeframe,
                prob_up=self._prob, confidence=self._conf,
                model_name="MomRegime", param_version=1,
            ),
            ModelOutput(
                asset=asset, timeframe=timeframe,
                prob_up=self._prob - 0.02, confidence=self._conf - 5,
                model_name="TechConf", param_version=1,
            ),
            ModelOutput(
                asset=asset, timeframe=timeframe,
                prob_up=self._prob - 0.01, confidence=self._conf - 3,
                model_name="FundBasis", param_version=1,
            ),
        ]


class MockScanner:
    def __init__(self, markets=None):
        self._markets = markets

    async def discover_markets(self):
        if self._markets is None:
            return [MockMarket()]
        return self._markets


class MockOrderBook:
    async def analyze(self, token_id, size_usd=100):
        return MockOrderBookSnap()


class MockEngine:
    def __init__(self):
        self.buys = []
        self.sells = []

    async def execute_buy(self, **kwargs):
        self.buys.append(kwargs)
        return {
            "trade_id": f"PAPER-{len(self.buys):04d}",
            "fill_price": kwargs.get("market_implied", 0.65),
            "taker_fee_usd": 0.0,
        }

    async def execute_sell(self, trade_id, exit_price, exit_reason):
        self.sells.append({"trade_id": trade_id, "exit_price": exit_price})
        return {
            "trade_id": trade_id,
            "exit_price": exit_price,
            "pnl_usd": 10.0,
            "result": "WON",
        }


class MockRiskManager:
    def get_position_size(self):
        """Fixed $20 position size."""
        return 20.0

    def check_limits(self, asset, size_usd, active_positions, daily_pnl=0.0, action="", timeframe=""):
        return True, ""


# ── Fixtures ──

@pytest.fixture
def full_pipeline():
    """Pipeline with all dependencies mocked for a full cycle."""
    from models.ensemble import EnsembleAggregator
    from execution.position_manager import PositionManager

    return TradingPipeline(
        regime_detector=RegimeDetector(),
        data_provider=MockDataProvider(),
        signal_generator=MockSignalGenerator(prob_up=0.30, confidence=75),
        ensemble=EnsembleAggregator(),
        scanner=MockScanner(),
        orderbook=MockOrderBook(),
        pricing_engine=PricingEngine(),
        risk_manager=MockRiskManager(),
        position_manager=PositionManager(),
        execution_engine=MockEngine(),
        feedback_store=FeedbackStore(),
    )


@pytest.fixture
def empty_scanner_pipeline():
    """Pipeline where scanner returns empty list."""
    from models.ensemble import EnsembleAggregator

    return TradingPipeline(
        regime_detector=RegimeDetector(),
        data_provider=MockDataProvider(),
        signal_generator=MockSignalGenerator(),
        ensemble=EnsembleAggregator(),
        scanner=MockScanner(markets=[]),
        pricing_engine=PricingEngine(),
        risk_manager=MockRiskManager(),
        execution_engine=MockEngine(),
        feedback_store=FeedbackStore(),
    )


@pytest.fixture
def low_confidence_pipeline():
    """Pipeline where all models return low confidence → HOLD."""
    from models.ensemble import EnsembleAggregator

    return TradingPipeline(
        regime_detector=RegimeDetector(),
        data_provider=MockDataProvider(),
        signal_generator=MockSignalGenerator(prob_up=0.52, confidence=30),
        ensemble=EnsembleAggregator(),
        scanner=MockScanner(),
        orderbook=MockOrderBook(),
        pricing_engine=PricingEngine(),
        risk_manager=MockRiskManager(),
        execution_engine=MockEngine(),
        feedback_store=FeedbackStore(),
    )


# ── Tests ──

class TestFullCycle:
    @pytest.mark.asyncio
    async def test_13_step_cycle_completes(self, full_pipeline):
        """Full cycle with all 13 steps runs without error."""
        result = await full_pipeline.run_cycle(timeframe="1h")
        assert isinstance(result, CycleResult)
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_cycle_discovers_markets(self, full_pipeline):
        result = await full_pipeline.run_cycle(timeframe="1h")
        assert result.markets_found == 1

    @pytest.mark.asyncio
    async def test_cycle_generates_signals(self, full_pipeline):
        result = await full_pipeline.run_cycle(timeframe="1h")
        # Should have signals for BTC (at least; other assets depend on data)
        assert result.signals_generated >= 1

    @pytest.mark.asyncio
    async def test_cycle_opens_trade_when_edge_exists(self, full_pipeline):
        """With prob=0.30 vs market=0.65, BUY_NO edge ~35% (>12%) → trade executed.
        3 models agree bearish (all prob_up < 0.45), conf ≥60, no disagreements."""
        result = await full_pipeline.run_cycle(timeframe="1h")
        # BUY_NO: (1-0.30) - (1-0.65) = 0.70 - 0.35 = 0.35 edge
        # Model agreement: 3 bearish models (0.30, 0.28, 0.29 — all < 0.45)
        assert result.trades_opened >= 1
        assert result.action == "TRADE"

    @pytest.mark.asyncio
    async def test_engine_receives_correct_params(self, full_pipeline):
        await full_pipeline.run_cycle(timeframe="1h")
        engine = full_pipeline._engine
        assert len(engine.buys) >= 1
        buy = engine.buys[0]
        assert buy["asset"] == "BTC"
        assert buy["timeframe"] == "1h"
        assert buy["action"] in ("BUY_YES", "BUY_NO")
        assert buy["size_usd"] > 0

    @pytest.mark.asyncio
    async def test_regime_detected(self, full_pipeline):
        result = await full_pipeline.run_cycle(timeframe="1h")
        assert result.regime in ("RISK_ON", "RISK_OFF", "HIGH_VOL", "TRENDING", "CHOPPY")


class TestEmptyScanner:
    @pytest.mark.asyncio
    async def test_empty_scanner_no_crash(self, empty_scanner_pipeline):
        """Scanner returns [] → no trades, no errors."""
        result = await empty_scanner_pipeline.run_cycle(timeframe="1h")
        assert result.markets_found == 0
        assert result.trades_opened == 0
        assert result.action == "HOLD"
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_empty_scanner_still_monitors_positions(self, empty_scanner_pipeline):
        """Even with no markets, position monitoring should run."""
        result = await empty_scanner_pipeline.run_cycle(timeframe="1h")
        # Should complete without error
        assert len(result.errors) == 0


class TestHoldBehavior:
    @pytest.mark.asyncio
    async def test_low_confidence_hold(self, low_confidence_pipeline):
        """All models conf=30 (< 60 threshold) → HOLD, no trades."""
        result = await low_confidence_pipeline.run_cycle(timeframe="1h")
        assert result.trades_opened == 0
        assert result.action == "HOLD"

    @pytest.mark.asyncio
    async def test_no_edge_hold(self):
        """prob ≈ market_implied → edge < 12% → HOLD."""
        from models.ensemble import EnsembleAggregator

        # With market YES=0.65 and prob_up=0.60, the edge is tiny:
        # BUY_NO edge = (1-0.60) - (1-0.65) = 0.40 - 0.35 = 0.05 (5%, below 12%)
        pipeline = TradingPipeline(
            regime_detector=RegimeDetector(),
            data_provider=MockDataProvider(),
            signal_generator=MockSignalGenerator(prob_up=0.60, confidence=70),
            ensemble=EnsembleAggregator(),
            scanner=MockScanner(),
            orderbook=MockOrderBook(),
            pricing_engine=PricingEngine(),
            risk_manager=MockRiskManager(),
            execution_engine=MockEngine(),
            feedback_store=FeedbackStore(),
        )
        result = await pipeline.run_cycle(timeframe="1h")
        assert result.trades_opened == 0
        assert result.action == "HOLD"


class TestExitExecution:
    @pytest.mark.asyncio
    async def test_exit_on_tp_hit(self):
        """When step 9 returns exit signals, step 10 executes them."""
        from models.ensemble import EnsembleAggregator

        engine = MockEngine()
        pipeline = TradingPipeline(
            data_provider=MockDataProvider(),
            signal_generator=MockSignalGenerator(prob_up=0.52, confidence=30),
            ensemble=EnsembleAggregator(),
            scanner=MockScanner(markets=[]),
            execution_engine=engine,
            feedback_store=FeedbackStore(),
        )

        # Monkey-patch step 9 to return exit signals
        async def mock_monitor():
            return {
                "monitored": [{"trade_id": "T-001"}],
                "exits": [{
                    "trade_id": "T-001",
                    "current_price": 0.70,
                    "reason": "take_profit",
                }],
            }
        pipeline._step_monitor_positions = mock_monitor

        result = await pipeline.run_cycle(timeframe="1h")
        assert result.exits_executed == 1
        assert result.action == "EXIT_ONLY"
        assert len(engine.sells) == 1


class TestErrorResilience:
    @pytest.mark.asyncio
    async def test_scanner_error_doesnt_crash(self):
        """Scanner raises exception → caught, zero markets, no crash."""
        scanner = AsyncMock()
        scanner.discover_markets.side_effect = Exception("API timeout")

        pipeline = TradingPipeline(
            data_provider=MockDataProvider(),
            scanner=scanner,
            execution_engine=MockEngine(),
            feedback_store=FeedbackStore(),
        )
        result = await pipeline.run_cycle(timeframe="1h")
        assert result.markets_found == 0
        assert len(result.errors) == 0  # Error handled internally

    @pytest.mark.asyncio
    async def test_minimal_pipeline_runs(self):
        """Pipeline with no dependencies → completes with HOLD."""
        pipeline = TradingPipeline()
        result = await pipeline.run_cycle(timeframe="1h")
        assert result.action == "HOLD"
        assert len(result.errors) == 0


class TestLearningIntegration:
    @pytest.mark.asyncio
    async def test_cold_start_no_learning(self):
        """< 50 trades → learning dormant."""
        store = FeedbackStore()
        pipeline = TradingPipeline(feedback_store=store)
        # No trades → cold start
        assert store.is_cold_start()
        result = await pipeline.run_cycle()
        assert len(result.errors) == 0
