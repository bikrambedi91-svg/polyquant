# The MGC 5-Minute Playbook — Version 2

**Micro Gold Futures (MGC) · Fair value gaps · Liquidity sweeps · 15m/30m confirmation**
**Prepared for Bikram · September 2026 · supersedes v1**

> Educational framework, not financial advice. Futures are leveraged and losses can exceed
> margin. Every number below is a starting parameter to be validated on Bar Replay and in
> simulation before real money. Contract specs and margins change; confirm with CME and your broker.

---

## 0. The whole playbook in four sentences

1. The **4H and 1H** decide the direction and the draw on liquidity.
2. The **30m and 15m** fair value gaps decide *where* you trade (POIs) and *where you take profit* (obstacles).
3. The **5m** decides *when*: a liquidity sweep at the POI, a displacement candle that shifts structure, and the 5m gap it leaves behind.
4. You take the trade only if the grade says so and there is at least **2R of room** before the first opposing 15m/30m gap or liquidity level.

**Golden rules:** higher timeframes decide *where*, the 5m decides *when* · a gap is judged only on its own timeframe · no sweep, no trade · no room, no trade · one trade at a time.

---

## 1. Contents

| § | Section | § | Section |
|---|---|---|---|
| 2 | How the three layers work | 10 | Setup grading checklist |
| 3 | Definitions and parameters (the rulebook) | 11 | Execution: orders, sizing, the contract ladder |
| 4 | MGC facts, costs, margins, rolls | 12 | Trade management |
| 5 | Gold's clock: sessions, kill zones, fixes, news | 13 | Risk rules and daily limits |
| 6 | Chart setup and indicators | 14 | Worked example (full checklist) |
| 7 | Bias and the draw on liquidity | 15 | Common mistakes and fixes |
| 8 | Handling 15m and 30m FVGs on a 5m chart | 16 | Journal, review, testing, scaling |
| 9 | Entry models A, B, C | 17 | One-page cheat sheet |

---

## 2. How the three layers work

Every decision passes through three layers, top down. A lower layer never overrules a higher one.

| Layer | Charts | Question | Output |
|---|---|---|---|
| 1 · Direction | 4H → 1H | Which way is price most likely to travel today? | Bias (bullish / bearish / neutral / conflicted) and a draw on liquidity (DOL) |
| 2 · Location | 30m → 15m | Where do I wait, and where will the trade stall? | POIs (with-bias gaps) and obstacles (opposing gaps and levels), marked before the session |
| 3 · Timing | 5m | Has price actually turned at my zone? | Sweep → MSS with displacement → 5m entry gap |

**Designed to do:** remove trades that lose for avoidable reasons (wrong location, no room, news, tilt), cap every loss at 1R, and leave a journal that shows what works.
**Not designed to do:** catch every move. Missing a trade costs nothing.

---

## 3. Definitions and parameters (the rulebook)

Everything in this playbook is defined precisely enough that two traders, or a trader and a script, get the same answer. Defaults are in bold; ranges are what you may tune after 50+ journaled trades.

### 3.1 Structure

| Term | Definition | Parameter |
|---|---|---|
| Swing high / low (5m) | A candle whose high is higher than the highs of *n* candles on each side (mirror for lows). Confirmed *n* bars after it prints. | **n = 2** (minor), n = 3 (major) |
| Swing high / low (1H, 4H) | Same, on that timeframe | **n = 3** |
| Break of structure (BOS) | A body close beyond the most recent same-direction swing (higher high in an uptrend) | — |
| Market structure shift (MSS) | After a sweep, a **displacement** candle closes its body beyond the most recent *opposite* 5m swing formed before the sweep candle | MSS must print within **12 bars (60 min)** of the sweep |
| Displacement | A candle (or 2–3 consecutive same-colour candles) with body ≥ *k* × the average body of the previous 10 candles, closing in the outer **30%** of its range | **k = 1.5** (5m and HTF) |
| Dealing range | On the 1H: the range from the most recent confirmed swing low to the most recent confirmed swing high that bounds current price. If price has broken above the last swing high, the top is the running high (mirror below). May be set manually. | Pivot n = 3 |
| Premium / discount | Above / below the 50% of the dealing range | — |

### 3.2 Fair value gaps

