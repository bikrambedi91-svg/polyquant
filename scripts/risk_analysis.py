"""Risk concentration analysis for active positions."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from database.models import Trade
from datetime import datetime, timezone

engine = create_engine("sqlite:///polyquant.db")
with Session(engine) as s:
    active = s.query(Trade).filter(Trade.status == "ACTIVE").order_by(Trade.created_at).all()
    closed = s.query(Trade).filter(Trade.status.in_(["CLOSED", "RESOLVED"])).all()
    now = datetime.now(timezone.utc)
    total_pnl = sum(t.pnl_usd or 0 for t in closed)

    print("=== ACTIVE POSITION AGE & RISK ===")
    total_long = 0
    total_short = 0
    for t in active:
        created = t.created_at.replace(tzinfo=timezone.utc)
        age_min = (now - created).total_seconds() / 60
        direction = "LONG" if t.action == "BUY_YES" else "SHORT"
        if direction == "LONG":
            total_long += t.size_usd
        else:
            total_short += t.size_usd
        tp_s = f"{t.tp_level:.3f}" if t.tp_level else "N/A"
        sl_s = f"{t.sl_level:.3f}" if t.sl_level else "N/A"
        print(f"  {t.trade_id[-8:]} {t.asset:4s} {t.timeframe:5s} {t.action:8s} | ${t.size_usd:.0f} | age={age_min:.0f}min | entry={t.entry_price:.3f} SL={sl_s} TP={tp_s}")

    print()
    print("DIRECTIONAL EXPOSURE:")
    print(f"  BUY_YES (long crypto): ${total_long:.0f}")
    print(f"  BUY_NO  (short crypto): ${total_short:.0f}")
    print(f"  Net long: ${total_long - total_short:.0f}")
    print(f"  Total exposure: ${total_long + total_short:.0f} / $600 limit (60%)")

    # Worst case if all BUY_YES SL simultaneously
    buy_yes_active = [t for t in active if t.action == "BUY_YES"]
    worst_case_yes = 0
    for t in buy_yes_active:
        shares = t.size_usd / t.entry_price if t.entry_price > 0 else 0
        sl_loss = (t.entry_price - t.sl_level) * shares + (t.taker_fee_paid or 0)
        worst_case_yes += sl_loss

    buy_no_active = [t for t in active if t.action == "BUY_NO"]
    worst_case_no = 0
    for t in buy_no_active:
        no_entry = 1.0 - t.entry_price
        shares = t.size_usd / no_entry if no_entry > 0 else 0
        no_sl = 1.0 - t.sl_level  # NO price at SL
        sl_loss_no = (no_entry - no_sl) * shares + (t.taker_fee_paid or 0)
        worst_case_no += sl_loss_no

    print()
    print("WORST CASE SIMULTANEOUS SL:")
    print(f"  All BUY_YES SL: -${worst_case_yes:.2f}")
    print(f"  All BUY_NO SL:  -${worst_case_no:.2f}")
    print(f"  Total worst case: -${worst_case_yes + worst_case_no:.2f}")
    print(f"  vs realized PnL: ${total_pnl:+.2f}")
    print(f"  Net if worst case: ${total_pnl - worst_case_yes - worst_case_no:.2f}")

    # Correlation risk
    print()
    print("CORRELATION RISK:")
    by_direction = {}
    for t in active:
        key = (t.action, t.timeframe)
        by_direction.setdefault(key, []).append(t)
    for (action, tf), trades in sorted(by_direction.items()):
        assets = [t.asset for t in trades]
        total = sum(t.size_usd for t in trades)
        print(f"  {action} {tf}: {len(trades)} positions ({', '.join(assets)}) = ${total:.0f}")
