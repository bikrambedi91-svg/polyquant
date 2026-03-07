"""Diagnostic: check what 4h UP/DOWN markets the scanner is finding."""
import sys
import os
import asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market.scanner import PolymarketScanner
from datetime import datetime, timezone

async def main():
    scanner = PolymarketScanner()
    markets = await scanner.discover_markets()

    now = datetime.now(timezone.utc)
    print(f"Current UTC time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total markets discovered: {len(markets)}")
    print()

    # Focus on 4h and daily markets
    for tf in ["4h", "1h", "daily"]:
        tf_markets = [m for m in markets if m.timeframe == tf]
        print(f"=== {tf} MARKETS ({len(tf_markets)}) ===")
        for m in tf_markets[:15]:  # show first 15
            start_str = m.start_datetime.strftime("%H:%M:%S") if m.start_datetime else "NONE"
            end_str = m.end_datetime.strftime("%H:%M:%S") if m.end_datetime else "NONE"

            if m.start_datetime:
                time_since_start = (now - m.start_datetime).total_seconds()
                start_status = f"started {time_since_start:.0f}s ago" if time_since_start > 0 else f"STARTS IN {-time_since_start:.0f}s"
            else:
                start_status = "NO START TIME"

            if m.end_datetime:
                ttr = (m.end_datetime - now).total_seconds()
                end_status = f"resolves in {ttr:.0f}s ({ttr/60:.0f}min)"
            else:
                end_status = "NO END TIME"

            print(f"  {m.asset:4s} {m.market_type:12s} | start={start_str:>8s} end={end_str:>8s} | {start_status:>25s} | {end_status}")
            print(f"       title: {m.title[:80]}")
        print()

asyncio.run(main())