| Term | Definition | Parameter |
|---|---|---|
| FVG | Three candles. Bullish: high of candle 1 < low of candle 3. Bearish: low of candle 1 > high of candle 3. The gap is the non-overlapping range. | — |
| CE | 50% midpoint of the gap. Default entry price and the line that shows how strongly a gap holds. | — |
| Near edge / far edge | For a bullish gap: near edge = top, far edge = bottom (mirror for bearish) | — |
| Size filter (15m/30m) | Gap height ≥ *s* × ATR(14) of the gap's own timeframe | **s = 0.25** |
| Displacement filter (15m/30m) | Middle candle qualifies as displacement on its own timeframe (3.1) | k = 1.5 |
| Volume tag | Middle candle volume ≥ its 20-bar average | quality +1 |
| Session tag | Middle candle formed 2:00 AM–11:30 AM ET | quality +1 |
| Fresh | Not traded through and reacted to at most once (≤ 1 prior touch) | — |
| Touch / reaction | Price enters the gap from outside (one entry = one reaction, however many bars it stays) | — |
| Tiny gap | Height < 5 ticks or < 10% of 5m ATR → enter at the near edge instead of the CE | — |
| Stacked zone | A 15m gap overlapping a 30m gap; the overlap is the POI, its midpoint the key level | — |
| Max per side | Keep at most **3** qualifying HTF gaps above and 3 below price; delete the rest | — |

### 3.3 Gap states (judged only with candles of the gap's own timeframe)

| State | What you see on the gap's own timeframe | Action |
|---|---|---|
| **Respected** | Wicks into the gap; bodies close back outside it or at least beyond the CE | Valid POI. Drop to the 5m, wait for sweep + MSS. |
| **Weakening** | A body closes past the CE but not through the far edge | Still a POI, but demand an A or A+ and cap risk at half. Sticky: it does not go back to Respected. |
| **Failed (IFVG)** | A body closes through the far edge | No more entries in that direction. The gap flips role and becomes a Setup C candidate from the other side. |
| **Used** | Two prior reactions, or fully traded through and returned | Delete or downgrade. Not a POI. |
| **Pending** | A 5m close has gone through the far edge but the 15m/30m candle is still open | Do nothing until that candle closes. A fast reclaim is a sweep, not a failure. |

A 15m gap inside a 30m gap: each is judged on its own timeframe. The overlap stays a POI while the 30m holds; if the 15m fails while the 30m holds, treat the zone as Weakening.

### 3.4 Liquidity

| Level | Definition | Class |
|---|---|---|
| PDH / PDL | Previous session's high / low (session = 6:00 PM–5:00 PM ET) | Major |
| PWH / PWL | Previous week's high / low | Major |
| Asian high / low | 6:00 PM–12:00 AM ET | Major |
| London high / low | 2:00 AM–8:00 AM ET | Major |
| NY session high / low | Running high / low since 8:00 AM ET (becomes major once 30+ min old) | Major |
| Equal highs / lows | Two 5m or 15m swings within **max(3 ticks, 10% of 5m ATR)** of each other | Major |
| 5m swing high / low | Minor pivot (n = 2) formed in the last 60 bars | Minor |
| Liquidity sweep | Price trades through a level with a wick and a 5m body closes back on the original side **within 3 bars** and before the POI's own-timeframe candle closes. Same-bar reclaim = strong sweep; 2–3 bar reclaim = weak sweep. | — |
| Sweep at the POI | The swept level lies between the POI's far edge − 0.5 × ATR(5m) and its near edge + 0.5 × ATR(5m), and the sweep candle touched the POI | Hard rule |
| Draw on liquidity (DOL) | The nearest untouched major level or unfilled 1H/4H gap in the bias direction beyond the first obstacle | TP2 |

### 3.5 Risk parameters

| Parameter | Default | Range |
|---|---|---|
| Risk per trade | **0.5%** of account until 50 journaled trades, then up to 1% | 0.25–1% |
| Stop buffer beyond sweep extreme | **12%** of 5m ATR(14), never less than **3 ticks** | 10–15% |
| Minimum stop distance | **25 ticks ($2.50)** — below this, commissions and spread eat the edge | 20–40 |
| Minimum room to first obstacle | **2.0R**, measured from entry to the obstacle's near edge minus 1 tick | 2.0–2.5 |
| Preferred distance to DOL (TP2) | ≥ 3R | — |
| Unfilled order expiry | **12 bars** after arming, or kill-zone end, or price reaches TP1 | 6–12 |
| Time stop | Flat if the trade has not reached TP1 in **60 minutes** and the kill zone has ended | 45–60 |
| Trades per day | **3** (re-entries count) | 2–3 |
| Daily stop | −2R cumulative, or 2 consecutive losing trades of any size | — |
| Weekly stop | −5R → no trading until the weekly review is written | — |
| Good-day rule | ≥ +3R → stop, protect the day (optional but recommended in month 1–3) | — |
| Kill-zone tail | No new entries in the last 15 minutes of a kill zone unless A+ | — |

---

## 4. MGC facts, costs, margins, rolls

