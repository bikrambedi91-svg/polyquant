# MGC Playbook v2 — Pine Script Guide

> **Which file do I use?** There are now two scripts in this folder.
>
> | File | Type | Use it when |
> |---|---|---|
> | `MGC_PBX_v2.pine` | **Strategy** (Strategy Tester) | You want the playbook executed and journaled: simulated bracket orders, TP1 partials, cancels, an honest trade list, plus the v2 rules below. **This is the recommended script.** |
> | `MGC_PBX_v1_baseline.pine` | Strategy | The unmodified script `MGC_PBX_v2.pine` was built from, kept so every change is diffable. |
> | `MGC_Playbook.pine` | Indicator | The earlier indicator-only implementation. Superseded; kept for reference. |
>
> ## MGC_PBX_v2 in two minutes
>
> 1. Chart: **COMEX:MGC1!**, **5 minutes**, and turn **back-adjustment on** (the "B-ADJ" toggle next to the symbol). The script warns with a red DATA row if the contract is unadjusted, because roll steps fake gaps and levels.
> 2. Pine Editor → paste → Add to chart. Open the **Strategy Tester** tab for the trade list.
> 3. Settings → group 5: set **Full risk per trade** (one R). Group 7: type today's extra release in **Extra release today** if there is one; 08:30 and 10:00 are blocked every day.
> 4. Alerts → create one alert on the script with the condition **"Any alert() function call"**. Every LAST-line event (zone reached, sweep, shift, order, fill, exit, skip, cancel) is sent.
> 5. Read the panel: **NOW** is one sentence in plain English, coloured yellow when an order or trade exists, blue when a setup is forming, grey when there is nothing to do, red when the day is stopped. Hover any zone, level or tag for the detail.
>
> ## What v2 adds to the baseline (all switchable in settings)
>
> | Playbook v2 rule | Where it lives |
> |---|---|
> | Setup C: IFVG flip retest (§9) | Group 4 `Setup C`. A failed 15m/30m zone that now agrees with the bias; first return, 5m close back beyond the midpoint; limit at the midpoint, stop beyond the far edge. |
> | 10:00 news window + an extra release time (§5) | Group 7 `Treat 10:00 as a data release`, `Extra release today`. |
> | A+-only windows: kill-zone tail, 11:00–11:30, afternoon (§5.2, rule 6) | Group 7 `A+ only`. Entries allowed there only when the setup grades A+. |
> | ADR budget tiers: 80% no Setup B, 100% A+ only, 130% done (§13.3) | Group 5 `Range budget`. |
> | Minimum stop distance 25 ticks (§3.5) | Group 4 `Minimum stop distance`. A tighter stop is widened. |
> | TP1 one tick in front of the obstacle (§8.5) | Built in. |
> | Weak sweep costs one confluence (§10) | Built in: a level reclaimed on a later candle than the one that took it. Shown as `weak-sweep(-1)` in the plus-points. |
> | Contract ladder: 3+ contracts take a third at TP1 (§11) | Built in. 1 contract: all out or hold (group 6). 2: one off. |
> | 1H against 4H → 1H direction at half risk, everything off at TP1 (§7.1) | Group 1 bias option `Auto: 1H, half risk when 4H disagrees`. |
> | Neutral bias: A+ sweeps of PDH/PDL, Asia or London H/L at half risk (§7.1) | Group 1 `When the bias is not clear`. |
> | Unfilled orders expire after 12 bars (§3.5) | Group 6 `Cancel an unfilled order after N bars`. |
> | LBMA AM/PM fix and settlement marks (§5.1) | Group 8 `Mark the LBMA fixes`. |
> | Alerts on every event | Group 8 `Send every LAST-line event`. |
> | DEBUG row off by default | Group 8. |
>
> The baseline's own strengths are untouched: 15m/30m candles rebuilt from the 5m bars with a parity check, the pre-session bias snapshot, the §5.3 sweep-with-deadline rule, zone merging, the single label column, and the Strategy Tester bracket engine.
>
> ---
>
> *The sections below describe the earlier indicator, `MGC_Playbook.pine`.*



File: `docs/mgc/MGC_Playbook.pine` · Pine Script v6 · overlay indicator.
It implements `02_MGC_Playbook_v2.md` on a single 5-minute chart: the higher-timeframe gaps,
their own-timeframe states, the liquidity map, the sweep → MSS → entry trigger, the room rule,
the grading checklist, position size, gold's clock, and a simulated trade manager that keeps the
daily counters.

---

## 1. Install (2 minutes)

