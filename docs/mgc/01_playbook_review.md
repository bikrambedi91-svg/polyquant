# MGC 5-Minute Playbook — Scrutiny Report (v1 → v2)

Scope: line-by-line review of *The MGC 5-Minute Playbook* (September 2026, 16 pages).
Every number was recomputed, every rule was tested for (a) internal consistency,
(b) whether it is precise enough to execute the same way twice, and (c) whether it
can be coded. The result is `02_MGC_Playbook_v2.md`; everything changed there is
justified here.

---

## 1. Verdict in one paragraph

The v1 playbook is structurally sound. The three-layer model (4H/1H direction → 30m/15m
location → 5m timing), the "judge a gap on its own timeframe" rule, and the 2R room rule are
the right skeleton and they survive scrutiny. The contract facts, the sizing formula, the
worked example and the expectancy math are all correct (see §2). What stops it from being
the *best* version is not what it says but what it leaves undefined: roughly a dozen rules
rely on terms that two traders (or a trader and a script) would interpret differently, two
rules contradict each other, the 1-contract case breaks the management plan, and the
session map omits the gold-specific clocks (the LBMA fixes) that actually drive the 10:00 AM
reversals it alludes to. v2 fixes all of that without changing the strategy's character.

---

## 2. What checked out (verified, unchanged)

| Item | Check | Result |
|---|---|---|
| Contract: 10 oz, $0.10 tick = $1.00, $1 move = $10 | CME MGC spec | Correct |
| Hours: Sun–Fri 6:00 PM–5:00 PM ET, 60-min break at 5:00 PM | CME Globex metals | Correct |
| Liquid months Feb/Apr/Jun/Aug/Oct/Dec | Even-month cycle (G, J, M, Q, V, Z) | Correct |
| Daily settlement 1:30 PM ET | COMEX gold settlement window | Correct |
| DST change dates Nov 1 2026 / Mar 14 2027 | First Sunday Nov / second Sunday Mar | Correct |
| MES: $1.25/tick, $5/point | CME MES spec | Correct |
| Sizing table: $100/30 ticks → 3, $100/55 → 1, $150/72 → 2, $200/40 → 5 | Contracts = Risk ÷ (Stop$ × 10), round down | All four correct |
| Worked example: stop 4,414.6 = 4,415.2 − 0.60; 1R = $5.60; room 11.8/5.6 = 2.1R; size 120/56 = 2.14 → 2; risk $112; TP1 +$118; TP2 +$218; total +$336 = 3.0R | Recomputed | All correct |
| Expectancy: 0.45 × 2.4 − 0.55 × 1 = +0.53R | Recomputed | Correct |
| Break-even win rate at 2R average winner ≈ 33% | 1 ÷ (1 + 2) | Correct |
| FVG definitions (bull: high₁ < low₃; bear: low₁ > high₃) | Standard three-candle imbalance | Correct |
| Buffer 13% of 5m ATR in example ($0.60) implies 5m ATR ≈ $4.60 | Plausible for gold near $4,400 | Consistent |

---

## 3. Errors and contradictions (fixed in v2)

### 3.1 The sweep definition contradicts §5.3
§2 defines a sweep as "trades through with a wick, then closes back on the original side"
(same candle). §5.3 then says a 5m *close* below a bullish HTF gap that is reclaimed before
the HTF candle closes "is often the very liquidity sweep you're waiting for". Both cannot be
the definition. **v2 rule:** a sweep is valid if price trades through the level and a 5m body
closes back on the original side **within 3 bars (15 min)** and before the gap's own-timeframe
candle closes. Same-bar reclaim is the strong form; a 1–3 bar reclaim is the weak form and
costs one confluence point.

### 3.2 The 1-contract case breaks Section 9
The sizing table itself produces "1 contract" ($100 risk, 55-tick stop), yet management says
"At TP1 close half, move stop to breakeven". You cannot close half of one contract.
**v2 rule (execution ladder):** 1 contract → take everything at TP1 and treat any TP2 as a
separate Setup B/C re-entry; 2 contracts → 1 off at TP1, 1 runner; 3+ → one-third at TP1,
one-third at TP2, one-third trailed.

### 3.3 §5.6 "right half of the range" contradicts Setup B
§5.6 says a bullish gap only belongs on the chart if it sits in discount. Setup B (nested-gap
continuation) exists precisely for trending markets, where the pullback gaps form in premium.
Applied literally, §5.6 deletes every Setup B zone. **v2 resolution:** the premium/discount
filter is a hard filter for **Setup A** POIs only; Setup B uses structure (HH/HL) and VWAP
instead; discount/premium remains a +1 confluence for both.

