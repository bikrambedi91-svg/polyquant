"""Tests for database/signals.py — Signal storage and retrieval."""

from datetime import datetime, timezone, timedelta

import pytest

from database.models import init_db
from database.signals import store_signal, get_latest_signals, get_signals_since


@pytest.fixture
def db_session():
    engine, SessionFactory = init_db("sqlite:///:memory:")
    session = SessionFactory()
    yield session
    session.close()


class TestStoreSignal:
    def test_store_basic(self, db_session):
        sig = store_signal(
            db_session,
            asset="BTC",
            timeframe="5m",
            model_name="MomRegime",
            prob_up=0.62,
            confidence=70,
            param_version=1,
            ensemble_prob=0.58,
        )
        assert sig.id is not None
        assert sig.asset == "BTC"
        assert sig.prob_up == 0.62
        assert sig.confidence == 70
        assert sig.model_name == "MomRegime"
        assert sig.created_at is not None

    def test_store_multiple_models(self, db_session):
        for model in ["MomRegime", "FundBasis", "TechConf"]:
            store_signal(
                db_session,
                asset="ETH",
                timeframe="1h",
                model_name=model,
                prob_up=0.55,
                confidence=60,
            )
        from database.models import Signal
        count = db_session.query(Signal).count()
        assert count == 3


class TestGetLatestSignals:
    def test_returns_latest_per_model(self, db_session):
        # Store two signals for MomRegime — should get the latest
        store_signal(
            db_session,
            asset="BTC",
            timeframe="5m",
            model_name="MomRegime",
            prob_up=0.50,
            confidence=60,
        )
        store_signal(
            db_session,
            asset="BTC",
            timeframe="5m",
            model_name="MomRegime",
            prob_up=0.65,
            confidence=75,
        )
        # Store one for TechConf
        store_signal(
            db_session,
            asset="BTC",
            timeframe="5m",
            model_name="TechConf",
            prob_up=0.70,
            confidence=80,
        )

        signals = get_latest_signals(db_session, "BTC", "5m")
        assert len(signals) == 2
        model_map = {s.model_name: s for s in signals}
        assert model_map["MomRegime"].prob_up == 0.65
        assert model_map["TechConf"].prob_up == 0.70

    def test_empty_for_unknown_asset(self, db_session):
        signals = get_latest_signals(db_session, "DOGE", "5m")
        assert len(signals) == 0

    def test_separate_asset_timeframe(self, db_session):
        store_signal(db_session, asset="BTC", timeframe="5m", model_name="MomRegime", prob_up=0.6, confidence=60)
        store_signal(db_session, asset="BTC", timeframe="1h", model_name="MomRegime", prob_up=0.7, confidence=70)

        signals_5m = get_latest_signals(db_session, "BTC", "5m")
        signals_1h = get_latest_signals(db_session, "BTC", "1h")
        assert len(signals_5m) == 1
        assert len(signals_1h) == 1
        assert signals_5m[0].prob_up == 0.6
        assert signals_1h[0].prob_up == 0.7


class TestGetSignalsSince:
    def test_returns_signals_after_datetime(self, db_session):
        before = datetime.now(timezone.utc) - timedelta(seconds=1)
        store_signal(db_session, asset="BTC", timeframe="5m", model_name="MomRegime", prob_up=0.6, confidence=60)
        signals = get_signals_since(db_session, before)
        assert len(signals) == 1
