"""Tab 8 — Live Decisions: real-time pipeline reasoning chain.

Shows every step of the bot's decision process:
- Market scan results
- Per-model signals and ensemble output
- Each filter check (pass/reject with values)
- Edge calculation details
- Risk checks
- Final trade execution or rejection reason

Auto-refreshes with the dashboard. Newest cycle at top.
"""

import json
from collections import defaultdict

import streamlit as st
import pandas as pd
from sqlalchemy import desc
from sqlalchemy.orm import Session

from database.models import PipelineDecision


# ── Color helpers ──

_DECISION_COLORS = {
    "PASS": "#00cc96",   # green
    "REJECT": "#ef553b",  # red
    "TRADE": "#636efa",   # blue
    "INFO": "#ffa15a",    # orange
}

_STAGE_ICONS = {
    "market_scan": "🔍",
    "signals": "📡",
    "filter_excluded_asset": "🚫",
    "filter_confidence": "💪",
    "filter_yes_price": "📊",
    "filter_model_agreement": "🤝",
    "filter_mtf_confirmation": "⏱",
    "filter_all_passed": "✅",
    "edge": "📐",
    "risk": "🛡",
    "execute": "🎯",
    "summary": "📋",
    "filter_market_match": "🗺",
}


def _get_icon(stage: str) -> str:
    return _STAGE_ICONS.get(stage, "▪")


def _decision_badge(decision: str) -> str:
    color = _DECISION_COLORS.get(decision, "#888")
    return f'<span style="background-color:{color};color:white;padding:2px 8px;border-radius:4px;font-size:0.8em;font-weight:bold">{decision}</span>'


def render_decisions(session: Session, settings):
    st.header("Live Decision Analysis")
    st.caption("Real-time view of the bot's decision process. Each cycle shows why trades were taken or rejected.")

    # ── Get latest cycles ──
    cycles_to_show = st.selectbox("Cycles to show", [1, 3, 5, 10], index=1, key="dec_cycles")

    # Get distinct cycle IDs (newest first)
    cycle_ids_query = (
        session.query(PipelineDecision.cycle_id)
        .distinct()
        .order_by(desc(PipelineDecision.created_at))
        .limit(cycles_to_show)
        .all()
    )
    cycle_ids = [c[0] for c in cycle_ids_query]

    if not cycle_ids:
        st.warning("No decision logs yet. The bot needs to run at least one cycle with decision logging enabled.")
        st.info("If the bot is running, restart it to enable decision logging (it was just added).")
        return

    # Fetch all decisions for these cycles
    decisions = (
        session.query(PipelineDecision)
        .filter(PipelineDecision.cycle_id.in_(cycle_ids))
        .order_by(desc(PipelineDecision.created_at))
        .all()
    )

    # Group by cycle
    cycles = defaultdict(list)
    for d in decisions:
        cycles[d.cycle_id].append(d)

    # ── Render each cycle ──
    for cycle_id in cycle_ids:
        cycle_decisions = cycles.get(cycle_id, [])
        if not cycle_decisions:
            continue

        # Sort by created_at within cycle
        cycle_decisions.sort(key=lambda x: x.created_at)

        # Get cycle summary
        summary = next((d for d in cycle_decisions if d.stage == "summary"), None)
        first_ts = cycle_decisions[0].created_at.strftime("%H:%M:%S UTC") if cycle_decisions else "?"
        tf = cycle_decisions[0].timeframe if cycle_decisions else "?"

        # Cycle header
        summary_text = ""
        if summary:
            try:
                det = json.loads(summary.details_json) if summary.details_json else {}
                summary_text = (
                    f"  |  Regime: **{det.get('regime', '?')}**"
                    f"  |  Markets: **{det.get('markets_found', 0)}**"
                    f"  |  Signals: **{det.get('signals_generated', 0)}**"
                    f"  |  Trades: **{det.get('trades_opened', 0)}**"
                )
            except json.JSONDecodeError:
                pass

        with st.expander(
            f"{'🎯' if summary and summary.decision == 'TRADE' else '⏸'} "
            f"Cycle {cycle_id} — {first_ts} — {tf}{summary_text}",
            expanded=(cycle_id == cycle_ids[0]),  # Expand newest
        ):
            _render_cycle(cycle_decisions)


