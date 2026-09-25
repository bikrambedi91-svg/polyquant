# MGC Playbook v2 — Pine Script Guide

File: `docs/mgc/MGC_Playbook.pine` · Pine Script v6 · overlay indicator.
It implements `02_MGC_Playbook_v2.md` on a single 5-minute chart: the higher-timeframe gaps,
their own-timeframe states, the liquidity map, the sweep → MSS → entry trigger, the room rule,
the grading checklist, position size, gold's clock, and a simulated trade manager that keeps the
daily counters.

---

## 1. Install (2 minutes)

1. TradingView → open **COMEX:MGC1!** (or **GC1!**) on the **5-minute** chart.
2. Pine Editor → *New* → paste the whole file → *Save* → *Add to chart*.
3. Inputs → group 5 *Risk & sizing*: set **Account size** and **Risk per trade %** (0.5% until
   you have 50 journaled trades). The dashboard's *Risk* row shows the dollar figure it will size from.
4. Inputs → group 6 *News*: type today's tier-1 releases as `hhmm` ET (e.g. `0830`, `1000`).
   Tick **FOMC day** on Fed days. Do this every morning as part of the pre-session (§6 of the playbook).
5. Optional: group 7 → enable **silver SMT** (needs a data plan that includes COMEX:SI1!).
6. Alerts: *Create alert* → condition **MGC Playbook** → **"Any alert() function call"**. One alert
   then delivers every dynamic message (POI touch, sweep, MSS, armed setup with prices and size,
   skips with reasons, fills, TP1, stops, gap failures, kill-zone opens, news windows, daily stop).
   The five static conditions (*Setup armed*, *Sweep at POI*, *MSS confirmed*, *Setup skipped*,
   *Price at POI*) are there if you prefer separate alerts.

The script warns in the dashboard header if the chart timeframe is not 5m or is higher than the
refinement timeframe.

---

## 2. What you see on the chart

| Element | Drawing | Meaning |
|---|---|---|
| 30m gaps | Strong fill, 2px border, dashed CE line | Primary zones (rank 3) |
| 15m gaps | Medium fill, 1px border, dashed CE | Refinement zones (rank 2) |
| 5m gaps | Faint fill, dotted border | Triggers only |
| Gap label (right of price) | `30m POI ★★★ · respected · touches 1 · STACKED · discount` | Role follows the current bias: **POI** (with-bias), **OBSTACLE** (opposing), **LIMBO** (5m closed through, HTF candle still open), **IFVG** (failed, flipped), **USED** (3rd touch). Stars = displacement + volume + London/NY session |
| Grey box | Failed gap kept as IFVG | Setup C candidate for `IFVG zone life` bars |
| Dotted horizontal lines | PDH/PDL, PWH/PWL, Asia H/L, London H/L, NY H/L, EQH/EQL | Major liquidity. Line stops with **✕** when swept, **⊘** when broken through |
| Orange label `sweep Asia L` | Sweep confirmed at a POI | `(weak)` = reclaimed within 2–3 bars, costs one confluence |
| Green/red label `MSS 2.4×` | Displacement close beyond the last opposite 5m swing | Ratio = body ÷ average body of the last 10 |
| Blue line + label | Armed limit order: entry, stop, R, TP1 (room in R and what it is), TP2 (what it is), grade, contracts | Lines run for `orderExpiry` bars |
| Grey label `SKIP LONG A — room 1.6R < 2.0R` | A trigger that failed a hard rule | Log it as a skip |
| Result label `+2.1R · TP2` | Simulated trade closed | Feeds the daily counters |
| Background | Blue = London KZ, teal = NY AM KZ, grey = lunch, yellow = PM, red = news window | Gold's clock |
| ◆ AM fix / PM fix, ■ settle | 5:30, 10:00, 13:30 ET | LBMA auctions and COMEX settlement |
| Orange line | Session VWAP (resets 6:00 PM ET) | Bias filter / confluence |
| Purple lines | 1H dealing range top, bottom and 50% | Premium above, discount below |

---

## 3. The dashboard, row by row

| Row | What it tells you |
|---|---|
| Header | Timeframes in use, or a warning if the chart is not 5m |
| Bias | BULLISH / BEARISH / NEUTRAL with the 1H and 4H arrows; **CONFLICTED** = 1H and 4H disagree → half risk, TP1 only; *1H gap lost* = price closed through the last with-bias 1H gap |
| Dealing range | Bottom – top, the 50%, and whether price is in DISCOUNT or PREMIUM |
| Draw on liquidity | Nearest untouched major level above and below (or your manual DOL) |
| Window | Where you are on gold's clock, and whether the window is TRADEABLE, A+ ONLY, or NO NEW TRADES |
| News | Blocked / clear, and the next release you typed in |
| HTF closes | Countdown to the next 30m and 15m closes (live bars only) — judge gaps on their own timeframe |
| ATR · ADR | 5m ATR (stop buffer), ADR and % used → *no Setup B* at 80%, *A+ only* at 100%, *DONE* at 130% |
| VWAP | Above / below |
| 30m / 15m zones | Counts of POIs, obstacles and IFVGs |
| Nearest POI / obstacle | Range, state and distance |
| Long / Short machine | The state each direction is in: idle → AT POI → SWEPT (and what the MSS needs) → MSS ✓ → ARMED → IN TRADE |
| Last event / Last setup | The most recent state change and the last armed or skipped setup with prices |
| Today | Simulated trades, R, losing streak, skips → **STOP FOR THE DAY** when a limit is hit |
| Week | Cumulative R → **WEEKLY STOP** at −5R |
| Risk | Dollar risk per trade, point value, tick |
| HARD RULES | The seven pass/fail rules for the last evaluated setup |
| CONFLUENCES | The eight +1 items, the weak-sweep penalty and the half-risk cap |

