"""Quick stats check for monitoring."""
import sys
sys.path.insert(0, ".")

from database.models import init_db, Trade
from datetime import datetime, timezone

engine, SF = init_db("sqlite:///polyquant.db")
s = SF()
trades = s.query(Trade).all()
total = len(trades)
active = [t for t in trades if t.status == "ACTIVE"]
closed = [t for t in trades if t.status in ("CLOSED", "RESOLVED")]
wins = [t for t in closed if t.result == "WON"]
losses = [t for t in closed if t.result == "LOST"]
total_pnl = sum(t.pnl_usd or 0 for t in closed)

today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
today_trades = [t for t in closed if t.resolved_at and t.resolved_at.replace(tzinfo=timezone.utc) >= today_start]
today_pnl = sum(t.pnl_usd or 0 for t in today_trades)
today_wins = len([t for t in today_trades if t.result == "WON"])
today_losses = len([t for t in today_trades if t.result == "LOST"])

last5 = sorted(closed, key=lambda t: t.resolved_at or datetime.min)[-5:]

print("=== OVERALL STATS ===")
print(f"Total trades: {total}")
print(f"Active: {len(active)}")
print(f"Closed: {len(closed)}")
print(f"Wins: {len(wins)} | Losses: {len(losses)}")
if closed:
    print(f"Win Rate: {len(wins)/len(closed)*100:.1f}%")
print(f"Total PnL: ${total_pnl:.2f}")
print()
print(f"=== TODAY ({today_start.strftime('%Y-%m-%d')}) ===")
print(f"Trades: {len(today_trades)} ({today_wins}W/{today_losses}L)")
print(f"Today PnL: ${today_pnl:.2f}")
print()
print("=== LAST 5 CLOSED TRADES ===")
for t in last5:
    rt = t.resolved_at.strftime("%H:%M") if t.resolved_at else "?"
    pnl = t.pnl_usd or 0
    print(f"  {rt} | {t.asset} {t.action} {t.timeframe} | entry={t.entry_price:.3f} exit={t.exit_price:.3f} | {t.result} ${pnl:+.2f} | {t.exit_reason}")

# Exit reason breakdown
print()
print("=== EXIT REASON BREAKDOWN ===")
reasons = {}
for t in closed:
    r = t.exit_reason or "unknown"
    if r not in reasons:
        reasons[r] = {"count": 0, "pnl": 0.0}
    reasons[r]["count"] += 1
    reasons[r]["pnl"] += t.pnl_usd or 0
for r, d in sorted(reasons.items()):
    print(f"  {r}: {d['count']} trades, ${d['pnl']:+.2f}")

# Per-asset breakdown
print()
print("=== PER-ASSET BREAKDOWN ===")
assets = {}
for t in closed:
    a = t.asset
    if a not in assets:
        assets[a] = {"wins": 0, "losses": 0, "pnl": 0.0}
    if t.result == "WON":
        assets[a]["wins"] += 1
    else:
        assets[a]["losses"] += 1
    assets[a]["pnl"] += t.pnl_usd or 0
for a, d in sorted(assets.items()):
    tot = d["wins"] + d["losses"]
    wr = d["wins"] / tot * 100 if tot > 0 else 0
    print(f"  {a}: {d['wins']}W/{d['losses']}L ({wr:.0f}% WR), ${d['pnl']:+.2f}")

s.close()
