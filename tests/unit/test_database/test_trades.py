"""Tests for database/trades.py — Full CRUD on SQLite with WAL mode."""

import os
import uuid
import tempfile
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import text

from database.models import init_db, Trade
from database.trades import (
    create_trade,
    update_trade,
    get_trade,
    get_active_trades,
    get_trade_history,
    get_trades_since,
    get_daily_pnl,
    count_trades,
)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite DB and return a session."""
    engine, SessionFactory = init_db("sqlite:///:memory:")
    session = SessionFactory()
    yield session
    session.close()


@pytest.fixture
def sample_trade_kwargs():
    """Minimal required kwargs for creating a trade."""
    return {
        "trade_id": str(uuid.uuid4()),
        "asset": "BTC",
        "timeframe": "5m",
        "action": "BUY_YES",
        "entry_price": 0.55,
        "size_usd": 100.0,
        "your_prob": 0.65,
        "market_implied": 0.55,
        "edge_at_entry": 0.10,
        "confidence": 70,
        "tp_level": 0.70,
        "sl_level": 0.47,
        "regime_at_entry": "TRENDING",
    }


class TestCreateTrade:
    def test_create_trade_basic(self, db_session, sample_trade_kwargs):
        trade = create_trade(db_session, **sample_trade_kwargs)
        assert trade.id is not None
        assert trade.trade_id == sample_trade_kwargs["trade_id"]
        assert trade.asset == "BTC"
        assert trade.status == "ACTIVE"

    def test_create_trade_defaults(self, db_session, sample_trade_kwargs):
        trade = create_trade(db_session, **sample_trade_kwargs)
        assert trade.was_sl_learned is False
        assert trade.taker_fee_paid == 0.0
        assert trade.market_type == "up_down"
        assert trade.created_at is not None

    def test_create_trade_unique_trade_id(self, db_session, sample_trade_kwargs):
        create_trade(db_session, **sample_trade_kwargs)
        with pytest.raises(Exception):
            create_trade(db_session, **sample_trade_kwargs)


class TestUpdateTrade:
    def test_update_trade_fields(self, db_session, sample_trade_kwargs):
        trade = create_trade(db_session, **sample_trade_kwargs)
        now = datetime.now(timezone.utc)
        updated = update_trade(
            db_session,
            trade.trade_id,
            exit_price=0.70,
            pnl_usd=15.0,
            result="WON",
            status="CLOSED",
            exit_reason="take_profit",
            resolved_at=now,
        )
        assert updated is not None
        assert updated.exit_price == 0.70
        assert updated.pnl_usd == 15.0
        assert updated.result == "WON"
        assert updated.status == "CLOSED"

    def test_update_nonexistent_returns_none(self, db_session):
        result = update_trade(db_session, "nonexistent_id", status="CLOSED")
        assert result is None


class TestGetTrade:
    def test_get_existing_trade(self, db_session, sample_trade_kwargs):
        created = create_trade(db_session, **sample_trade_kwargs)
        found = get_trade(db_session, created.trade_id)
        assert found is not None
        assert found.trade_id == created.trade_id

    def test_get_nonexistent_returns_none(self, db_session):
        assert get_trade(db_session, "no_such_id") is None


class TestGetActiveTrades:
    def test_returns_only_active(self, db_session, sample_trade_kwargs):
        # Active trade
        create_trade(db_session, **sample_trade_kwargs)
        # Closed trade
        kwargs2 = {**sample_trade_kwargs, "trade_id": str(uuid.uuid4()), "status": "CLOSED"}
        create_trade(db_session, **kwargs2)

        active = get_active_trades(db_session)
        assert len(active) == 1
        assert active[0].status == "ACTIVE"


class TestGetTradeHistory:
    def test_history_filter_by_asset(self, db_session, sample_trade_kwargs):
        # BTC closed trade
        kwargs1 = {**sample_trade_kwargs, "trade_id": str(uuid.uuid4()), "status": "CLOSED", "result": "WON"}
        create_trade(db_session, **kwargs1)
        # ETH closed trade
        kwargs2 = {**sample_trade_kwargs, "trade_id": str(uuid.uuid4()), "asset": "ETH", "status": "CLOSED", "result": "LOST"}
        create_trade(db_session, **kwargs2)

        btc_history = get_trade_history(db_session, asset="BTC")
        assert len(btc_history) == 1
        assert btc_history[0].asset == "BTC"

    def test_history_filter_by_result(self, db_session, sample_trade_kwargs):
        kwargs1 = {**sample_trade_kwargs, "trade_id": str(uuid.uuid4()), "status": "CLOSED", "result": "WON"}
        create_trade(db_session, **kwargs1)
        kwargs2 = {**sample_trade_kwargs, "trade_id": str(uuid.uuid4()), "status": "CLOSED", "result": "LOST"}
        create_trade(db_session, **kwargs2)

        won = get_trade_history(db_session, result="WON")
        assert len(won) == 1

    def test_history_excludes_active(self, db_session, sample_trade_kwargs):
        create_trade(db_session, **sample_trade_kwargs)  # ACTIVE
        history = get_trade_history(db_session)
        assert len(history) == 0


class TestGetTradesSince:
    def test_returns_trades_after_datetime(self, db_session, sample_trade_kwargs):
        before = datetime.now(timezone.utc) - timedelta(seconds=1)
        create_trade(db_session, **sample_trade_kwargs)
        trades = get_trades_since(db_session, before)
        assert len(trades) == 1


class TestGetDailyPnl:
    def test_daily_pnl_sums_correctly(self, db_session, sample_trade_kwargs):
        now = datetime.now(timezone.utc)
        for i, pnl in enumerate([10.0, -3.0, 5.0]):
            kwargs = {
                **sample_trade_kwargs,
                "trade_id": str(uuid.uuid4()),
                "status": "CLOSED",
                "result": "WON" if pnl > 0 else "LOST",
                "pnl_usd": pnl,
                "resolved_at": now,
            }
            create_trade(db_session, **kwargs)

        total = get_daily_pnl(db_session, now)
        assert total == pytest.approx(12.0)

    def test_daily_pnl_no_trades(self, db_session):
        total = get_daily_pnl(db_session)
        assert total == 0.0


class TestCountTrades:
    def test_count_all(self, db_session, sample_trade_kwargs):
        create_trade(db_session, **sample_trade_kwargs)
        assert count_trades(db_session) == 1

    def test_count_by_status(self, db_session, sample_trade_kwargs):
        create_trade(db_session, **sample_trade_kwargs)
        kwargs2 = {**sample_trade_kwargs, "trade_id": str(uuid.uuid4()), "status": "CLOSED"}
        create_trade(db_session, **kwargs2)

        assert count_trades(db_session, status="ACTIVE") == 1
        assert count_trades(db_session, status="CLOSED") == 1


class TestWALMode:
    def test_sqlite_wal_mode_enabled(self, tmp_path):
        """Verify WAL mode is set on a file-based SQLite connection.

        NOTE: In-memory SQLite does not support WAL; we need a real file.
        """
        db_file = tmp_path / "test_wal.db"
        db_url = f"sqlite:///{db_file}"
        engine, SessionFactory = init_db(db_url)
        session = SessionFactory()
        try:
            result = session.execute(text("PRAGMA journal_mode")).scalar()
            assert result == "wal"
        finally:
            session.close()