| Item | Value |
|---|---|
| Exchange / symbol | COMEX (CME Group) · MGC |
| Contract size | 10 troy oz (one-tenth of GC) |
| Tick | $0.10/oz = **$1.00** per contract |
| $1.00 move | **$10** per contract |
| Trading hours | Sunday 6:00 PM – Friday 5:00 PM ET, daily 60-min break 5:00–6:00 PM ET |
| Daily settlement | 1:30 PM ET |
| Liquid months | Feb (G), Apr (J), Jun (M), Aug (Q), Oct (V), Dec (Z) |
| Roll | Volume migrates to the next even month during the last ~5 sessions before the front month's first notice day (the last business day of the month before delivery). Trade whichever contract shows more 5m volume; switch charts the day the back month wins. |
| Margin | Set by CME and your broker and changes with volatility. Day-trade margins are typically a few hundred dollars or less; overnight maintenance is in the low thousands. Check before every session; never let margin decide size. |
| Round-turn cost | Roughly $1.50–$3.50 per contract (commission + exchange + NFA). Log it in R. |
| Spread | Usually 1 tick in London/NY hours, 2–4 ticks in Asia and after 4:00 PM ET. Use limit orders for entries; stops are stop-market. |
| GC vs MGC | Same month tracks tick for tick. Chart GC for volume reads if MGC looks thin; execute on MGC. 10 MGC = 1 GC. |

**Position sizing (always from the stop):**

```
Contracts = floor( Risk$ × grade multiplier ÷ (Stop distance in $ × 10) )
```

If the result is 0, the stop is too wide for your budget: skip. Never raise risk to make a trade fit.

| Risk budget | Stop | Risk / contract | Contracts |
|---|---|---|---|
| $100 | $3.00 (30 ticks) | $30 | 3 |
| $100 | $5.50 (55 ticks) | $55 | 1 |
| $150 | $7.20 (72 ticks) | $72 | 2 |
| $200 | $4.00 (40 ticks) | $40 | 5 |

**Coming from MES:** the tick is $1.00 not $1.25; $1 of gold = $10 not $5 per point; gold's centre of gravity is London, not New York; and gold's drivers are the dollar, real yields, Fed expectations and geopolitics. 8:30 AM ET data hits both markets; 10:00 AM ET hits gold harder (§5).

---

## 5. Gold's clock: sessions, kill zones, fixes, news

### 5.1 Session map (New York time)

| Time (ET) | What gold tends to do | Your plan |
|---|---|---|
| 6:00 PM–12:00 AM · Asia | Quiet; builds the Asian range | Mark Asian high/low. Liquidity for later. No trades. |
| 12:00–2:00 AM | Thin | No trades. |
| **2:00–5:00 AM · London kill zone** | First real volume; commonly runs the Asian high or low then turns | Tradable once you have tested it and you are rested. |
| 5:30 AM · **LBMA AM auction** (10:30 London) | Frequent sweep/turn | Watch for a sweep into a POI. |
| 5:00–8:00 AM | Slower; builds the London range | Mark London high/low. |
| 8:00–8:20 AM | US desks arrive; pre-data positioning | Plan written, orders drafted. |
| 8:30 AM · **US tier-1 data** | CPI, PPI, NFP, jobless claims, retail sales, GDP, PCE | No entries 8:15–8:45. The spike often *becomes* the sweep. |
| **8:30–11:00 AM · NY AM kill zone** | The best-quality moves of the day | Primary window. |
| 10:00 AM · **LBMA PM auction** (3:00 PM London) + US 10:00 data (ISM, UMich, JOLTS) | The most consistent intraday inflection in gold; the "second leg" | Second-chance window 10:00–11:00. No entries 9:55–10:10 on tier-1 10:00 data days. |
| 11:00–11:30 AM | London physical desks close; liquidity thins | Be done by 11:30 unless an A+ trade is running. |
| 12:00–1:30 PM · NY lunch | Chop and false breaks | No new trades. |
| 1:00 PM · Treasury auctions (some days) | Yield jolt → gold jolt | No entries 12:55–1:15 on auction days. |
| 1:30 PM · COMEX settlement | Volume burst, then thinner trade that can reverse the morning | PM window 1:30–4:00: A+ only, or done. |
| 2:00 PM · **FOMC decision / minutes** | Fed | Flat. No new trades until the press conference ends (≈ 3:30 PM). |
| 4:00–5:00 PM | Thin, positioning into the break | No trades. |

### 5.2 Kill zones and no-trade windows (defaults)

| Window | ET | Rule |
|---|---|---|
| London kill zone | 2:00–5:00 AM | Tradable |
| NY AM kill zone | 8:30–11:00 AM | Primary |
| NY lunch | 12:00–1:30 PM | No new trades |
| NY PM | 1:30–4:00 PM | A+ only |
| Tier-1 data | ±15 min around 8:30 and 10:00 AM releases | No entries |
| FOMC day | Flat from 1:45 PM until the presser ends | No entries |
| Friday | No new trades after 12:00 PM | Thin, weekend risk |
| Holiday / half sessions | No trades | Thin |

