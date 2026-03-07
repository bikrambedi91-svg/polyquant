"""Check TP/SL levels on recent trades for validation."""
import sys
sys.path.insert(0, ".")

from database.models import init_db, Trade
from datetime import datetime, timezone

engine, SF = init_db("sqlite:///polyquant.db")
s = SF()

# Last 10 closed trades
trades = (s.query(Trade)
          .filter(Trade.status.in_(["CLOSED", "RESOLVED"]))
          .order_by(Trade.resolved_at.desc())
          .limit(10)
          .all())

print("=== LAST 10 TRADES — TP/SL VALIDATION ===")
for t in trades:
    rt = t.resolved_at.strftime("%H:%M:%S") if t.resolved_at else "?"

    # Expected TP/SL from fill price
    if t.action == "BUY_NO":
        expected_sl = t.entry_price + 0.10 * (1 - t.entry_price)
        expected_tp = t.entry_price - 0.20 * (1 - t.entry_price)
        tp_ok = abs((t.tp_level or 0) - expected_tp) < 0.005
        sl_ok = abs((t.sl_level or 0) - expected_sl) < 0.005
    else:  # BUY_YES
        expected_sl = t.entry_price * (1 - 0.10)
        expected_tp = min(t.entry_price * (1 + 0.20), 0.95)
        tp_ok = abs((t.tp_level or 0) - expected_tp) < 0.005
        sl_ok = abs((t.sl_level or 0) - expected_sl) < 0.005

    tp_flag = "OK" if tp_ok else "MISMATCH"
    sl_flag = "OK" if sl_ok else "MISMATCH"

    print(f"  {rt} | {t.asset} {t.action} {t.timeframe}")
    print(f"    entry={t.entry_price:.4f} exit={t.exit_price:.4f} | {t.result} ${(t.pnl_usd or 0):+.2f} | {t.exit_reason}")
    print(f"    TP: actual={t.tp_level:.4f} expected={expected_tp:.4f} [{tp_flag}]")
    print(f"    SL: actual={t.sl_level:.4f} expected={expected_sl:.4f} [{sl_flag}]")

    # Validate exit price matches reason
    if t.exit_reason == "take_profit":
        if abs(t.exit_price - (t.tp_level or 0)) > 0.005:
            print(f"    *** EXIT PRICE MISMATCH: exit={t.exit_price:.4f} != tp={t.tp_level:.4f}")
    print()

s.close()
