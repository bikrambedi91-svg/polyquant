"""Signal storage and retrieval."""

from datetime import datetime, timezone

import structlog
from sqlalchemy.orm import Session

from database.models import Signal

logger = structlog.get_logger(__name__)


def store_signal(session: Session, **kwargs) -> Signal:
    """Store a model signal snapshot.

    Required kwargs: asset, timeframe, model_name, prob_up, confidence
    Optional: param_version, ensemble_prob
    """
    signal = Signal(**kwargs)
    session.add(signal)
    session.commit()
    session.refresh(signal)
    logger.debug(
        "signal_stored",
        asset=signal.asset,
        timeframe=signal.timeframe,
        model=signal.model_name,
        prob_up=signal.prob_up,
    )
    return signal


def get_latest_signals(session: Session, asset: str, timeframe: str) -> list[Signal]:
    """Get the most recent signal for each model for a given asset+timeframe.

    Returns one signal per model_name (the latest by created_at).
    """
    from sqlalchemy import func

    # Subquery: max created_at per model_name for this asset+timeframe
    subq = (
        session.query(
            Signal.model_name,
            func.max(Signal.created_at).label("max_created"),
        )
        .filter(Signal.asset == asset, Signal.timeframe == timeframe)
        .group_by(Signal.model_name)
        .subquery()
    )

    results = (
        session.query(Signal)
        .join(
            subq,
            (Signal.model_name == subq.c.model_name)
            & (Signal.created_at == subq.c.max_created)
            & (Signal.asset == asset)
            & (Signal.timeframe == timeframe),
        )
        .all()
    )
    return results


def get_signals_since(session: Session, dt: datetime) -> list[Signal]:
    """Get all signals created since a given datetime."""
    return session.query(Signal).filter(Signal.created_at >= dt).order_by(Signal.created_at).all()
