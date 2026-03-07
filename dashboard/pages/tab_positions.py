"""Tab 2 — Active Positions: entry/current/unrealized, TP/SL badges, countdown."""

from datetime import datetime, timezone

import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session

from database.models import Trade


def render_positions(session: Session, settings):
    st.header("Active Positions")

    active = (
        session.query(Trade)
        .filter(Trade.status == "ACTIVE")
        .order_by(Trade.created_at.desc())
        .all()
    )

    if not active:
        st.info("No active positions.")
        return

    # ── Summary metrics ──
    total_exposure = sum(t.size_usd for t in active)
    exposure_pct = total_exposure / settings.BANKROLL_USDC * 100
    c1, c2, c3 = st.columns(3)
    c1.metric("Active Positions", str(len(active)))
    c2.metric("Total Exposure", f"${total_exposure:,.0f}")
    c3.metric("Exposure %", f"{exposure_pct:.1f}%")

    # ── Position cards ──
    for trade in active:
        sl_badge = "🧠" if trade.was_sl_learned else "📏"
        created = trade.created_at
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        elapsed = datetime.now(timezone.utc) - created
        elapsed_str = f"{elapsed.total_seconds() / 60:.0f}m"

        with st.expander(
            f"{trade.asset} {trade.timeframe} — {trade.action} "
            f"@ {trade.entry_price:.2f} | {sl_badge} | {elapsed_str} ago",
            expanded=True,
        ):
            # Market link
            if trade.market_url:
                title = trade.market_title or "View on Polymarket"
                st.markdown(
                    f"[{title}]({trade.market_url})",
                    unsafe_allow_html=False,
                )

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Entry", f"{trade.entry_price:.2f}")
            col2.metric("Our Prob", f"{trade.your_prob:.2f}" if trade.your_prob else "—")
            col3.metric("Edge", f"{trade.edge_at_entry:.1%}" if trade.edge_at_entry else "—")
            col4.metric("Size", f"${trade.size_usd:,.0f}")

            col5, col6, col7, col8 = st.columns(4)
            col5.metric("TP Level", f"{trade.tp_level:.2f}" if trade.tp_level else "—")
            col6.metric("SL Level", f"{trade.sl_level:.2f}" if trade.sl_level else "—")
            col7.metric("Confidence", str(trade.confidence or "—"))
            col8.metric("Regime", trade.regime_at_entry or "—")

            # TP/SL badge explanation
            if trade.was_sl_learned:
                st.caption("🧠 SL/TP levels learned from historical MAE/MFE data")
            else:
                st.caption("📏 SL/TP using default levels")

    # ── Table view ──
    st.subheader("Position Table")
    rows = []
    for t in active:
        rows.append({
            "Trade ID": t.trade_id,
            "Asset": t.asset,
            "TF": t.timeframe,
            "Action": t.action,
            "Entry": t.entry_price,
            "Size ($)": t.size_usd,
            "Edge": f"{t.edge_at_entry:.1%}" if t.edge_at_entry else "—",
            "Conf": t.confidence,
            "TP": t.tp_level,
            "SL": t.sl_level,
            "SL Type": "🧠" if t.was_sl_learned else "📏",
            "Regime": t.regime_at_entry,
            "Market": t.market_url or "",
        })
    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Market": st.column_config.LinkColumn("Market", display_text="View"),
        },
    )
