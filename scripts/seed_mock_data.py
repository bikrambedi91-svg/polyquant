"""Seed the database with realistic mock data for dashboard and validation testing.

Creates ~200 closed trades, 8 active positions, signals, and learning events
spanning 20 days. Run: python -m scripts.seed_mock_data
"""

import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.models import init_db, Trade, Signal, LearningEvent
from config.constants import ASSETS, MARKET_TIMEFRAMES, MODEL_NAMES, REGIMES

random.seed(42)

DB_URL = "sqlite:///polyquant_dashboard.db"
BANKROLL = 10_000.0
NUM_CLOSED_TRADES = 200
NUM_ACTIVE_TRADES = 8
NUM_DAYS = 20


def _rand_dt(start: datetime, end: datetime) -> datetime:
    delta = (end - start).total_seconds()
    return start + timedelta(seconds=random.uniform(0, delta))


def _seed_trades(session):
    """Generate closed + active trades."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=NUM_DAYS)

    trades = []
    cumulative_pnl = 0.0

    # Closed trades
    for i in range(NUM_CLOSED_TRADES):
        asset = random.choice(ASSETS)
        tf = random.choice(MARKET_TIMEFRAMES)
        action = random.choice(["BUY_YES", "BUY_NO"])
        entry = round(random.uniform(0.35, 0.70), 2)
        our_prob = round(entry + random.uniform(0.05, 0.20), 2)
        our_prob = min(our_prob, 0.95)
        edge = round(abs(our_prob - entry), 3)
        confidence = random.randint(55, 92)
        size = round(random.uniform(80, 600), 2)
        regime = random.choice(REGIMES)
        sl = round(entry - random.uniform(0.06, 0.15), 2)
        tp = round(our_prob + 0.05, 2)
        was_sl_learned = random.random() < 0.3

        # 58% win rate overall
        won = random.random() < 0.58
        if won:
            exit_price = round(random.uniform(entry + 0.02, min(tp + 0.03, 0.98)), 2)
            pnl = round(size * (exit_price - entry) - random.uniform(0, 2), 2)
            result = "WON"
            exit_reason = random.choice(["resolution", "take_profit"])
        else:
            exit_price = round(random.uniform(max(sl - 0.02, 0.02), entry - 0.01), 2)
            pnl = round(size * (exit_price - entry) - random.uniform(0, 2), 2)
            result = "LOST"
            exit_reason = random.choice(["resolution", "stop_loss", "time_decay"])

        cumulative_pnl += pnl
        created = _rand_dt(start, now - timedelta(hours=2))
        resolved = created + timedelta(minutes=random.randint(5, 240))
        taker_fee = round(random.uniform(0, 3.0), 2) if tf in ("5m", "15m") else 0.0

        mae = round(random.uniform(0.01, 0.12), 3)
        mfe = round(random.uniform(0.02, 0.15), 3)
        whwih = random.random() < 0.6 if result == "LOST" else None

        trade = Trade(
            trade_id=f"PAPER-{i:04d}",
            asset=asset,
            timeframe=tf,
            market_title=f"Will {asset} go up in the next {tf}?",
            market_url=f"https://polymarket.com/event/{asset.lower()}-{tf}",
            market_type="up_down",
            action=action,
            entry_price=entry,
            exit_price=exit_price,
            size_usd=size,
            pnl_usd=pnl,
            result=result,
            status="CLOSED",
            exit_reason=exit_reason,
            your_prob=our_prob,
            market_implied=entry,
            edge_at_entry=edge,
            confidence=confidence,
            tp_level=tp,
            sl_level=sl,
            was_sl_learned=was_sl_learned,
            would_have_won_if_held=whwih,
            max_adverse_excursion=mae,
            max_favorable_excursion=mfe,
            regime_at_entry=regime,
            param_versions_json=json.dumps({"MomRegime": 1, "TechConf": 1}),
            oracle_start_price=round(random.uniform(60000, 70000), 2) if asset == "BTC" else round(random.uniform(100, 4000), 2),
            oracle_end_price=round(random.uniform(60000, 70000), 2) if asset == "BTC" else round(random.uniform(100, 4000), 2),
            taker_fee_paid=taker_fee,
            created_at=created,
            resolved_at=resolved,
        )
        trades.append(trade)

    # Active trades
    for i in range(NUM_ACTIVE_TRADES):
        asset = ASSETS[i % len(ASSETS)]
        tf = random.choice(["1h", "4h"])
        action = random.choice(["BUY_YES", "BUY_NO"])
        entry = round(random.uniform(0.40, 0.65), 2)
        our_prob = round(entry + random.uniform(0.08, 0.18), 2)
        edge = round(abs(our_prob - entry), 3)
        confidence = random.randint(60, 88)
        size = round(random.uniform(100, 500), 2)
        regime = random.choice(REGIMES)

        trade = Trade(
            trade_id=f"PAPER-A{i:03d}",
            asset=asset,
            timeframe=tf,
            market_title=f"Will {asset} go up in the next {tf}?",
            market_url=f"https://polymarket.com/event/{asset.lower()}-{tf}",
            market_type="up_down",
            action=action,
            entry_price=entry,
            size_usd=size,
            status="ACTIVE",
            your_prob=our_prob,
            market_implied=entry,
            edge_at_entry=edge,
            confidence=confidence,
            tp_level=round(our_prob + 0.05, 2),
            sl_level=round(entry - 0.12, 2),
            was_sl_learned=random.random() < 0.3,
            regime_at_entry=regime,
            param_versions_json=json.dumps({"MomRegime": 1, "TechConf": 1}),
            taker_fee_paid=0.0,
            created_at=now - timedelta(minutes=random.randint(10, 120)),
        )
        trades.append(trade)

    session.add_all(trades)
    session.commit()
    print(f"  Seeded {NUM_CLOSED_TRADES} closed + {NUM_ACTIVE_TRADES} active trades")


def _seed_signals(session):
    """Generate recent signals for each asset/timeframe/model."""
    now = datetime.now(timezone.utc)
    signals = []

    for asset in ASSETS:
        for tf in MARKET_TIMEFRAMES:
            ensemble_prob = round(random.uniform(0.45, 0.80), 3)
            for model in MODEL_NAMES:
                prob = round(random.uniform(0.40, 0.85), 3)
                conf = random.randint(30, 95)
                sig = Signal(
                    asset=asset,
                    timeframe=tf,
                    model_name=model,
                    prob_up=prob,
                    confidence=conf,
                    param_version=1,
                    ensemble_prob=ensemble_prob,
                    created_at=now - timedelta(minutes=random.randint(0, 30)),
                )
                signals.append(sig)

    session.add_all(signals)
    session.commit()
    print(f"  Seeded {len(signals)} signals")


def _seed_learning_events(session):
    """Generate learning events over last 20 days."""
    now = datetime.now(timezone.utc)
    events = []

    event_types = [
        ("recalibration", None),
        ("weight_update", None),
        ("param_mutation", "MomRegime"),
        ("model_warning", "FundBasis"),
        ("sl_updated", None),
        ("tp_updated", None),
        ("model_promoted", "TechConf"),
        ("param_mutation", "VolSurf"),
        ("recalibration", None),
        ("model_warning", "ChainFlow"),
        ("model_critical", "SentComp"),
        ("sl_updated", None),
        ("recalibration", None),
    ]

    for i, (etype, model) in enumerate(event_types):
        dt = now - timedelta(days=NUM_DAYS - i * (NUM_DAYS / len(event_types)))
        details = {}
        if etype == "recalibration":
            details = {"cycle": i // 3 + 1, "total_trades": 50 + i * 10, "models_evaluated": 7}
        elif etype == "weight_update":
            details = {"model": "MomRegime", "old_weight": 0.20, "new_weight": 0.22}
        elif etype == "param_mutation":
            details = {"param": "ema_fast", "old": 12, "new": 10}
        elif etype in ("model_warning", "model_critical"):
            details = {"brier_score": round(random.uniform(0.28, 0.38), 3), "status": etype.split("_")[1].upper()}
        elif etype in ("sl_updated", "tp_updated"):
            details = {"asset": "BTC", "timeframe": "1h", "old_level": 0.12, "new_level": 0.10}
        elif etype == "model_promoted":
            details = {"from": "PROBATION", "to": "ACTIVE", "shadow_trades": 35, "brier": 0.21}

        ev = LearningEvent(
            event_type=etype,
            model_name=model or random.choice(MODEL_NAMES),
            timeframe=random.choice(MARKET_TIMEFRAMES),
            details_json=json.dumps(details),
            created_at=dt,
        )
        events.append(ev)

    session.add_all(events)
    session.commit()
    print(f"  Seeded {len(events)} learning events")


def main():
    print(f"Seeding dashboard DB: {DB_URL}")
    engine, SessionFactory = init_db(DB_URL)
    session = SessionFactory()

    try:
        _seed_trades(session)
        _seed_signals(session)
        _seed_learning_events(session)
        print("Done! Run dashboard with: streamlit run dashboard/app.py")
    finally:
        session.close()


if __name__ == "__main__":
    main()
