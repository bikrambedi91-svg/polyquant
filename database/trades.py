"""Trade CRUD operations."""

from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy.orm import Session

from database.models import Trade

logger = structlog.get_logger(__name__)


def create_trade(session: Session, **kwargs) -> Trade:
    """Create a new trade record and commit.

    Required kwargs: trade_id, asset, timeframe, action, entry_price, size_usd
    """
    trade = Trade(**kwargs)
    session.add(trade)
    session.commit()
    session.refresh(trade)
    logger.info("trade_created", trade_id=trade.trade_id, asset=trade.asset, action=trade.action)
    return trade


def update_trade(session: Session, trade_id: str, **kwargs) -> Optional[Trade]:
    """Update a trade by trade_id. Returns the updated trade or None."""
    trade = session.query(Trade).filter(Trade.trade_id == trade_id).first()
    if trade is None:
        logger.warning("trade_not_found", trade_id=trade_id)
        return None
    for key, value in kwargs.items():
        if hasattr(trade, key):
            setattr(trade, key, value)
    session.commit()
    session.refresh(trade)
    logger.info("trade_updated", trade_id=trade_id, fields=list(kwargs.keys()))
    return trade


def get_trade(session: Session, trade_id: str) -> Optional[Trade]:
    """Get a single trade by trade_id."""
    return session.query(Trade).filter(Trade.trade_id == trade_id).first()


def get_active_trades(session: Session) -> list[Trade]:
    """Get all trades with status=ACTIVE."""
    return session.query(Trade).filter(Trade.status == "ACTIVE").all()


def get_trade_history(
    session: Session,
    asset: Optional[str] = None,
    timeframe: Optional[str] = None,
    result: Optional[str] = None,
    exit_reason: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Trade]:
    """Get trade history with optional filters."""
    query = session.query(Trade).filter(Trade.status.in_(["CLOSED", "RESOLVED"]))
    if asset:
        query = query.filter(Trade.asset == asset)
    if timeframe:
        query = query.filter(Trade.timeframe == timeframe)
    if result:
        query = query.filter(Trade.result == result)
    if exit_reason:
        query = query.filter(Trade.exit_reason == exit_reason)
    return query.order_by(Trade.created_at.desc()).offset(offset).limit(limit).all()


def get_trades_since(session: Session, dt: datetime) -> list[Trade]:
    """Get all trades created since a given datetime."""
    return session.query(Trade).filter(Trade.created_at >= dt).order_by(Trade.created_at).all()


def get_daily_pnl(session: Session, date: Optional[datetime] = None) -> float:
    """Get total P&L for a given date (defaults to today UTC)."""
    if date is None:
        date = datetime.now(timezone.utc)

    start = date.replace(hour=0, minute=0, second=0, microsecond=0)
    end = date.replace(hour=23, minute=59, second=59, microsecond=999999)

    trades = (
        session.query(Trade)
        .filter(
            Trade.status.in_(["CLOSED", "RESOLVED"]),
            Trade.resolved_at >= start,
            Trade.resolved_at <= end,
        )
        .all()
    )
    return sum(t.pnl_usd or 0.0 for t in trades)


def count_trades(session: Session, status: Optional[str] = None) -> int:
    """Count trades, optionally filtered by status."""
    query = session.query(Trade)
    if status:
        query = query.filter(Trade.status == status)
    return query.count()