def _render_cycle(decisions: list):
    """Render all decisions within one cycle."""

    # Separate by type
    scan = [d for d in decisions if d.stage == "market_scan"]
    signals = [d for d in decisions if d.stage == "signals"]
    filters = [d for d in decisions if d.stage.startswith("filter_")]
    edges = [d for d in decisions if d.stage == "edge"]
    risks = [d for d in decisions if d.stage == "risk"]
    trades = [d for d in decisions if d.stage == "execute"]

    # ── 1. Market Scan ──
    if scan:
        st.markdown("#### 🔍 Market Scan")
        for s in scan:
            try:
                det = json.loads(s.details_json) if s.details_json else {}
                markets = det.get("markets", [])
                if markets:
                    rows = []
                    for m in markets:
                        rows.append({
                            "Asset": m.get("asset", "?"),
                            "TF": m.get("timeframe", "?"),
                            "YES Price": f"{m.get('yes_price', 0):.3f}",
                            "Type": m.get("type", "?"),
                            "Title": m.get("title", "?")[:50],
                        })
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                else:
                    st.info(f"Found {det.get('total', 0)} markets (none matching criteria)")
            except json.JSONDecodeError:
                st.text(s.reason)

    # ── 2. Model Signals ──
    if signals:
        st.markdown("#### 📡 Model Signals & Ensemble")
        for sig in signals:
            try:
                det = json.loads(sig.details_json) if sig.details_json else {}
                models = det.get("models", [])
                ens_prob = det.get("ensemble_prob", 0.5)
                ens_conf = det.get("ensemble_confidence", 0)
                disagreements = det.get("disagreement_flags", [])

                # Ensemble summary
                direction = "BEARISH 🔴" if ens_prob < 0.45 else "BULLISH 🟢" if ens_prob > 0.55 else "NEUTRAL ⚪"
                st.markdown(
                    f"**{sig.asset}** — Ensemble: **{ens_prob:.3f}** ({direction}) "
                    f"| Confidence: **{ens_conf}**"
                )

                if models:
                    rows = []
                    for m in models:
                        prob = m.get("prob_up", 0.5)
                        conf = m.get("confidence", 0)
                        wt = m.get("weight", 0)
                        drivers = ", ".join(m.get("key_drivers", []))
                        dir_icon = "🔴" if prob < 0.45 else "🟢" if prob > 0.55 else "⚪"
                        rows.append({
                            "Model": m.get("model", "?"),
                            "Dir": dir_icon,
                            "Prob Up": f"{prob:.3f}",
                            "Conf": conf,
                            "Weight": f"{wt:.3f}",
                            "Drivers": drivers[:40],
                        })
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

                if disagreements:
                    st.warning(f"Disagreements: {', '.join(disagreements)}")
            except json.JSONDecodeError:
                st.text(sig.reason)
        st.markdown("---")

    # ── 3. Filter Chain (per asset) ──
    # Group filters + edge + risk by asset
    asset_decisions = defaultdict(list)
    for d in filters + edges + risks + trades:
        asset_decisions[d.asset].append(d)

    if asset_decisions:
        st.markdown("#### 🔗 Decision Chain (per asset)")

        for asset in sorted(asset_decisions.keys()):
            decs = sorted(asset_decisions[asset], key=lambda x: x.created_at)

            # Determine final outcome for this asset
            has_trade = any(d.stage == "execute" for d in decs)
            final_reject = next(
                (d for d in reversed(decs) if d.decision == "REJECT"), None
            )

            if has_trade:
                outcome = "🎯 TRADED"
            elif final_reject:
                outcome = f"🚫 REJECTED at {final_reject.stage.replace('filter_', '')}"
            else:
                outcome = "⏸ NO ACTION"

            market_title = next((d.market_title for d in decs if d.market_title), "")
            title_display = f" — {market_title[:50]}" if market_title else ""

            with st.expander(f"**{asset}** {outcome}{title_display}", expanded=has_trade):
                for d in decs:
                    icon = _get_icon(d.stage)
                    stage_name = d.stage.replace("filter_", "").replace("_", " ").title()
                    color = _DECISION_COLORS.get(d.decision, "#888")

                    # Build the step display
                    st.markdown(
                        f"{icon} **{stage_name}** "
                        f'<span style="background-color:{color};color:white;padding:1px 6px;'
                        f'border-radius:3px;font-size:0.75em">{d.decision}</span> '
                        f"— {d.reason}",
                        unsafe_allow_html=True,
                    )

                    # Show details in a compact format
                    if d.details_json:
                        try:
                            det = json.loads(d.details_json)
                            # Show key numeric values inline
                            key_vals = []
                            for k, v in det.items():
                                if isinstance(v, (int, float)):
                                    if isinstance(v, float):
                                        key_vals.append(f"`{k}={v:.4f}`")
                                    else:
                                        key_vals.append(f"`{k}={v}`")
                            if key_vals:
                                st.caption("  ".join(key_vals[:8]))
                        except json.JSONDecodeError:
                            pass

    # ── 4. Quick Stats ──
    total_assets = len(set(d.asset for d in decisions if d.asset not in ("_CYCLE", "_SCAN")))
    total_rejects = sum(1 for d in filters if d.decision == "REJECT")
    total_trades = len(trades)
    total_passed = sum(1 for d in filters if d.decision == "PASS" and d.stage == "filter_all_passed")

    cols = st.columns(4)
    cols[0].metric("Assets Evaluated", total_assets)
    cols[1].metric("Filters Rejected", total_rejects)
    cols[2].metric("Qualified", total_passed)
    cols[3].metric("Trades Executed", total_trades)