---

## 4. How each playbook rule is implemented

| Playbook rule | Implementation | Non-repainting? |
|---|---|---|
| FVG = three-candle imbalance (§3.2) | HTF: last three **confirmed** HTF candles via `request.security(..., [high[1] … low[3]], lookahead_on)` on the first 5m bar of each new HTF bar. 5m: `low > high[2]` / `high < low[2]` on confirmed bars. | Yes |
| Size ≥ 0.25 × that TF's ATR(14) | `minGapAtr` × HTF ATR | Yes |
| Displacement middle candle (§3.1) | Body ≥ 1.5 × avg body of the previous 10 candles of that TF, close in the outer 30% of its range. `reqDispHTF` off → gap still drawn, star missing | Yes |
| Judge a gap only on its own TF (§3.3) | State updates run only when a 30m/15m candle closes: close through far edge → **Failed**, close past CE → **Weakening** (sticky), else **Respected** | Yes |
| Touch / reaction, Used after two reactions | 5m entries into the gap from outside are counted; third entry → **Used** | Yes |
| Limbo (5m close through, HTF open) | Gap not POI-eligible while `close` is beyond its far edge | Yes |
| Keep ≤ 3 per side, clear old gaps | `maxPerSide` nearest active gaps above/below price; `gapMaxAge` (48h default) | — |
| POI vs obstacle (§8.2) | Bull gaps below price are POIs when bias is bullish; bear gaps above are obstacles; mirror for bearish; neutral shows both | — |
| Setup A POIs in discount / premium (§8.4) | `reqPD_A` (on by default) — the gap's CE must be on the right side of the 1H dealing-range 50% | — |
| Liquidity map (§3.4) | PDH/PDL and PWH/PWL from confirmed D/W bars; Asia 18:00–00:00 and London 02:00–08:00 ranges finalised at session end; NY H/L run from 08:00 and respawn when swept; EQH/EQL = two 5m pivots within max(3 ticks, 10% ATR); minor 5m pivots (len 2) for the last 60 bars | Yes |
| Sweep (§3.4) | Wick through a level and a 5m body closes back on the original side: same bar = **strong**, within `reclaimBars` (3) = **weak** (−1 confluence). A close beyond that is not reclaimed in time = level **broken**, not swept | Yes |
| Sweep at or inside the POI | Level price within [far edge − 0.5 ATR, near edge + 0.5 ATR] and price has touched the POI within `atPoiBars` | — |
| MSS (§3.1) | Displacement candle (or 2-bar sequence) closes beyond the most recent confirmed 5m swing that sits ≥ 0.5 ATR beyond the sweep extreme, within `mssWindow` (12) bars of the sweep; a close back through the swept level cancels the sweep | Yes |
| Entry gap | First 5m gap in the trade direction born within `entryGapBars` of the MSS whose far edge is beyond the sweep extreme → limit at CE (near edge if tiny: < 5 ticks or < 10% ATR). Alternate: an inverted 5m gap the MSS closed through | Yes |
| Stop | Sweep extreme ± max(12% ATR, 3 ticks), widened to ≥ 25 ticks | — |
| Room rule (§8.5) | TP1 = first opposing active 15m/30m gap edge **or** major level beyond entry, minus one tick; room = (TP1 − entry) ÷ R must be ≥ 2.0 | — |
| TP2 / DOL | Manual input, else the next major level beyond TP1; if none, an R-based fallback is labelled as such | — |
| Hard rules 1–7 (§10) | 1 bias (auto/manual, conflicted allowed at half) · 2 POI Respected/Weakening · 3 sweep · 4 MSS · 5 room ≥ 2R · 6 not in news/lunch/Friday PM, window class allows the grade · 7 trades < 3, R > −2, streak < 2, week > −5R, ADR < 130%, **calm checkbox** | — |
| Confluences 1–8 | Stacked 15m/30m · major level swept · discount/premium · displacement volume > 20-SMA · VWAP reclaimed/lost on the MSS bar · inside kill zone · first touch · silver SMT (optional) | — |
| Grade → risk | A+ ≥ 4 → 1.0 · A 2–3 → 0.5 · B ≤ 1 → 0 (or 0.25 with `allowB`) · Weakening POI, conflicted or neutral bias → cap 0.5 | — |
| Size | `floor(risk$ × mult ÷ (R × syminfo.pointvalue))` → works on GC too | — |
| Setup B (§9) | HH/HL on 5m pivots, above VWAP, fresh MSS ≤ 36 bars ago (from A or the generic tracker), **first** pullback into a 5m gap overlapping an active HTF gap; entry at the overlap CE, stop beyond the overlap far edge; blocked when ADR ≥ 80% | Yes |
| Setup C (§9) | Failed HTF gap whose flipped role agrees with bias, first retest within `ifvgLife` bars, 5m wick in and close back beyond the CE; stop beyond the far edge; re-fails if its own TF closes back through | Yes |
| Order handling (§11) | Cancel if TP1 is reached unfilled, a 5m body closes through the entry gap, `orderExpiry` (12) bars pass, or the window closes | — |
| Management (§12) | Stop untouched until TP1 → ladder (1 ct: all; 2 ct: half; 3+: third) → stop to breakeven → runner to TP2 or trailed under new 5m higher lows (never tighter than 1 ATR) → exits on POI failure, time stop (12 bars after the window ends), or a news window before TP1 (non-A+) | — |
| Daily / weekly limits (§13) | Counters from simulated trades (+ manual adjustments) reset at 18:00 ET / weekly; **STOP FOR THE DAY** and **WEEKLY STOP** in the dashboard and by alert | — |
| Gold's clock (§5) | Kill zones, lunch, PM (A+ only), 11:00–11:30 (A+ only), last 15 min of a KZ (A+ only), Friday after 12:00, tier-1 windows ± 15 min, FOMC 13:45–15:30, LBMA fixes and settlement markers; all in `America/New_York` so DST is handled | — |

