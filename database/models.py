"""SQLAlchemy ORM models and engine setup.

IMPORTANT: SQLite uses WAL mode (Write-Ahead Logging) to prevent
"database locked" errors when the bot and Streamlit dashboard access
the database concurrently.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(String(64), unique=True, nullable=False, index=True)
    asset = Column(String(10), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False)
    market_title = Column(String(256), nullable=True)
    market_url = Column(String(512), nullable=True)
    market_type = Column(String(20), default="up_down")  # "up_down" or "price_target"
    action = Column(String(10), nullable=False)  # "BUY_YES" or "BUY_NO"
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    size_usd = Column(Float, nullable=False)
    pnl_usd = Column(Float, nullable=True)
    result = Column(String(10), nullable=True)  # "WON", "LOST", or None
    status = Column(String(10), nullable=False, default="ACTIVE", index=True)  # ACTIVE, CLOSED, RESOLVED
    exit_reason = Column(String(30), nullable=True)  # resolution, take_profit, stop_loss, time_decay, edge_evaporated
    your_prob = Column(Float, nullable=True)
    market_implied = Column(Float, nullable=True)
    edge_at_entry = Column(Float, nullable=True)
    confidence = Column(Integer, nullable=True)
    tp_level = Column(Float, nullable=True)
    sl_level = Column(Float, nullable=True)
    was_sl_learned = Column(Boolean, default=False)
    would_have_won_if_held = Column(Boolean, nullable=True)
    max_adverse_excursion = Column(Float, nullable=True)
    max_favorable_excursion = Column(Float, nullable=True)
    regime_at_entry = Column(String(20), nullable=True)
    param_versions_json = Column(Text, nullable=True)  # JSON string of model param versions
    oracle_start_price = Column(Float, nullable=True)
    oracle_end_price = Column(Float, nullable=True)
    taker_fee_paid = Column(Float, default=0.0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime, nullable=True)


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset = Column(String(10), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False, index=True)
    model_name = Column(String(30), nullable=False)
    prob_up = Column(Float, nullable=False)
    confidence = Column(Integer, nullable=False)
    param_version = Column(Integer, nullable=True)
    ensemble_prob = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class LearningEvent(Base):
    __tablename__ = "learning_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False, index=True)  # e.g., "param_mutation", "model_retired", "sl_updated"
    model_name = Column(String(30), nullable=True)
    timeframe = Column(String(10), nullable=True)
    details_json = Column(Text, nullable=True)  # JSON string with event details
    param_before_json = Column(Text, nullable=True)
    param_after_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PipelineDecision(Base):
    """Logs every decision step in the pipeline for dashboard visibility.

    Each row = one asset evaluation within one cycle. The details_json
    contains the full chain of reasoning at each filter step.
    """
    __tablename__ = "pipeline_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cycle_id = Column(String(32), nullable=False, index=True)  # unique per pipeline run
    asset = Column(String(10), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False)
    market_title = Column(String(256), nullable=True)
    stage = Column(String(30), nullable=False)  # signal, ensemble, edge, filter, risk, execute
    decision = Column(String(10), nullable=False)  # PASS, REJECT, TRADE, INFO
    reason = Column(String(256), nullable=True)  # human-readable explanation
    details_json = Column(Text, nullable=True)  # JSON: all numeric values at this step
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


def _set_sqlite_wal(dbapi_connection, connection_record):
    """Enable WAL mode on SQLite connections."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def create_db_engine(db_url: str):
    """Create a SQLAlchemy engine with appropriate settings.

    For SQLite: enables WAL mode and sets a connection timeout of 30s.
    """
    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args = {"timeout": 30}

    engine = create_engine(db_url, connect_args=connect_args)

    # Enable WAL mode for SQLite
    if db_url.startswith("sqlite"):
        event.listen(engine, "connect", _set_sqlite_wal)

    return engine


def create_session_factory(engine):
    """Create a sessionmaker bound to the given engine."""
    return sessionmaker(bind=engine)


def init_db(db_url: str):
    """Initialize the database: create engine, tables, and return (engine, SessionFactory)."""
    engine = create_db_engine(db_url)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    return engine, session_factory