**DST mismatch:** Europe changes clocks on the last Sunday of March and October; the US on the second Sunday of March and first Sunday of November. During the ~2 weeks in spring and ~1 week in autumn when they differ, London opens at 4:00 AM ET and the London kill zone runs 3:00–6:00 AM ET. The LBMA fixes shift the same way. Recheck local times on Nov 1 2026 and Mar 14 2027 (US), and Oct 25 2026 and Mar 28 2027 (Europe).

### 5.3 Weekly news map
Block these before the week starts: CPI, PPI, NFP (first Friday), FOMC decisions and minutes, PCE, GDP, retail sales, ISM manufacturing/services, JOLTS, jobless claims (every Thursday 8:30), Treasury 10y/30y auctions, scheduled Fed chair testimony. Geopolitical headlines cannot be scheduled: if gold moves more than 1 × 5m ATR in a single candle on no scheduled news, stand aside for 15 minutes.

---

## 6. Chart setup and indicators

| Chart | Job | On it |
|---|---|---|
| 4H and Daily (prep only) | Weekly draw | PWH/PWL, unfilled Daily/4H gaps, major swings |
| 1H | Direction | 1H swings, PDH/PDL, fresh 1H gaps, dealing range 50% |
| 15m | Location | 30m and 15m gaps with CE lines, candle countdown |
| 5m | Timing | HTF gap boxes projected on, 5m gaps, session highs/lows, VWAP, volume |
| Silver 5m (optional) | SMT | Same session levels as gold |

**Colour code:** green bullish, red bearish. 30m gaps: strongest fill, 2px border. 15m: medium fill, 1px. 5m: faint fill, dotted border. Dashed CE line on every 15m/30m gap. A failed gap is either deleted or re-drawn as a grey IFVG.

**Indicators (lean):**

| Tool | Setting | Use |
|---|---|---|
| Session VWAP | Resets at 6:00 PM ET | Bias filter and confluence: reclaim after bullish MSS strengthens a long |
| ATR(14) 5m | 14 | Stop buffer, tiny-gap test, sweep tolerance, EQH/EQL tolerance |
| ATR(14) 15m / 30m | 14 | Gap-size filter for that timeframe |
| ADR: ATR(14) Daily | 14 | Range budget (§13.3) |
| Volume + 20 SMA | 20 | Displacement candles should print above average; read GC volume if MGC is thin |
| Candle countdown | 15m and 30m | Never guess an HTF close |
| Economic calendar | High-impact US | No-trade windows |
| MTF FVG script (`MGC_Playbook.pine`) | — | Everything above, plus the checklist, on one chart |
| Leave off | RSI, MACD, stochastics | Lag on the 5m and argue with a liquidity method |

**Levels to mark before every session:** PDH/PDL · PWH/PWL · Asian H/L · London H/L (for NY) · equal highs/lows on 5m/15m · up to 3 qualifying 30m/15m gaps per side with CE · the 50% of the dealing range.

---

## 7. Bias and the draw on liquidity

### 7.1 Bias scorecard (1H, checked against the 4H)

| Check | Bullish | Bearish |
|---|---|---|
| Last 1H structural break (body close beyond a 1H swing, n = 3) | Up | Down |
| Price vs the last 1H with-bias gap | Holding above the last 1H bullish gap (no 1H body close through its bottom) | Holding below the last 1H bearish gap |
| 4H last structural break | Up | Down |
| Position in the 1H dealing range (for the trade you want) | Discount for longs | Premium for shorts |

| Result | Bias | Risk |
|---|---|---|
| 1H and 4H breaks agree | Bullish / Bearish | Full (per grade) |
| 1H against 4H | Conflicted → trade the 1H direction only | Half risk, TP1 only, no runner |
| No 1H break in the last 24 bars **and** price inside the previous day's range | Neutral | Sit out, or A+ sweeps of the range extremes (PDH/PDL, Asian/London H/L) at half risk |
| 1H bias gap has failed (body close through) | Downgrade one step | Re-assess at the next 1H close |

### 7.2 Draw on liquidity
The DOL is the nearest untouched major level in the bias direction beyond the first obstacle: PDH/PDL, Asian or London high/low, equal highs/lows, PWH/PWL, or an unfilled 1H/4H gap. It is your TP2 and the sanity check on the bias: if the DOL is less than 3R away, expect a scalp, not a runner.

---

## 8. Handling 15m and 30m FVGs on a 5m chart

**The golden rule.** Higher timeframes decide where; the 5m decides when. When a 5m signal and a 15m/30m gap disagree, the higher timeframe wins, and its opposing gap becomes your first target rather than your problem.