---

## 5. What the script cannot decide for you

- **The draw on liquidity.** Auto = nearest major level. When the weekly story says otherwise
  (PWH two days away, an unfilled 4H gap), type it into *Manual overrides*.
- **The bias when structure is messy.** Auto bias is the last 1H body close beyond a 1H swing,
  checked against the 4H and the last 1H gap. Override it and log why.
- **Whether a gap "came out of a sweep or broke structure"** (§8.4 bonus). The stars cover
  displacement, volume and session only.
- **News that is not on your list.** Type releases in every morning. Headline moves > 1 ATR in one
  candle: stand aside 15 minutes (not automated).
- **Hard rule 7.** The counters are simulated from armed setups; the *calm* part is a checkbox.
  If you took a trade the script did not arm, add it to *Manual adjustment*.
- **Fills.** The simulator fills at the limit when price touches it and assumes the stop wins when
  a bar touches both stop and target. Real fills differ; the counters are a guide, the journal is the record.

---

## 6. Replay and backtest workflow (§16.3)

1. Bar Replay on the 5m chart, 1H/15m charts open beside it.
2. At each **AT POI** event, write the If–Then plan before stepping forward.
3. Let the script arm or skip. For every armed setup, check the checklist rows against your own
   read. Where you disagree, note which rule and why: that is where the playbook is unclear or
   where the script needs a parameter change.
4. Log every armed setup and every skip (reason) into the journal fields in §16.1.
5. After 50–100 setups, review by setup/grade/session/POI timeframe. Change one input at a time.

---

## 7. Tuning inputs safely

| Input | Default | When to change |
|---|---|---|
| `minGapAtr` | 0.25 | Too many slivers → 0.35. Too few gaps → 0.20 |
| `dispMult` | 1.5 | Gold in a high-vol regime → 1.3 catches more real shifts; chop → 1.8 |
| `reclaimBars` | 3 | Never above 4: a "sweep" that takes longer is a failed level |
| `mssWindow` | 12 | Keep 8–12; longer windows let stale sweeps trigger |
| `bufPct` / `minStopTicks` | 0.12 / 25 | If MAE analysis shows stops hit by 1–3 ticks then reversal, raise the buffer to 0.15 |
| `minRoomR` | 2.0 | Raise to 2.5 on 15m POIs if the journal shows TP1 misses |
| `maxPerSide` | 3 | Leave. More boxes = worse decisions |
| `gapMaxAge` | 576 | Lower to 288 if you only trade New York and yesterday's London gaps distract |
| `allowOff` | off | Only after London/NY results are proven |
| `allowB` | off | Only after 50+ journaled trades show B setups pay |

---

## 8. Known limits

- Pine draws at most 500 boxes/lines/labels per script; the script prunes its own objects but very
  long histories drop the oldest setup markers first.
- `request.security` with `lookahead_on` and `[1]` offsets is the documented non-repainting idiom;
  HTF gaps therefore appear on the first 5m bar **after** the HTF candle closes, never earlier.
- Realtime state changes are evaluated on confirmed 5m bars, so an alert arrives at the close of
  the bar that produced it.
- The SMT check compares the sweep bar against the last 20 bars of both symbols; it is a proxy
  for "silver did not make the same low", not a full SMT engine.
- Session strings use the exchange calendar; a holiday half-session still shows kill zones. The
  playbook says no trades on those days.
