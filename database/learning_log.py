"""Learning event storage — logs all learning engine decisions and parameter changes."""

import json
from datetime import datetime

import structlog
from sqlalchemy.orm import Session

from database.models import LearningEvent

logger = structlog.get_logger(__name__)


def log_event(
    session: Session,
    event_type: str,
    model_name: str | None = None,
    timeframe: str | None = None,
    details: dict | None = None,
    param_before: dict | None = None,
    param_after: dict | None = None,
) -> LearningEvent:
    """Log a learning engine event.

    event_type examples: "param_mutation", "model_retired", "model_promoted",
    "sl_updated", "tp_updated", "recalibration", "weight_update", "model_warning",
    "model_critical"
    """
    event = LearningEvent(
        event_type=event_type,
        model_name=model_name,
        timeframe=timeframe,
        details_json=json.dumps(details) if details else None,
        param_before_json=json.dumps(param_before) if param_before else None,
        param_after_json=json.dumps(param_after) if param_after else None,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    logger.info(
        "learning_event_logged",
        event_type=event_type,
        model_name=model_name,
        timeframe=timeframe,
    )
    return event


def get_events_since(session: Session, dt: datetime) -> list[LearningEvent]:
    """Get all learning events since a given datetime."""
    return (
        session.query(LearningEvent)
        .filter(LearningEvent.created_at >= dt)
        .order_by(LearningEvent.created_at)
        .all()
    )


def get_events_by_type(session: Session, event_type: str, limit: int = 50) -> list[LearningEvent]:
    """Get learning events filtered by type."""
    return (
        session.query(LearningEvent)
        .filter(LearningEvent.event_type == event_type)
        .order_by(LearningEvent.created_at.desc())
        .limit(limit)
        .all()
    )


def get_model_events(session: Session, model_name: str, limit: int = 50) -> list[LearningEvent]:
    """Get all learning events for a specific model."""
    return (
        session.query(LearningEvent)
        .filter(LearningEvent.model_name == model_name)
        .order_by(LearningEvent.created_at.desc())
        .limit(limit)
        .all()
    )