### 8.1 One job per timeframe

| Timeframe | Job | Rule |
|---|---|---|
| 30m | Primary zones | The strongest gaps on the chart; outrank 15m and 5m signals |
| 15m | Refinement | Narrows where inside a 30m move to look; holds the nearest obstacles |
| 5m | Trigger only | Never a reason to trade by itself |

### 8.2 Label every gap before the session
- **POI:** agrees with bias (bullish gap *below* price when bullish; bearish gap *above* price when bearish). Where you wait.
- **Obstacle:** opposes bias, sits between entry and DOL. Where TP1 lives. Never an entry.
- **Limbo:** a with-bias gap price has moved through on the 5m while its own candle is open. Wait.
- **IFVG:** failed, role flipped. Setup C candidate only.
- Cannot label it? It does not belong on the chart.

### 8.3 Judge every gap on its own timeframe
A 5m close through a 30m gap does not break it; only a 30m body close does. 30m candles close on :00 and :30; 15m on :00/:15/:30/:45. When price is inside an HTF gap, stop reacting to 5m closes and wait for that timeframe's close. A 5m close through the far edge that is reclaimed before the HTF close is usually the sweep you were waiting for.

### 8.4 Which gaps deserve a place (filters, §3.2)
Displacement on its own timeframe · fresh (≤ 1 prior touch) · size ≥ 0.25 × that timeframe's ATR · **for Setup A POIs:** bullish gaps in discount, bearish gaps in premium · bonus: formed 2:00–11:30 AM ET, above-average volume, came out of a sweep or broke structure. Stacked 15m-inside-30m gaps are the best zones; the best 5m entries come when the 5m entry gap also sits inside the overlap.

### 8.5 The room rule: 2R before the first obstacle
From entry to the near edge of the first opposing 15m/30m gap **or** opposing major level, minus 1 tick. Less than 2R → skip. 2R or more → take it, TP1 one tick in front of that edge.

Why 2R: with winners averaging 2R you break even at a 33% win rate; at 1R you need more than 50%, before costs.

### 8.6 Decision matrix

| Situation | Meaning | Action |
|---|---|---|
| Price trades into a with-bias 15m/30m gap | At a POI | Drop to the 5m. Sweep → MSS → enter at the 5m gap. |
| Price between zones | No location edge | Wait. |
| 5m long setup, opposing gap < 2R above | Obstacle too close | Skip; log it. |
| 5m long setup, opposing gap ≥ 2R above | Room | Take it; TP1 at the near edge. |
| 5m closes through a 30m POI, 30m still open | Limbo | Wait for the 30m close. Fast reclaim = sweep. |
| 15m/30m body closes through the POI's far edge | Failed (IFVG) | Cancel entries there. Watch the other side (Setup C). |
| 15m inside 30m | Stacked | Trade the overlap; its midpoint is the key level. |
| 15m fails, 30m holds | Weakening | Half risk, A/A+ only. |
| Bullish and bearish HTF gaps both near, bias unclear | Two-way chop | A+ sweeps of the range extremes at half risk, or sit out. |
| In a trade, price reaches an opposing gap | Obstacle | Take TP1. If the 5m shifts against you there, close the rest. |
| 15m body closes through the opposing 15m gap | Obstacle cleared, flips | Hold the runner. The flipped gap can host Setup C. |
| ADR ≥ 80% used before entry | Range budget | No Setup B. ≥ 100%: Setup A only from an HTF POI at the day's extreme. ≥ 130%: done. |

Shorts mirror everything.

---

## 9. Entry models

### Setup A · Sweep and Shift (reversal from a POI) — the primary model
1. Price trades into a with-bias, non-failed 15m/30m POI during a kill zone.
2. A liquidity level at or inside the POI is swept (§3.4).
3. Within 12 bars, a 5m displacement candle closes beyond the last opposite 5m swing formed before the sweep: the MSS.
4. Entry: limit at the CE of the 5m gap the displacement left (near edge if tiny). If no 5m gap forms within 3 bars, use the inverted 5m gap the displacement closed through (alternate trigger).
5. Stop: beyond the sweep extreme plus the buffer (§3.5). Minimum 25 ticks.
6. TP1 at the first obstacle (≥ 2R). TP2 at the DOL.
7. Invalid if: the POI fails on its own timeframe; the "shift" has no displacement; price reaches TP1 unfilled; a 5m body closes through the far side of the entry gap before the fill; the order is 12 bars old.