### 3.4 Daily-stop wording is ambiguous with half-risk trades
"−2R, or two losses in a row" — two half-risk losses are −1R. Is the day over? **v2:** the day
ends on whichever comes first: cumulative −2R, **two consecutive losing trades of any size**,
or three trades taken. Re-entries count as trades.

### 3.5 "8:20 AM COMEX open" is a legacy time
The COMEX pit closed in 2016; Globex trades continuously. 8:20 AM ET still marks the step-up
in US volume, so the time stays, but v2 labels it correctly and adds the clocks that matter
more for gold (§4.2 below).

### 3.6 Example confluence count is fine, but the volume/VWAP confluences are silently skipped
Not an error, but the example never says whether the displacement candle had above-average
volume or whether VWAP was reclaimed. v2's worked example fills in every checklist line so it
can be used as a template.

---

## 4. Gaps (things the playbook needs but never defines)

### 4.1 Undefined terms the rules depend on
| Term used in v1 | Why it matters | v2 definition |
|---|---|---|
| "5m swing high / swing low" (MSS trigger) | The whole trigger depends on it | Pivot with 2 bars on each side (3 for a "major" swing). The MSS level is the most recent confirmed swing high formed **before** the sweep candle. |
| "Current dealing range" (premium/discount) | Decides a hard filter and a confluence | On the 1H: from the most recent confirmed swing low to swing high that bounds price (pivot 3/3). If price is above the last swing high, the top of the range is the running high. Manual override allowed. |
| "Equal highs/lows" | Major liquidity, +1 confluence | Two 5m/15m swing highs within **3 ticks or 10% of 5m ATR**, whichever is larger. |
| "London high/low" | Liquidity for NY | 2:00–8:00 AM ET (Frankfurt open to COMEX open). |
| "Asian range" | Liquidity for London | 6:00 PM–12:00 AM ET. |
| "Tiny gap" (enter at edge instead of CE) | Entry price | Gap height < 5 ticks or < 10% of 5m ATR. |
| "Large-bodied" HTF displacement (§5.6) | Which 15m/30m gaps qualify | Middle candle body ≥ 1.5× the average body of the previous 10 candles **of that timeframe**, closing in the outer 30% of its range. |
| "Nearby liquidity level at or inside the POI" | Sweep validity | Level between POI far edge − 0.5 × ATR(5m) and POI near edge + 0.5 × ATR(5m). |
| "Neutral bias" | Sit out vs. trade | No 1H body close beyond a 1H swing in the last 24 bars **and** price inside the previous day's range. |
| "Significant break" (1H bias) | Bias itself | Body close beyond a 1H pivot (3/3). |
| "Last significant obstacle cleared" | Runner logic | 15m body close through the opposing 15m gap's far edge. |
| MSS window | Old sweeps should not trigger | MSS must print within **12 bars (60 min)** of the sweep; later it expires. |
| Unfilled-order expiry | Not covered at all | Cancel if unfilled after 12 bars, at kill-zone end, or when price reaches TP1. |

### 4.2 Gold's own clock is missing
The session map is an index-futures map with London bolted on. Gold has fixed events the
playbook never mentions, and they explain the "10:00–11:00 second leg" it observes:

| Time (ET) | Event | Why it matters for MGC |
|---|---|---|
| 5:30 AM | LBMA AM gold auction (10:30 London) | Frequent London-session sweep/turn |
| 10:00 AM | LBMA PM gold auction (3:00 PM London) | The most consistent intraday inflection in gold; often the sweep that starts the 10–11 AM leg |
| 10:00 AM | US data: ISM, UMich, JOLTS, new home sales | Second data window, missing from v1's news rule |
| 11:00–11:30 AM | London physical desks close | Liquidity thins; the "be done by 11:30" rule is really this |
| 1:00 PM | US Treasury auctions (yields → gold) | Whippy on auction days |
| 1:30 PM | COMEX settlement | Reference price; volume burst |
| 2:00 PM | FOMC decision / FOMC minutes | Flat (v1 covers decision only) |
| 5:00 PM | Globex break | Last 15 minutes before it are thin |

**DST mismatch:** the EU changes clocks on the last Sunday of March and October; the US on
the second Sunday of March and first Sunday of November. For about two weeks each spring and
one week each autumn, London opens at 4:00 AM ET, not 3:00 AM. The London kill zone shifts one
hour later in those weeks. v1 mentions only the US dates.

### 4.3 Commission floor and minimum stop
At a 30-tick stop, 1R = $30 per contract. Round-turn cost on MGC is roughly $1.50–$3.50
(broker + exchange). That is 5–12% of R, paid on every trade, winners included. v1 says
"before commissions" once and moves on. **v2:** minimum stop distance 25 ticks ($2.50);
commissions are logged in R and included in expectancy; the 2R room rule is measured after
subtracting one tick of spread.