1. TradingView → open **COMEX:MGC1!** (or **GC1!**) on the **5-minute** chart. On any other
   timeframe the script draws nothing and the card says "Switch this chart to 5 minutes".
2. Pine Editor → *New* → paste the whole file → *Save* → *Add to chart*.
   The default **View** is *Clean*: the two nearest zones per side, today's levels, and a
   7-row status card in plain English. Hover any zone, level, marker or card row for the details.
   *Standard* adds CE lines, 5m gaps, the dealing range, session marks and clock rows;
   *Everything* adds the full 7 + 8 checklist.
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

The chart stays quiet on purpose: short labels, muted fills, and the full story one hover away.

| Element | Looks like | Hover shows |
|---|---|---|
| 30m / 15m zones | Soft teal (bullish) or rose (bearish) boxes, thin border, 30m slightly stronger | Range and midpoint, what to do there, state (respected / weakening / failed / used), touches, stacked, discount/premium, quality |
| Zone label (right edge) | `30m POI`, `15m obstacle`, `30m limbo`, `15m IFVG`, `30m used` (stars in Standard+) | Same tooltip |
| Failed zone | Grey box kept for Setup C | Why it flipped |
| Today's levels | Thin dotted lines with tiny right-edge labels: `PDH`, `PDL`, `Asia H/L`, `London H/L`, `NY H/L` (plus `PWH/PWL`, `EQH/EQL` in Standard+) | What the level is and what a sweep of it looks like |
| Swept / broken level | The line stops and fades (amber = swept, grey = broken); its label disappears | — |
| `sweep` marker | Tiny amber tag at the sweep wick | Which level, strong or weak, and what has to happen next |
| `MSS` marker | Tiny teal/rose tag on the displacement candle | Displacement ratio, level broken, volume, what comes next |
| Armed setup | Rose box entry→stop, teal box entry→TP1, amber entry line, dashed TP2 line, tag `LONG A+ · 2 ct` | Full order: prices, R, room, targets, contracts, dollar risk, and the whole checklist |
| `skip` tag | Tiny grey tag | Plain-English reason and what the trade would have been |
| `cancelled` tag | Tiny grey tag at the entry | Why the unfilled order was pulled |
| `+2.1R` / `−1R` tag | Result of the simulated trade | How it closed |
| Background | Faint blue = kill zone, faint red = news window (lunch shading in Standard+) | — |
| Orange line | Session VWAP (resets 6:00 PM ET) | — |
| Faint grey line | Dealing-range 50% (top and bottom in Standard+) | — |
| ● AM fix / PM fix, ■ settle | Standard+ only: 5:30, 10:00, 13:30 ET | — |

Colours are inputs (group 8) if you prefer your own palette.

---

## 3. The status card

Seven rows in Clean view. Every row has a hover tooltip that explains it.

| Row | Example | Meaning |
|---|---|---|
| Status | `● TRADEABLE — NY AM kill zone · news at 10:00` | Green: trade. Amber: A+ setups only (11:00–11:30, afternoon, last 15 min of a kill zone). Red: no new trades (lunch, Friday PM, news, FOMC, Asia). |
| Bias | `Bullish ▲ · 1H and 4H agree` | The only direction you may trade. `4H disagrees → half risk, TP1 only`, `1H gap lost`, or `Neutral — sit out`. |
| Now | `At the 30m zone 4,319.9–4,332.3 — wait for a sweep of a level there` | What the playbook is waiting for next, in order: reach a zone → sweep → structure shift → 5m gap → order. Turns amber once a sweep is in, green when an order is armed or a trade is on. |
| Next zone | `30m 4,319.9–4,332.3 · 6.1 below` | The nearest with-bias zone. No zone, no trade. |
| Targets | `first obstacle 15m bear gap 4,350.1 · draw PDH 4,362.0` | TP1 and TP2 for the bias direction, measured from the current price. |
| Today | `0 of 3 trades · +0.0R · ADR 62% used` | Limits. Shows `■ STOP FOR THE DAY` or `■ WEEKLY STOP` when a limit is hit. |
| Last | `Swept Asia L inside the 30m zone` | The most recent event in plain English; hover for the last setup's prices. |

Standard view adds **Clock** (countdown to the 30m and 15m closes, VWAP side, discount/premium), **Volatility** (5m ATR, ADR, stop buffer, minimum stop) and **Risk** (dollar risk per grade). Everything view, or the *Show checklist* input, appends the 7 hard rules and 8 confluences of the last evaluated setup.

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