### Setup B · Nested-gap continuation
Use when bias is clear and price has already displaced away from a POI (you missed A, or the market is trending).
1. 5m making HH/HL (longs) and trading above VWAP.
2. First pullback after a fresh MSS into a 5m gap that overlaps a 15m (or 30m) with-bias gap; ideally the pullback takes a minor 5m swing low (internal liquidity).
3. Entry: limit at the CE of the overlap, or wait for a 5m candle to wick in and close back above the CE.
4. Stop: below the pullback low plus buffer. Minimum 25 ticks.
5. TP1 at the recent swing high or next obstacle (≥ 2R). TP2 at the DOL.
6. Only the first pullback after the MSS. Not if ADR ≥ 80% used. Premium/discount is a confluence, not a filter, for B.

### Setup C · IFVG flip retest
Use when a 15m/30m gap has failed on its own timeframe and now sits *with* your bias (a bearish gap you were long into that just got closed above by a 15m body → new support).
1. Bias agrees with the flip and the DOL is beyond.
2. Price returns into the IFVG within 24 bars of the flip (first retest only).
3. A 5m candle wicks into the IFVG and closes back beyond its CE, ideally after sweeping a minor 5m swing.
4. Entry: limit at the CE of the IFVG. Stop: beyond the IFVG's far edge plus buffer. Min 25 ticks.
5. TP1 next obstacle (≥ 2R). TP2 DOL.
6. Invalid if a 15m body closes back through the IFVG (flip failed) or the retest is the second one.

Grade B and C with the same checklist as A. For B and C the "liquidity swept" hard rule is satisfied by a minor 5m swing; a major level counts as a confluence as usual.

---

## 10. Setup grading checklist

Run it before every order. Hard rules are pass/fail; confluences decide size.

**Hard rules — all seven must be yes**
1. Bias is Bullish/Bearish (or Conflicted at half risk) and this trade goes with it.
2. Price is at a with-bias 15m/30m POI that has not failed on its own timeframe (Respected or Weakening).
3. A liquidity level was swept at or inside the POI, reclaimed within 3 bars.
4. 5m MSS with displacement (body close beyond the last opposite swing, within 12 bars of the sweep).
5. ≥ 2R of room to the first opposing 15m/30m gap or major level; stop ≥ 25 ticks.
6. No tier-1 news within 15 minutes; not in lunch; not in the last 15 minutes of the kill zone (unless A+).
7. Inside today's limits (trades < 3, R > −2, not two losses in a row) and calm.

**Confluences — +1 each**
- 15m and 30m gaps overlap at the POI.
- The swept level is major (PDH/PDL, PWH/PWL, Asian/London/NY H/L, equal H/L).
- Entry in discount (longs) / premium (shorts) of the 1H dealing range.
- Displacement candle volume above its 20-bar average.
- VWAP reclaimed after the MSS (longs) / lost (shorts).
- Inside a kill zone (2:00–5:00 AM or 8:30–11:00 AM ET).
- First touch of the POI.
- SMT: silver did not confirm gold's sweep.

**Penalties:** weak sweep (2–3 bar reclaim) −1 · POI Weakening → cap at half risk · Conflicted bias → cap at half risk, TP1 only.

| Grade | Requirement | Risk |
|---|---|---|
| A+ | All hard rules + ≥ 4 confluences (after penalties) | Full (1R) |
| A | All hard rules + 2–3 | Half (0.5R) |
| B | All hard rules + 0–1 | No trade until 50+ journaled trades show B pays; then quarter risk |
| Skip | Any hard rule missing | Log the skip |

---

## 11. Execution: orders, sizing, the contract ladder

- **Entry:** limit at the CE (near edge if tiny). Never market into a setup.
- **Stop:** stop-market at the sweep extreme ± buffer, placed with the entry (bracket/OCO).
- **Targets:** TP1 limit one tick in front of the obstacle; TP2 limit at the DOL.
- **Size:** `floor(Risk$ × multiplier ÷ (Stop$ × 10))`, multiplier 1.0 (A+), 0.5 (A), 0.25 (B, if allowed).
- **Contract ladder (fixes the "close half of one contract" problem):**

| Contracts | At TP1 | Runner |
|---|---|---|
| 1 | Close all. Re-enter via Setup B/C if the runner leg sets up. | none |
| 2 | Close 1, stop to breakeven | 1 to TP2 or trailed |
| 3+ | Close ⅓, stop to breakeven | ⅓ to TP2, ⅓ trailed under 5m HLs |

- **Cancel the order** if: price reaches TP1 unfilled; a 5m body closes through the far side of the entry gap; 12 bars pass; the kill zone ends; a news window starts.

---

## 12. Trade management

