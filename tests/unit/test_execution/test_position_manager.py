"""Tests for execution/position_manager.py — percentage-based TP/SL, regime adjustments, liquidity checks."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock

from execution.position_manager import (
    PositionManager,
    DefaultSLTPProvider,
    TPSLLevels,
    ExitSignal,
)


@pytest.fixture
def pm():
    return PositionManager()


class TestDefaultSLTPProvider:
    def test_buy_yes_flat_tp_sl(self):
        """BUY_YES: flat 10% SL, 20% TP regardless of confidence."""
        provider = DefaultSLTPProvider()
        levels = provider.get_levels("BTC", "1h", "RISK_ON", 0.50, 0.65, "BUY_YES", confidence=65)
        # SL = 0.50 * 0.90 = 0.45  (10% SL)
        assert levels.sl_price == pytest.approx(0.45, abs=0.001)
        # TP = 0.50 * 1.20 = 0.60  (20% TP)
        assert levels.tp_price == pytest.approx(0.60, abs=0.001)
        assert levels.was_learned is False

    def test_buy_yes_same_at_all_confidence(self):
        """Flat TP/SL: same values regardless of confidence level."""
        provider = DefaultSLTPProvider()
        low = provider.get_levels("BTC", "1h", "RISK_ON", 0.50, 0.65, "BUY_YES", confidence=65)
        mid = provider.get_levels("BTC", "1h", "RISK_ON", 0.50, 0.65, "BUY_YES", confidence=80)
        high = provider.get_levels("BTC", "1h", "RISK_ON", 0.50, 0.65, "BUY_YES", confidence=90)
        # All confidence levels → same TP/SL
        assert low.tp_price == pytest.approx(mid.tp_price, abs=0.001)
        assert mid.tp_price == pytest.approx(high.tp_price, abs=0.001)
        assert low.sl_price == pytest.approx(mid.sl_price, abs=0.001)

    def test_buy_no_levels_reversed(self):
        """BUY_NO: TP = entry - tp_pct*(1-entry), SL = entry + sl_pct*(1-entry)."""
        provider = DefaultSLTPProvider()
        levels = provider.get_levels("BTC", "1h", "RISK_ON", 0.45, 0.35, "BUY_NO", confidence=65)
        # no_cost = 1-0.45 = 0.55
        # TP = 0.45 - 0.20*0.55 = 0.45 - 0.110 = 0.340  (20% flat TP)
        assert levels.tp_price == pytest.approx(0.340, abs=0.001)
        # SL = 0.45 + 0.10*0.55 = 0.45 + 0.055 = 0.505  (10% flat SL)
        assert levels.sl_price == pytest.approx(0.505, abs=0.001)

    def test_no_regime_adjustments(self):
        """Flat TP/SL: regime has NO effect — all regimes return same values."""
        provider = DefaultSLTPProvider()
        risk_on = provider.get_levels("BTC", "1h", "RISK_ON", 0.50, 0.65, "BUY_YES", confidence=65)
        risk_off = provider.get_levels("BTC", "1h", "RISK_OFF", 0.50, 0.65, "BUY_YES", confidence=65)
        high_vol = provider.get_levels("BTC", "1h", "HIGH_VOL", 0.50, 0.65, "BUY_YES", confidence=65)
        trending = provider.get_levels("BTC", "1h", "TRENDING", 0.50, 0.65, "BUY_YES", confidence=65)
        # All regimes → identical TP/SL
        for regime_levels in [risk_off, high_vol, trending]:
            assert regime_levels.sl_price == pytest.approx(risk_on.sl_price, abs=0.001)
            assert regime_levels.tp_price == pytest.approx(risk_on.tp_price, abs=0.001)

    def test_tp_capped_at_95(self):
        """TP should not exceed 0.95."""
        provider = DefaultSLTPProvider()
        levels = provider.get_levels("BTC", "1h", "RISK_ON", 0.90, 0.92, "BUY_YES", confidence=90)
        assert levels.tp_price <= 0.95

    def test_sl_floored_at_01(self):
        """SL should not go below 0.01."""
        provider = DefaultSLTPProvider()
        levels = provider.get_levels("BTC", "4h", "RISK_ON", 0.05, 0.20, "BUY_YES", confidence=65)
        assert levels.sl_price >= 0.01

    def test_same_sl_across_timeframes(self):
        """Percentage-based SL is the same regardless of timeframe."""
        provider = DefaultSLTPProvider()
        lev_15m = provider.get_levels("BTC", "15m", "RISK_ON", 0.50, 0.60, "BUY_YES", confidence=65)
        lev_4h = provider.get_levels("BTC", "4h", "RISK_ON", 0.50, 0.60, "BUY_YES", confidence=65)
        assert lev_15m.sl_price == pytest.approx(lev_4h.sl_price, abs=0.001)

    def test_default_confidence_flat_tp(self):
        """Default confidence → flat 20% TP."""
        provider = DefaultSLTPProvider()
        levels = provider.get_levels("BTC", "1h", "RISK_ON", 0.50, 0.60, "BUY_YES")
        # tp_pct=0.20 → TP = 0.50*1.20 = 0.60
        assert levels.tp_price == pytest.approx(0.60, abs=0.001)


class TestPositionManagerTPSL:
    def test_calculate_tp_sl_with_confidence(self, pm):
        levels = pm.calculate_tp_sl("BTC", "1h", "RISK_ON", 0.50, 0.65, "BUY_YES", confidence=80)
        assert isinstance(levels, TPSLLevels)
        # Flat 20% TP → 0.50*1.20 = 0.60 (confidence ignored)
        assert levels.tp_price == pytest.approx(0.60, abs=0.001)
        assert levels.sl_price < 0.50


class TestMonitorPositions:
    @pytest.mark.asyncio
    async def test_tp_triggered(self, pm):
        """Price above TP → exit signal with take_profit."""
        positions = [{
            "trade_id": "TRD-1",
            "token_id_yes": "TOK_1",
            "action": "BUY_YES",
            "entry_price": 0.55,
            "size_usd": 100,
            "tp_level": 0.70,
            "sl_level": 0.43,
            "our_prob": 0.65,
            "max_adverse_excursion": 0.0,
            "max_favorable_excursion": 0.0,
        }]

        async def get_price(token_id):
            return 0.72  # Above TP

        async def get_depth(token_id, size):
            return 500.0  # Enough liquidity

        signals = await pm.monitor_positions(positions, get_price, get_depth)
        assert len(signals) == 1
        assert signals[0].reason == "take_profit"
        assert signals[0].trade_id == "TRD-1"

    @pytest.mark.asyncio
    async def test_sl_triggered(self, pm):
        """Price below SL → stop_loss signal."""
        positions = [{
            "trade_id": "TRD-2",
            "token_id_yes": "TOK_2",
            "action": "BUY_YES",
            "entry_price": 0.55,
            "size_usd": 100,
            "tp_level": 0.70,
            "sl_level": 0.43,
            "our_prob": 0.65,
            "max_adverse_excursion": 0.0,
            "max_favorable_excursion": 0.0,
        }]

        async def get_price(token_id):
            return 0.40  # Below SL

        async def get_depth(token_id, size):
            return 500.0

        signals = await pm.monitor_positions(positions, get_price, get_depth)
        assert len(signals) == 1
        assert signals[0].reason == "stop_loss"

    @pytest.mark.asyncio
    async def test_no_trigger_between_levels(self, pm):
        """Price between SL and TP → no signal."""
        positions = [{
            "trade_id": "TRD-3",
            "token_id_yes": "TOK_3",
            "action": "BUY_YES",
            "entry_price": 0.55,
            "size_usd": 100,
            "tp_level": 0.70,
            "sl_level": 0.43,
            "our_prob": 0.65,
            "max_adverse_excursion": 0.0,
            "max_favorable_excursion": 0.0,
        }]

        async def get_price(token_id):
            return 0.58  # Between SL and TP

        async def get_depth(token_id, size):
            return 500.0

        signals = await pm.monitor_positions(positions, get_price, get_depth)
        assert len(signals) == 0

    @pytest.mark.asyncio
    async def test_insufficient_liquidity_skips_exit(self, pm):
        """TP triggered but insufficient depth → exit skipped."""
        positions = [{
            "trade_id": "TRD-4",
            "token_id_yes": "TOK_4",
            "action": "BUY_YES",
            "entry_price": 0.55,
            "size_usd": 500,
            "tp_level": 0.70,
            "sl_level": 0.43,
            "our_prob": 0.65,
            "max_adverse_excursion": 0.0,
            "max_favorable_excursion": 0.0,
        }]

        async def get_price(token_id):
            return 0.75  # Above TP

        async def get_depth(token_id, size):
            return 100.0  # Only $100 available, need $500

        signals = await pm.monitor_positions(positions, get_price, get_depth)
        assert len(signals) == 0  # Exit skipped due to no liquidity

    @pytest.mark.asyncio
    async def test_excursion_tracking_updates(self, pm):
        """MAE and MFE should be updated on each price check."""
        pos = {
            "trade_id": "TRD-5",
            "token_id_yes": "TOK_5",
            "action": "BUY_YES",
            "entry_price": 0.55,
            "size_usd": 100,
            "tp_level": 0.90,
            "sl_level": 0.10,
            "our_prob": 0.65,
            "max_adverse_excursion": 0.0,
            "max_favorable_excursion": 0.0,
        }

        async def get_price(token_id):
            return 0.60  # 5 cents above entry

        async def get_depth(token_id, size):
            return 500.0

        await pm.monitor_positions([pos], get_price, get_depth)

        assert pos["max_favorable_excursion"] == pytest.approx(0.05)
        assert pos["max_adverse_excursion"] == 0.0  # No adverse

    @pytest.mark.asyncio
    async def test_adverse_excursion_tracked(self, pm):
        """When price drops below entry, MAE is updated."""
        pos = {
            "trade_id": "TRD-6",
            "token_id_yes": "TOK_6",
            "action": "BUY_YES",
            "entry_price": 0.55,
            "size_usd": 100,
            "tp_level": 0.90,
            "sl_level": 0.10,
            "our_prob": 0.65,
            "max_adverse_excursion": 0.0,
            "max_favorable_excursion": 0.0,
        }

        async def get_price(token_id):
            return 0.50  # 5 cents below entry

        async def get_depth(token_id, size):
            return 500.0

        await pm.monitor_positions([pos], get_price, get_depth)

        assert pos["max_adverse_excursion"] == pytest.approx(0.05)
        assert pos["max_favorable_excursion"] == 0.0

    @pytest.mark.asyncio
    async def test_time_decay_exit(self, pm):
        """When < 5% time remaining → time_decay exit."""
        end_time = datetime.now(timezone.utc) + timedelta(seconds=10)  # Almost expired
        pos = {
            "trade_id": "TRD-7",
            "token_id_yes": "TOK_7",
            "action": "BUY_YES",
            "entry_price": 0.55,
            "size_usd": 100,
            "tp_level": 0.90,
            "sl_level": 0.10,
            "our_prob": 0.65,
            "max_adverse_excursion": 0.0,
            "max_favorable_excursion": 0.0,
            "end_datetime": end_time.isoformat(),
            "total_duration_seconds": 300,
        }

        async def get_price(token_id):
            return 0.56  # Between SL and TP

        async def get_depth(token_id, size):
            return 500.0

        signals = await pm.monitor_positions([pos], get_price, get_depth)
        assert len(signals) == 1
        assert signals[0].reason == "time_decay"

    @pytest.mark.asyncio
    async def test_buy_no_tp_triggered(self, pm):
        """BUY_NO: price drops below TP → take_profit."""
        positions = [{
            "trade_id": "TRD-8",
            "token_id_yes": "TOK_8",
            "action": "BUY_NO",
            "entry_price": 0.45,
            "size_usd": 100,
            "tp_level": 0.30,
            "sl_level": 0.57,
            "our_prob": 0.35,
            "max_adverse_excursion": 0.0,
            "max_favorable_excursion": 0.0,
        }]

        async def get_price(token_id):
            return 0.25  # Below TP (YES price falling = good for NO)

        async def get_depth(token_id, size):
            return 500.0

        signals = await pm.monitor_positions(positions, get_price, get_depth)
        assert len(signals) == 1
        assert signals[0].reason == "take_profit"
