"""Tests for execution/paper_engine.py — simulated buy/sell/resolution."""

import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from database.models import init_db
from execution.paper_engine import PaperEngine


@pytest.fixture
def db_session():
    engine, SessionFactory = init_db("sqlite:///:memory:")
    session = SessionFactory()
    yield session
    session.close()


@pytest.fixture
def engine(db_session):
    return PaperEngine(db_session)


@pytest.fixture
def engine_with_ob(db_session):
    """Engine with a mock orderbook analyzer."""
    mock_ob = AsyncMock()
    snap = MagicMock()
    snap.best_ask = 0.57      # Maker entry = best_ask - 0.01 = 0.56
    snap.best_bid = 0.55      # Spread = 0.02 (within 4c limit)
    snap.avg_fill_price = 0.56
    snap.expected_slippage_cents = 0.01
    mock_ob.analyze.return_value = snap
    return PaperEngine(db_session, orderbook_analyzer=mock_ob)


@pytest.fixture
def engine_wide_spread(db_session):
    """Engine with a mock orderbook that has a wide spread (>4c)."""
    mock_ob = AsyncMock()
    snap = MagicMock()
    snap.best_ask = 0.60
    snap.best_bid = 0.54      # Spread = 0.06 > MAX_ENTRY_SPREAD (0.04)
    snap.avg_fill_price = 0.57
    snap.expected_slippage_cents = 0.03
    mock_ob.analyze.return_value = snap
    return PaperEngine(db_session, orderbook_analyzer=mock_ob)


async def _buy(engine, **overrides):
    """Helper to execute a standard buy."""
    defaults = {
        "asset": "BTC",
        "timeframe": "1h",
        "action": "BUY_YES",
        "size_usd": 100.0,
        "our_prob": 0.65,
        "market_implied": 0.55,
        "edge": 0.10,
        "confidence": 70,
        "tp_level": 0.70,
        "sl_level": 0.43,
        "regime": "RISK_ON",
    }
    defaults.update(overrides)
    return await engine.execute_buy(**defaults)