| Moment | Action |
|---|---|
| Before TP1 | Leave the stop alone. Gold retests the entry gap constantly; early breakeven turns winners into scratches. |
| At TP1 | Ladder (§11). Stop to breakeven on the remainder. |
| Runner | Hold for TP2, or trail one tick under each new 5m higher low that forms after displacement (above each lower high for shorts). Never trail tighter than 1 × 5m ATR. |
| Exit early | A 15m body closes back through your POI against you · price reaches an opposing gap and the 5m shifts against you there · 60 minutes without TP1 after the kill zone has ended · a tier-1 news window starts while you are still before TP1 (unless A+ and past 1R open profit) |
| Obstacle cleared | A 15m body closes through the opposing 15m gap → hold the runner; that gap is now a Setup C zone. |
| One re-entry | After a stop-out, once, at the same POI, only if it is still Respected/Weakening on its own timeframe and a fresh sweep + MSS print. The re-entry counts toward the three trades. |
| Never | Widen a stop, add to a loser, re-enter a failed zone, or take a second re-entry. |

---

## 13. Risk rules and daily limits

### 13.1 Limits
| Rule | Setting |
|---|---|
| Risk per trade | 0.5% until 50 journaled trades; then ≤ 1% |
| Trades per day | 3, including re-entries |
| Daily stop | −2R cumulative **or** 2 consecutive losing trades, whichever first |
| Weekly stop | −5R → stop until the weekly review is written |
| Good-day rule | +3R → consider stopping |
| Thin markets | No trades at lunch, Friday after 12:00 PM, holidays, last 15 min before the 5:00 PM break |
| Prop / funded accounts | Daily stop at most 50% of the firm's daily loss limit; know the trailing drawdown before every session |

### 13.2 Expectancy
`Expectancy (R) = win rate × avg win (R) − loss rate × avg loss (R) − cost (R)`
Example: 45% winners at +2.4R, 55% losers at −1R, cost 0.06R per trade → 1.08 − 0.55 − 0.06 = **+0.47R** per trade. At $100 risk that is ≈ $47 per trade over a large sample. Cost matters: at a 30-tick stop, $2.50 round-turn = 0.08R.

### 13.3 Range budget (ADR)
Range used = (today's high − today's low) ÷ ATR(14, Daily).
- < 80%: all setups.
- 80–100%: no Setup B; Setup A and C only.
- 100–130%: Setup A only, from an HTF POI at the day's extreme, A+ only.
- ≥ 130%: done for the day.

---

## 14. Worked example: Setup A long (full checklist)