### 4.4 Setup C is referenced but never written
The decision matrix says a flipped (failed) obstacle "can host a Setup B entry" and §2 calls the
IFVG "a secondary entry zone in the new direction", but no entry model describes it. **v2 adds
Setup C (IFVG flip retest)** with its own trigger, stop and invalidation.

### 4.5 Range budget has no numbers
"If the day has covered roughly 80–100% of its average range, shrink targets or stop" is not a
rule. **v2:** ≥ 80% of ADR used → no Setup B; ≥ 100% → Setup A only, and only from an HTF POI
at the day's extreme; ≥ 130% → done for the day.

### 4.6 1H vs 4H conflict is not handled
"Bias on the 1H, confirmed on the 4H" says nothing about what to do when they disagree.
**v2:** 1H and 4H agree → full risk; 1H against 4H → trade the 1H direction at half risk and
only to the first obstacle (no runner); neither has a recent break → neutral.

### 4.7 No rule for setups near a kill-zone end
A setup that arms at 10:55 AM has five minutes of kill zone left. **v2:** no new entries in the
last 15 minutes of a kill zone unless the grade is A+.

### 4.8 Stacked POIs: which timeframe judges the zone?
If a 15m gap sits inside a 30m gap and the 15m fails while the 30m holds, v1 gives no
answer. **v2:** each gap is judged on its own timeframe; the overlap stays valid while the 30m
holds, but drops to "weakening" (half risk) once the 15m fails.

### 4.9 Contract roll guidance
"Follow your broker's roll schedule" is not actionable. **v2:** volume migrates to the next
even-month contract in the last five sessions before the front month's first notice day (the
last business day of the month before delivery). Trade the contract with the higher volume on
the 5m; chart GC of the same month if MGC prints look thin.

### 4.10 Journal metrics
v1 logs the right fields but reviews only win rate/avg R. **v2 adds** MAE/MFE in R for every
trade (which is how you find out whether the stop buffer and TP1 are placed well) and rule
adherence as a per-trade score, not a feeling.

---

## 5. Things v1 gets right that v2 deliberately keeps unchanged

- No entry without a sweep **and** a shift. It costs some winners; it removes most of the
  losers. Keep it.
- Judge gaps on their own timeframe. This is the single most valuable rule in the document.
- Stop stays put until TP1. Gold retests entries constantly; early breakeven is a leak.
- Three trades, −2R, two consecutive losses. Simple limits survive bad days.
- Leave RSI/MACD/stochastics off the chart.
- Test 50–100 replays before sim, 20–30 sim before 1 live contract.

---

## 6. What the Pine script automates and what stays manual

| Playbook element | Script | Notes |
|---|---|---|
| 30m/15m FVG detection with §5.6 filters, CE, colour/weight by TF | Automated | Non-repainting (confirmed HTF bars only) |
| Respected / Weakening / Failed / Used states judged on the gap's own TF | Automated | Updates only when the HTF candle closes |
| POI vs Obstacle labelling from bias | Automated | Bias auto (1H/4H structure) or manual |
| Liquidity: PDH/PDL, PWH/PWL, Asian, London, NY session H/L, equal H/L, 5m swings | Automated | Major vs minor tagged |
| Sweep → MSS (displacement) → 5m entry gap or IFVG | Automated | State machine per direction |
| 2R room rule to the first opposing gap or level; TP1 / TP2 | Automated | Manual DOL override |
| Stop = sweep extreme ± buffer; contracts = risk ÷ (R × point value) | Automated | Uses `syminfo.pointvalue`, works on GC too |
| 7 hard rules + 8 confluences → grade → risk multiplier | Automated (6 of 7 hard rules; "calm & within limits" is a checkbox) | SMT needs the silver symbol enabled |
| Kill zones, lunch, PM, news windows, FOMC, LBMA fixes | Automated | News times typed in daily |
| Premium/discount line, VWAP, ATR 5m, ADR and % used | Automated | Dealing range auto or manual |
| Setup B (nested-gap continuation) and Setup C (IFVG flip) | Automated candidates | Grade with the same checklist |
| Trade management: TP1 → BE, trail under 5m HLs, time stop, POI-fail exit | Simulated on chart | Drives the daily counters |
| Daily counters: trades, R, consecutive losses → "STOP" | Automated from simulated trades | Manual override inputs exist |
| Weekly draw, news calendar, bias sanity check, screenshots, journal | Manual | Judgement that code handles badly |
