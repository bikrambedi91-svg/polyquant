"""Quick portfolio status check."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.models import init_db, Trade
from config.settings import get_settings
from datetime import datetime, timezone

s = get_settings()
engine, sf = init_db(s.DB_URL)
session = sf()

trades = session.query(Trade).all()
closed = [t for t in trades if t.status == 'CLOSED']
active = [t for t in trades if t.status == 'ACTIVE']

wins = [t for t in closed if t.result == 'WON']
losses = [t for t in closed if t.result == 'LOST']
total_pnl = sum(t.pnl_usd or 0 for t in closed)
total_fees = sum(t.taker_fee_paid or 0 for t in closed)

today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
today_closed = [t for t in closed if t.resolved_at and t.resolved_at.replace(tzinfo=timezone.utc) >= today_start]
today_pnl = sum(t.pnl_usd or 0 for t in today_closed)
today_wins = sum(1 for t in today_closed if t.result == 'WON')
today_losses = sum(1 for t in today_closed if t.result == 'LOST')

# Per-asset breakdown
assets = sorted(set(t.asset for t in closed))
per_asset = {}
for a in assets:
    at = [t for t in closed if t.asset == a]
    aw = sum(1 for t in at if t.result == 'WON')
    al = sum(1 for t in at if t.result == 'LOST')
    ap = sum(t.pnl_usd or 0 for t in at)
    per_asset[a] = (aw, al, ap)

# Per-action breakdown
buy_yes = [t for t in closed if t.action == 'BUY_YES']
buy_no = [t for t in closed if t.action == 'BUY_NO']

print("=== PORTFOLIO STATUS ===")
print(f"Total trades: {len(trades)}")
if closed:
    print(f"Closed: {len(closed)} (W:{len(wins)} L:{len(losses)} WR:{len(wins)/len(closed)*100:.1f}%)")
else:
    print("Closed: 0")
print(f"Active: {len(active)}")
print(f"Running PnL: ${total_pnl:.2f}")
print(f"Total fees: ${total_fees:.2f}")
print()

print("=== TODAY ===")
print(f"Closed: {len(today_closed)} (W:{today_wins} L:{today_losses})")
print(f"Today PnL: ${today_pnl:.2f}")
print()

print("=== PER ASSET ===")
for a, (w, l, p) in per_asset.items():
    wr = w / (w + l) * 100 if (w + l) > 0 else 0
    print(f"  {a}: {w}W/{l}L ({wr:.0f}%) PnL=${p:.2f}")
print()

print("=== PER ACTION ===")
yn_w = sum(1 for t in buy_yes if t.result == 'WON')
yn_l = sum(1 for t in buy_yes if t.result == 'LOST')
no_w = sum(1 for t in buy_no if t.result == 'WON')
no_l = sum(1 for t in buy_no if t.result == 'LOST')
print(f"  BUY_YES: {yn_w}W/{yn_l}L PnL=${sum(t.pnl_usd or 0 for t in buy_yes):.2f}")
print(f"  BUY_NO:  {no_w}W/{no_l}L PnL=${sum(t.pnl_usd or 0 for t in buy_no):.2f}")
print()

print("=== ACTIVE POSITIONS ===")
for t in active:
    tp = f"{t.tp_level:.3f}" if t.tp_level else "?"
    sl = f"{t.sl_level:.3f}" if t.sl_level else "?"
    ep = f"{t.entry_price:.3f}" if t.entry_price else "?"
    print(f"  {t.asset} {t.action} {t.timeframe} | entry={ep} tp={tp} sl={sl} | size=${t.size_usd:.0f}")

print()
print("=== LAST 10 CLOSED ===")
for t in sorted(closed, key=lambda x: x.resolved_at or datetime.min)[-10:]:
    pnl = t.pnl_usd or 0
    er = t.exit_reason or "?"
    ep = t.entry_price or 0
    xp = t.exit_price or 0
    print(f"  {t.asset} {t.action} {t.timeframe} | entry={ep:.3f} exit={xp:.3f} | pnl=${pnl:.2f} | {t.result} | {er}")

session.close()