class TestExecuteBuy:
    @pytest.mark.asyncio
    async def test_basic_buy(self, engine):
        result = await _buy(engine)
        assert result is not None
        assert result["trade_id"].startswith("PAPER-")
        assert result["fill_price"] == 0.55

    @pytest.mark.asyncio
    async def test_fee_calculated_1h(self, engine):
        """1h is fee-free → taker_fee_usd should be 0."""
        result = await _buy(engine, timeframe="1h")
        assert result["taker_fee_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_fee_calculated_15m(self, engine):
        """15m uses MAKER-ONLY entry → 0% fee (no taker fee)."""
        result = await _buy(engine, timeframe="15m", market_implied=0.50, size_usd=100)
        # Maker orders have 0% fee
        assert result["taker_fee_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_buy_with_orderbook(self, engine_with_ob):
        """When orderbook available, use maker entry (best_ask - 0.01)."""
        result = await _buy(engine_with_ob, token_id="TOK_1")
        # best_ask=0.57, maker fill = 0.57 - 0.01 = 0.56
        assert result["fill_price"] == pytest.approx(0.56)

    @pytest.mark.asyncio
    async def test_trade_stored_in_db(self, engine, db_session):
        result = await _buy(engine)
        from database.trades import get_trade
        trade = get_trade(db_session, result["trade_id"])
        assert trade is not None
        assert trade.asset == "BTC"
        assert trade.status == "ACTIVE"
        assert trade.action == "BUY_YES"
        assert trade.entry_price == 0.55


class TestExecuteSell:
    @pytest.mark.asyncio
    async def test_sell_win(self, engine):
        """Buy at 0.55, sell at 0.70 → profit."""
        buy_result = await _buy(engine)
        sell_result = await engine.execute_sell(
            buy_result["trade_id"], exit_price=0.70, exit_reason="take_profit",
        )
        assert sell_result is not None
        assert sell_result["result"] == "WON"
        # PnL = (0.70 - 0.55) * shares, shares = 100/0.55 = 181.818
        # = 0.15 * 181.818 = 27.27 (1h is fee-free)
        assert sell_result["pnl_usd"] == pytest.approx(27.27, abs=0.01)

    @pytest.mark.asyncio
    async def test_sell_loss(self, engine):
        """Buy at 0.55, sell at 0.43 → loss."""
        buy_result = await _buy(engine)
        sell_result = await engine.execute_sell(
            buy_result["trade_id"], exit_price=0.43, exit_reason="stop_loss",
        )
        assert sell_result["result"] == "LOST"
        assert sell_result["pnl_usd"] < 0

    @pytest.mark.asyncio
    async def test_sell_updates_db(self, engine, db_session):
        buy_result = await _buy(engine)
        await engine.execute_sell(buy_result["trade_id"], 0.70, "take_profit")
        from database.trades import get_trade
        trade = get_trade(db_session, buy_result["trade_id"])
        assert trade.status == "CLOSED"
        assert trade.exit_reason == "take_profit"
        assert trade.exit_price == 0.70

    @pytest.mark.asyncio
    async def test_sell_nonexistent_returns_none(self, engine):
        result = await engine.execute_sell("NONEXISTENT", 0.50, "manual")
        assert result is None

    @pytest.mark.asyncio
    async def test_sell_tp_maker_zero_fee(self, engine):
        """TP exit is a maker limit sell → 0% fee."""
        buy_result = await _buy(engine, timeframe="15m", market_implied=0.50, size_usd=100)
        sell_result = await engine.execute_sell(
            buy_result["trade_id"], exit_price=0.60, exit_reason="take_profit",
        )
        # shares = 100/0.50 = 200
        # Gross PnL: (0.60 - 0.50) * 200 = $20
        # Exit fee: $0 (maker TP limit sell)
        # Net PnL: $20
        assert sell_result["pnl_usd"] == pytest.approx(20.00, abs=0.01)

    @pytest.mark.asyncio
    async def test_sell_sl_taker_fee(self, engine):
        """SL exit is a taker market sell → 1.56% max fee applies."""
        buy_result = await _buy(engine, timeframe="1h", market_implied=0.50, size_usd=100)
        sell_result = await engine.execute_sell(
            buy_result["trade_id"], exit_price=0.43, exit_reason="stop_loss",
        )
        # shares = 100/0.50 = 200
        # Gross PnL: (0.43 - 0.50) * 200 = -$14.00
        # SL taker fee: 0.0156 * 2 * 0.43 * 0.57 * 100 = $0.765
        # Net PnL: -$14.00 - $0.765 = -$14.765
        assert sell_result["pnl_usd"] == pytest.approx(-14.765, abs=0.01)
        assert sell_result["result"] == "LOST"


class TestCheckResolution:
    @pytest.mark.asyncio
    async def test_active_trade_resolved_up_buy_yes_wins(self, engine):
        """Active BUY_YES, resolved UP → WON."""
        buy = await _buy(engine)
        res = await engine.check_resolution(buy["trade_id"], resolved_up=True)
        assert res["result"] == "WON"
        assert res["would_have_won_if_held"] is True
        assert res["pnl_usd"] > 0

    @pytest.mark.asyncio
    async def test_active_trade_resolved_down_buy_yes_loses(self, engine):
        """Active BUY_YES, resolved DOWN → LOST."""
        buy = await _buy(engine)
        res = await engine.check_resolution(buy["trade_id"], resolved_up=False)
        assert res["result"] == "LOST"
        assert res["pnl_usd"] < 0

    @pytest.mark.asyncio
    async def test_already_closed_retroactive_flag(self, engine):
        """Trade closed by TP, then resolved → would_have_won_if_held set."""
        buy = await _buy(engine)
        await engine.execute_sell(buy["trade_id"], 0.70, "take_profit")
        res = await engine.check_resolution(buy["trade_id"], resolved_up=True)
        assert res["already_closed"] is True
        assert res["would_have_won_if_held"] is True

    @pytest.mark.asyncio
    async def test_early_sl_exit_would_have_won(self, engine):
        """Trade stopped out, but resolution was favorable → flag True."""
        buy = await _buy(engine)
        await engine.execute_sell(buy["trade_id"], 0.43, "stop_loss")
        res = await engine.check_resolution(buy["trade_id"], resolved_up=True)
        assert res["would_have_won_if_held"] is True
        assert res["original_result"] == "LOST"

    @pytest.mark.asyncio
    async def test_buy_no_resolution(self, engine):
        """BUY_NO, resolved DOWN → WON."""
        buy = await _buy(engine, action="BUY_NO", market_implied=0.45)
        res = await engine.check_resolution(buy["trade_id"], resolved_up=False)
        assert res["result"] == "WON"
        assert res["would_have_won_if_held"] is True

    @pytest.mark.asyncio
    async def test_resolution_updates_db(self, engine, db_session):
        buy = await _buy(engine)
        await engine.check_resolution(buy["trade_id"], resolved_up=True)
        from database.trades import get_trade
        trade = get_trade(db_session, buy["trade_id"])
        assert trade.status == "RESOLVED"
        assert trade.exit_reason == "resolution"
        assert trade.would_have_won_if_held is True

    @pytest.mark.asyncio
    async def test_nonexistent_trade_returns_none(self, engine):
        result = await engine.check_resolution("NOPE", resolved_up=True)
        assert result is None


class TestSpreadFilter:
    @pytest.mark.asyncio
    async def test_wide_spread_rejects_trade(self, engine_wide_spread):
        """Trade rejected when bid-ask spread > MAX_ENTRY_SPREAD (4c)."""
        result = await _buy(engine_wide_spread, token_id="TOK_WIDE")
        assert result is None  # Rejected by spread filter

    @pytest.mark.asyncio
    async def test_narrow_spread_allows_trade(self, engine_with_ob):
        """Trade allowed when bid-ask spread <= MAX_ENTRY_SPREAD (4c)."""
        result = await _buy(engine_with_ob, token_id="TOK_NARROW")
        assert result is not None
        assert result["trade_id"].startswith("PAPER-")

    @pytest.mark.asyncio
    async def test_no_orderbook_still_fills(self, engine):
        """Without orderbook, trade fills at market_implied (no spread check)."""
        result = await _buy(engine)
        assert result is not None
        assert result["fill_price"] == 0.55


class TestSLSlippage:
    @pytest.mark.asyncio
    async def test_sl_exit_includes_taker_fee(self, engine):
        """SL exit has taker fee applied (emergency market sell)."""
        buy = await _buy(engine, timeframe="15m", market_implied=0.50, size_usd=100)
        sell = await engine.execute_sell(buy["trade_id"], 0.43, "stop_loss")
        # SL is a taker exit → fee should be applied
        assert sell["exit_fee_usd"] > 0

    @pytest.mark.asyncio
    async def test_tp_exit_zero_fee(self, engine):
        """TP exit is maker → 0 fee."""
        buy = await _buy(engine, timeframe="15m", market_implied=0.50, size_usd=100)
        sell = await engine.execute_sell(buy["trade_id"], 0.60, "take_profit")
        assert sell["exit_fee_usd"] == 0.0
