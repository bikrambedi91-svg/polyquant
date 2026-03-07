"""Tests for database/learning_log.py — Learning event storage and retrieval."""

import json
from datetime import datetime, timezone, timedelta

import pytest

from database.models import init_db
from database.learning_log import (
    log_event,
    get_events_since,
    get_events_by_type,
    get_model_events,
)


@pytest.fixture
def db_session():
    engine, SessionFactory = init_db("sqlite:///:memory:")
    session = SessionFactory()
    yield session
    session.close()


class TestLogEvent:
    def test_log_basic_event(self, db_session):
        event = log_event(
            db_session,
            event_type="recalibration",
            details={"cycle": 1, "trades_analyzed": 50},
        )
        assert event.id is not None
        assert event.event_type == "recalibration"
        assert event.created_at is not None
        details = json.loads(event.details_json)
        assert details["cycle"] == 1

    def test_log_param_mutation(self, db_session):
        event = log_event(
            db_session,
            event_type="param_mutation",
            model_name="MomRegime",
            timeframe="5m",
            details={"reason": "Brier > 0.28", "brier_score": 0.30},
            param_before={"adx_period": 14, "ema_fast": 20},
            param_after={"adx_period": 12, "ema_fast": 18},
        )
        assert event.model_name == "MomRegime"
        assert event.timeframe == "5m"

        before = json.loads(event.param_before_json)
        after = json.loads(event.param_after_json)
        assert before["adx_period"] == 14
        assert after["adx_period"] == 12

    def test_log_model_retired(self, db_session):
        event = log_event(
            db_session,
            event_type="model_retired",
            model_name="ChainFlow",
            timeframe="4h",
            details={"reason": "Brier > 0.35 for 2 cycles", "final_brier": 0.38},
        )
        assert event.event_type == "model_retired"

    def test_log_without_optional_fields(self, db_session):
        event = log_event(db_session, event_type="system_start")
        assert event.model_name is None
        assert event.details_json is None
        assert event.param_before_json is None


class TestGetEventsSince:
    def test_returns_events_after_datetime(self, db_session):
        before = datetime.now(timezone.utc) - timedelta(seconds=1)
        log_event(db_session, event_type="recalibration")
        events = get_events_since(db_session, before)
        assert len(events) == 1

    def test_empty_when_no_events(self, db_session):
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        events = get_events_since(db_session, future)
        assert len(events) == 0


class TestGetEventsByType:
    def test_filter_by_type(self, db_session):
        log_event(db_session, event_type="param_mutation", model_name="MomRegime")
        log_event(db_session, event_type="recalibration")
        log_event(db_session, event_type="param_mutation", model_name="TechConf")

        mutations = get_events_by_type(db_session, "param_mutation")
        assert len(mutations) == 2
        for e in mutations:
            assert e.event_type == "param_mutation"

    def test_respects_limit(self, db_session):
        for i in range(10):
            log_event(db_session, event_type="recalibration")

        events = get_events_by_type(db_session, "recalibration", limit=3)
        assert len(events) == 3


class TestGetModelEvents:
    def test_filter_by_model(self, db_session):
        log_event(db_session, event_type="param_mutation", model_name="MomRegime")
        log_event(db_session, event_type="model_warning", model_name="MomRegime")
        log_event(db_session, event_type="param_mutation", model_name="TechConf")

        events = get_model_events(db_session, "MomRegime")
        assert len(events) == 2
        for e in events:
            assert e.model_name == "MomRegime"

    def test_empty_for_unknown_model(self, db_session):
        events = get_model_events(db_session, "NonexistentModel")
        assert len(events) == 0
