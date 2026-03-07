"""Quick trade analysis script."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from database.models import Trade

engine = create_engine("sqlite:///polyquant.db")
with Session(engine) as s:
    trades = s.query(Trade).order_by(Trade.created_at).all()
    active_trades = [t for t in trades if t.status == "ACTIVE"]
    closed_trades = [t for t in trades if t.status in ("CLOSED", "RESOLVED")]
    wins = [t for t in closed_trades if t.result == "WON"]
    losses = [t for t in closed_trades if t.result == "LOST"]
    total_pnl = sum(t.pnl_usd or 0 for t in closed_trades)
    total_fees = sum(t.taker_fee_paid or 0 for t in closed_trades)

    buy_yes_closed = [t for t in closed_trades if t.action == "BUY_YES"]
    buy_no_closed = [t for t in closed_trades if t.action == "BUY_NO"]
    by_yes_wins = [t for t in buy_yes_closed if t.result == "WON"]
    by_no_wins = [t for t in buy_no_closed if t.result == "WON"]

    print(f"Total: {len(trades)} | Active: {len(active_trades)} | Closed: {len(closed_trades)}")
    print(f"W/L: {len(wins)}W / {len(losses)}L | Total PnL: ${total_pnl:+.2f}")
    if buy_yes_closed:
        yes_pnl = sum(t.pnl_usd or 0 for t in buy_yes_closed)
        print(f"BUY_YES: {len(by_yes_wins)}/{len(buy_yes_closed)} ({len(by_yes_wins)/len(buy_yes_closed)*100:.0f}% WR) PnL=${yes_pnl:+.2f}")
    if buy_no_closed:
        no_pnl = sum(t.pnl_usd or 0 for t in buy_no_closed)
        print(f"BUY_NO:  {len(by_no_wins)}/{len(buy_no_closed)} ({len(by_no_wins)/len(buy_no_closed)*100:.0f}% WR) PnL=${no_pnl:+.2f}")
    print(f"Total fees (closed): ${total_fees:.2f}")
    print()

    print(f"{'ID':>8} {'Asset':>5} {'TF':>5} {'Act':>8} {'Type':>10} {'Entry':>6} {'Exit':>6} {'TP':>6} {'SL':>6} {'Size':>6} {'PnL':>10} {'Fee':>6} {'Reason':>15} {'St':>8}")
    print("-" * 130)
    for t in trades:
        tid = t.trade_id[-8:]
        ex = f"{t.exit_price:.3f}" if t.exit_price else "  -  "
        pnl = f"${t.pnl_usd:+.2f}" if t.pnl_usd else "     -"
        reason = (t.exit_reason or "-")[:15]
        fee = f"${t.taker_fee_paid:.2f}" if t.taker_fee_paid else " $0.00"
        mtype = (t.market_type or "unk")[:10]
        sz = f"${t.size_usd:.0f}"
        tp = f"{t.tp_level:.3f}" if t.tp_level else "  -  "
        sl = f"{t.sl_level:.3f}" if t.sl_level else "  -  "
        print(f"{tid:>8} {t.asset:>5} {t.timeframe:>5} {t.action:>8} {mtype:>10} {t.entry_price:.3f} {ex:>6} {tp:>6} {sl:>6} {sz:>6} {pnl:>10} {fee:>6} {reason:>15} {t.status:>8}")
