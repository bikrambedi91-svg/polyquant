"""Tab 3 — Trade History: filterable ledger with exit quality badges."""

import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session

from database.models import Trade
from config.constants import ASSETS, MARKET_TIMEFRAMES


def render_history(session: Session, settings):
    st.header("Trade History")

    # ── Filters ──
    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    with col_f1:
        asset_filter = st.selectbox("Asset", ["All"] + ASSETS, key="hist_asset")
    with col_f2:
        tf_filter = st.selectbox("Timeframe", ["All"] + MARKET_TIMEFRAMES, key="hist_tf")
    with col_f3:
        result_filter = st.selectbox("Result", ["All", "WON", "LOST"], key="hist_result")
    with col_f4:
        exit_filter = st.selectbox(
            "Exit Reason",
            ["All", "resolution", "take_profit", "stop_loss", "time_decay"],
            key="hist_exit",
        )

    # ── Query ──
    query = session.query(Trade).filter(Trade.status.in_(["CLOSED", "RESOLVED"]))
    if asset_filter != "All":
        query = query.filter(Trade.asset == asset_filter)
    if tf_filter != "All":
        query = query.filter(Trade.timeframe == tf_filter)
    if result_filter != "All":
        query = query.filter(Trade.result == result_filter)
    if exit_filter != "All":
        query = query.filter(Trade.exit_reason == exit_filter)

    trades = query.order_by(Trade.created_at.desc()).limit(200).all()

    if not trades:
        st.info("No trades match filters.")
        return

    # ── Summary ──
    total_pnl = sum(t.pnl_usd or 0 for t in trades)
    wins = sum(1 for t in trades if t.result == "WON")
    wr = wins / len(trades) * 100 if trades else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Trades Shown", str(len(trades)))
    c2.metric("P&L", f"${total_pnl:,.2f}")
    c3.metric("Win Rate", f"{wr:.1f}%")
    c4.metric("Avg P&L", f"${total_pnl / len(trades):,.2f}" if trades else "$0")

    # ── Build table ──
    rows = []
    for t in trades:
        # Exit quality badge
        if t.result == "WON":
            badge = "✅"
        elif t.result == "LOST":
            # Check if would have won if held
            if t.would_have_won_if_held:
                badge = "➖"  # Bad exit — would have won
            else:
                badge = "❌"  # Correct exit
        else:
            badge = "—"

        rows.append({
            "": badge,
            "Date": t.created_at.strftime("%m/%d %H:%M") if t.created_at else "",
            "Asset": t.asset,
            "TF": t.timeframe,
            "Action": t.action,
            "Entry": f"{t.entry_price:.2f}",
            "Exit": f"{t.exit_price:.2f}" if t.exit_price else "—",
            "P&L": f"${t.pnl_usd:,.2f}" if t.pnl_usd else "—",
            "Edge": f"{t.edge_at_entry:.1%}" if t.edge_at_entry else "—",
            "Exit Reason": t.exit_reason or "—",
            "Fee": f"${t.taker_fee_paid:.2f}" if t.taker_fee_paid else "$0",
            "SL Type": "🧠" if t.was_sl_learned else "📏",
            "Regime": t.regime_at_entry or "—",
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, height=500)

    # ── Legend ──
    st.caption("✅ Won | ❌ Lost (correct exit) | ➖ Lost but would have won if held | 🧠 Learned SL/TP | 📏 Default SL/TP")