**Plan written 8:00 AM ET.** 1H bias bullish (yesterday's NY session closed above a 1H swing high; 4H last break up → agree). Dealing range 4,398.0–4,442.0, 50% = 4,420.0. DOL = PDH 4,442.0. POI = 30m bullish gap 4,412.0–4,418.0 (CE 4,415.0; size $6 ≈ 0.55 × 30m ATR; formed 9:00 AM yesterday on above-average volume; untouched). Asian low 4,416.5 sits inside it. Obstacle = 15m bearish gap 4,432.0–4,436.0. ADR $38, range used at 8:00 AM: 40%. News: jobless claims 8:30 (blocked 8:15–8:45); no 10:00 data.

**IF** price sweeps the Asian low into the 30m gap and the 5m shifts up → long, TP1 4,431.9, TP2 4,442.0. **IF** a 30m body closes below 4,412.0 → no longs today.

**What happened**
1. **Location** 8:50–9:05: price sells off into the 30m gap. Touch count = 1 (first touch).
2. **Sweep** 9:10: a 5m wick runs to 4,415.2, through the Asian low 4,416.5, and the candle closes at 4,417.1 — same-bar reclaim (strong). The 9:00 30m candle is still open; the 9:30 close later prints at 4,421.0, above the CE → Respected.
3. **Shift** 9:25: displacement candle 4,418.4 → 4,423.6 (body $5.20 vs 10-bar average $2.10 = 2.5×, close in the top 15% of its range, volume 1.4× the 20-bar average) closes above the 5m swing high 4,422.0 formed at 8:55. MSS. It leaves a 5m gap 4,419.0–4,421.4, CE 4,420.2. VWAP 4,419.6 reclaimed.
4. **Entry** limit 4,420.2. Stop 4,414.6 (sweep low − $0.60, 13% of 5m ATR $4.60; 56 ticks ≥ 25 ✓). 1R = $5.60.
5. **Room** 4,431.9 − 4,420.2 = $11.70 = 2.09R ✓. TP2 4,442.0 = 3.9R.
6. **Checklist** Hard rules 7/7. Confluences: overlap ✗ (no 15m inside), major level ✓, discount ✓ (4,420.2 < 4,420.0? No — 4,420.2 is 0.2 above the 50%. Strictly ✗). Volume ✓, VWAP ✓, kill zone ✓, first touch ✓, SMT ✓ (silver held above its Asian low). **Six confluences → A+.** (v1 counted "discount" loosely; the strict answer changes nothing here, but be honest in the journal.)
7. **Size** $120 × 1.0 ÷ ($5.60 × 10) = 2.14 → **2 MGC**, real risk $112. Fills on the 9:45 pullback.
8. **TP1** 10:20: 4,431.9 tagged. Close 1 for +$117. Stop to 4,420.2.
9. **TP2** 11:00: the 15m candle closes at 4,437.2, above 4,436.0 → obstacle failed, runner stays. 11:10: PDH 4,442.0 hit, +$218.

**Result** +$335 on $112 risk ≈ **+3.0R**. Cost: 2 contracts × $2.50 = $5 (0.04R).

**Would have been a skip if:** the 15m bearish gap started at 4,429.0 (1.6R) · a 30m body had closed below 4,412.0 before the shift · CPI at 8:30 and the MSS printed at 8:40 · this was the POI's third touch · the 9:25 candle's body was $2.40 (1.1× average: no displacement).

---

## 15. Common mistakes and fixes

| Mistake | Fix |
|---|---|
| Taking every 5m FVG | 5m gaps are triggers. No 15m/30m POI, no trade. |
| Buying under a 30m bearish gap / selling over a 30m bullish one | Room check before every entry. |
| Calling a 30m gap broken on a 5m close | Wait for the 30m close. Use the countdown. |
| Entering on the sweep, before the shift | The sweep sets up; the MSS triggers. |
| Trading an MSS an hour after the sweep | 12-bar window. Old sweeps expire. |
| Too many boxes | Filters (§8.4), three per side, clear used gaps daily. |
| Expecting full fills | Many gaps only reach the CE. Enter at the CE; stop beyond the sweep. |
| Trading the 8:30 / 10:00 candle | Wait 15 minutes; the spike is often the sweep. |
| Trading lunch or after 11:30 | Done by 11:30 unless A+ running. |
| Breakeven too early | Only after TP1. |
| Closing "half" of one contract | Use the ladder (§11). |
| Revenge trading | −2R or two losses. Close the platform. |
| Changing rules after three losses | Judge on 30–50 trades. One rule change at a time. |
| Trusting the script's bias blindly | The script scores structure; you decide the draw. Override when the higher-timeframe story says so, and log why. |

---

## 16. Journal, review, testing, scaling

### 16.1 Log every trade (and every skipped A+)
Date/session · bias and DOL · POI (TF, range, state, touch #) · level swept (class) · sweep type (strong/weak) · MSS time · displacement ratio · entry/stop/TP1/TP2 · setup A/B/C · grade and confluence list · contracts · planned R to TP1 · realized R · **MAE and MFE in R** · costs in R · rule adherence (each hard rule followed? y/n) · emotional state 1–5 · one lesson · screenshots 1H/15m/5m.

### 16.2 Weekly review (Sunday, with the weekly prep)
Win rate, avg win, avg loss, expectancy after costs · results by setup, grade, session, POI timeframe, day of week, sweep type · MAE distribution (if 80% of winners never go past −0.5R, the buffer may be too wide; if losers regularly bounce from −1.1R, it is too tight) · MFE distribution (if most winners reach 2.5R+, TP1 is too close) · rule adherence ≥ 90%.

### 16.3 Test before you trust
1. **Backtest** 50–100 setups on Bar Replay with exactly these rules. The script's armed setups give you the candidates; you still judge bias and POI choice by hand.
2. **Simulate** 20–30 trades in real time during your window.
3. **Go live** with 1 MGC for 30–50 trades.
4. **Scale** one contract at a time, only after positive expectancy and ≥ 90% adherence over 50+ live trades. Ten MGC equal one GC.

Change one rule at a time, only when the journal says so.

---

## 17. One-page cheat sheet

**Golden rules** · 30m/15m decide *where*, the 5m decides *when* · judge a gap only on its own timeframe · no sweep, no trade · no 2R room, no trade · one trade at a time

**Trigger** · at a with-bias POI → sweep (reclaim ≤ 3 bars) → displacement MSS (≤ 12 bars) → 5m gap → limit at CE → stop beyond sweep + 12% ATR (≥ 25 ticks) → TP1 first obstacle (≥ 2R) → TP2 DOL

**Kill zones (ET)** · London 2:00–5:00 · NY AM 8:30–11:00 (second chance 10:00–11:00) · no trades 12:00–1:30 · PM A+ only · flat ±15 min around 8:30 / 10:00 data, flat into 2:00 PM Fed

**Grade** · A+ ≥ 4 confluences = full · A 2–3 = half · B 0–1 = no trade · any hard rule missing = skip

**Ladder** · 1 contract: all at TP1 · 2: one at TP1, one runs · 3+: thirds

**Stop for the day** · −2R · two losses in a row · three trades · ADR ≥ 130% used

**Size** · Contracts = floor(Risk$ × multiplier ÷ (Stop$ × 10)) · never a fixed count
