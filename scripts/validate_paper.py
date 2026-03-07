"""Validate paper trading results against graduation criteria.

Reads all closed trades from the database and checks every graduation
criterion. Prints a detailed report with pass/fail for each.

Usage:
    python scripts/validate_paper.py
    python scripts/validate_paper.py --db sqlite:///polyquant.db
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.models import init_db, Trade
from config.settings import get_settings
from orchestrator.graduation import GraduationManager, TradeStats


def load_trade_stats(session, bankroll: float) -> TradeStats:
    """Build TradeStats from all closed/resolved trades in DB."""
    trades = (
        session.query(Trade)
        .filter(Trade.status.in_(["CLOSED", "RESOLVED"]))
        .order_by(Trade.created_at)
        .all()
    )

    if not trades:
        print("No closed trades found in database.")
        return TradeStats()

    total = len(trades)
    wins = sum(1 for t in trades if t.result == "WON")
    losses = sum(1 for t in trades if t.result == "LOST")
    total_pnl = sum(t.pnl_usd or 0.0 for t in trades)

    # Daily P&L aggregation
    daily_pnl = {}
    for t in trades:
        dt = t.resolved_at or t.created_at
        if dt:
            day = dt.strftime("%Y-%m-%d")
            daily_pnl[day] = daily_pnl.get(day, 0.0) + (t.pnl_usd or 0.0)
    daily_pnls = list(daily_pnl.values()) if daily_pnl else []

    # First trade date (ensure timezone-aware for graduation manager)
    first_trade_date = trades[0].created_at if trades else None
    if first_trade_date and first_trade_date.tzinfo is None:
        first_trade_date = first_trade_date.replace(tzinfo=timezone.utc)

    # Calibration error: mean |predicted - actual|
    cal_errors = []
    for t in trades:
        if t.your_prob is not None:
            actual = 1.0 if t.result == "WON" else 0.0
            if t.action == "BUY_NO":
                actual = 1.0 - actual  # Flip for BUY_NO
            cal_errors.append(abs(t.your_prob - actual))
    calibration_error = sum(cal_errors) / len(cal_errors) if cal_errors else 0.0

    # Count recalibration cycles from learning events
    from database.models import LearningEvent
    recal_events = (
        session.query(LearningEvent)
        .filter(LearningEvent.event_type == "recalibration")
        .all()
    )
    recal_cycles = len(recal_events)

    # Count CRITICAL models
    critical_events = (
        session.query(LearningEvent)
        .filter(LearningEvent.event_type == "model_critical")
        .order_by(LearningEvent.created_at.desc())
        .limit(20)
        .all()
    )
    # Count distinct models currently in CRITICAL (not recovered)
    critical_models = set()
    recovered_models = set()
    for ev in critical_events:
        if ev.model_name:
            critical_models.add(ev.model_name)
    # Check if any were promoted back
    promoted = (
        session.query(LearningEvent)
        .filter(LearningEvent.event_type == "model_promoted")
        .all()
    )
    for ev in promoted:
        if ev.model_name:
            recovered_models.add(ev.model_name)
    active_critical = critical_models - recovered_models

    return TradeStats(
        total_trades=total,
        wins=wins,
        losses=losses,
        total_pnl=total_pnl,
        daily_pnls=daily_pnls,
        first_trade_date=first_trade_date,
        calibration_error=calibration_error,
        recalibration_cycles=recal_cycles,
        critical_model_count=len(active_critical),
    )


def print_report(stats: TradeStats, check, settings):
    """Print a detailed graduation report."""
    bankroll = settings.BANKROLL_USDC

    print(f"\n{'='*60}")
    print(f"  POLYQUANT -- PAPER TRADING VALIDATION REPORT")
    print(f"{'='*60}")
    print(f"  Mode:     {settings.MODE.upper()}")
    print(f"  Bankroll: ${bankroll:,.0f}")
    print(f"  Date:     {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    # Trade summary
    print("TRADE SUMMARY")
    print(f"  Total trades:    {stats.total_trades}")
    print(f"  Wins:            {stats.wins}")
    print(f"  Losses:          {stats.losses}")
    print(f"  Win rate:        {stats.win_rate:.1%}")
    print(f"  Total P&L:       ${stats.total_pnl:,.2f}")
    print(f"  Sharpe ratio:    {stats.sharpe_ratio:.2f}")
    print(f"  Days trading:    {stats.days_trading}")
    print(f"  Max daily DD:    ${stats.max_daily_drawdown:,.2f}")
    if bankroll > 0:
        print(f"  Max DD % bankr:  {stats.max_daily_drawdown / bankroll:.1%}")
    print(f"  Calibration err: {stats.calibration_error:.3f}")
    print(f"  Recal cycles:    {stats.recalibration_cycles}")
    print(f"  CRITICAL models: {stats.critical_model_count}")
    print()

    # Graduation criteria
    print("GRADUATION CRITERIA")
    print(f"{'-'*60}")

    for criterion, passed in check.criteria.items():
        icon = "PASS" if passed else "FAIL"
        detail = check.details.get(criterion, "")
        print(f"  [{icon}] {criterion:<20s} {detail}")

    print(f"{'-'*60}")

    if check.eligible:
        print("\n  [OK] ALL CRITERIA MET -- READY TO GRADUATE TO LIVE\n")
    else:
        failed = check.failed_criteria
        print(f"\n  [!!] {len(failed)} CRITERIA FAILED: {', '.join(failed)}")
        print(f"       Not ready for live trading.\n")

    # Daily P&L breakdown
    if stats.daily_pnls:
        print("DAILY P&L (last 10 days)")
        for i, pnl in enumerate(stats.daily_pnls[-10:]):
            bar = "#" * max(1, int(abs(pnl) / 20))
            prefix = "+" if pnl >= 0 else ""
            marker = "+" if pnl >= 0 else "-"
            print(f"  Day {len(stats.daily_pnls) - 10 + i + 1:>3}: {prefix}${pnl:>8.2f} [{marker}] {bar}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Validate paper trading for graduation")
    parser.add_argument("--db", default=None, help="Database URL (default: from settings or dashboard DB)")
    args = parser.parse_args()

    settings = get_settings()
    db_url = args.db or settings.DB_URL

    # Try dashboard DB if main DB has no trades
    engine, session_factory = init_db(db_url)
    session = session_factory()

    trade_count = session.query(Trade).filter(Trade.status.in_(["CLOSED", "RESOLVED"])).count()
    if trade_count == 0:
        session.close()
        # Try dashboard DB
        db_url = "sqlite:///polyquant_dashboard.db"
        engine, session_factory = init_db(db_url)
        session = session_factory()
        trade_count = session.query(Trade).filter(Trade.status.in_(["CLOSED", "RESOLVED"])).count()

    print(f"Using DB: {db_url} ({trade_count} closed trades)")

    try:
        stats = load_trade_stats(session, settings.BANKROLL_USDC)

        manager = GraduationManager(bankroll=settings.BANKROLL_USDC)
        check = manager.check_graduation(stats)

        print_report(stats, check, settings)

        # Exit code: 0 if eligible, 1 if not
        sys.exit(0 if check.eligible else 1)

    finally:
        session.close()


if __name__ == "__main__":
    main()
