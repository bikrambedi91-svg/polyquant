"""Tab 1 — Overview: Bankroll, P&L, equity curve, regime badge."""

from datetime import datetime, timedelta, timezone
from collections import defaultdict

import streamlit as st
import plotly.graph_objects as go
from sqlalchemy.orm import Session

from database.models import Trade


def render_overview(session: Session, settings):
    st.header("Overview")

    # ── Query data ──
    all_trades = (
        session.query(Trade)
        .filter(Trade.status.in_(["CLOSED", "RESOLVED"]))
        .order_by(Trade.created_at)
        .all()
    )
    active_trades = session.query(Trade).filter(Trade.status == "ACTIVE").all()

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # SQLite stores naive datetimes — compare as naive
    today_start_naive = today_start.replace(tzinfo=None)

    # ── Metrics ──
    total_pnl = sum(t.pnl_usd or 0.0 for t in all_trades)
    today_pnl = sum(
        (t.pnl_usd or 0.0)
        for t in all_trades
        if t.resolved_at and t.resolved_at >= today_start_naive
    )
    total_closed = len(all_trades)
    wins = sum(1 for t in all_trades if t.result == "WON")
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0.0
    total_fees = sum(t.taker_fee_paid or 0.0 for t in all_trades)

    # Mode & regime
    mode = settings.MODE.upper()
    # Get most recent trade's regime
    last_regime = all_trades[-1].regime_at_entry if all_trades else "UNKNOWN"

    # ── Top row: mode badge + regime badge ──
    col_mode, col_regime, col_spacer = st.columns([1, 1, 3])
    with col_mode:
        badge_color = "🟢" if mode == "PAPER" else "🔴"
        st.markdown(f"### {badge_color} {mode}")
    with col_regime:
        regime_icons = {
            "RISK_ON": "🟢", "RISK_OFF": "🔴", "HIGH_VOL": "🟡",
            "TRENDING": "🔵", "CHOPPY": "🟠",
        }
        icon = regime_icons.get(last_regime, "⚪")
        st.markdown(f"### {icon} {last_regime}")

    # ── Metric cards ──
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Bankroll", f"${settings.BANKROLL_USDC:,.0f}")
    c2.metric("All-Time P&L", f"${total_pnl:,.2f}")
    c3.metric("Today P&L", f"${today_pnl:,.2f}")
    c4.metric("Win Rate", f"{win_rate:.1f}%")
    c5.metric("Total Trades", str(total_closed))
    c6.metric("Active", str(len(active_trades)))

    # ── Equity Curve ──
    st.subheader("Equity Curve")
    if all_trades:
        cumulative = []
        running = settings.BANKROLL_USDC
        dates = []
        for t in all_trades:
            running += t.pnl_usd or 0.0
            cumulative.append(running)
            dates.append(t.resolved_at or t.created_at)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates, y=cumulative,
            mode="lines",
            name="Equity",
            line=dict(color="#00cc96", width=2),
            fill="tozeroy",
            fillcolor="rgba(0, 204, 150, 0.1)",
        ))
        fig.add_hline(
            y=settings.BANKROLL_USDC,
            line_dash="dash", line_color="gray",
            annotation_text="Starting Bankroll",
        )
        fig.update_layout(
            height=350, margin=dict(l=20, r=20, t=30, b=20),
            xaxis_title="", yaxis_title="Equity ($)",
            template="plotly_dark",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No closed trades yet.")

    # ── P&L by Asset ──
    st.subheader("P&L by Asset")
    if all_trades:
        asset_pnl = defaultdict(float)
        for t in all_trades:
            asset_pnl[t.asset] += t.pnl_usd or 0.0

        assets = list(asset_pnl.keys())
        pnls = [asset_pnl[a] for a in assets]
        colors = ["#00cc96" if p >= 0 else "#ef553b" for p in pnls]

        fig2 = go.Figure(go.Bar(
            x=assets, y=pnls,
            marker_color=colors,
            text=[f"${p:,.2f}" for p in pnls],
            textposition="auto",
        ))
        fig2.update_layout(
            height=250, margin=dict(l=20, r=20, t=20, b=20),
            template="plotly_dark",
            yaxis_title="P&L ($)",
        )
        st.plotly_chart(fig2, use_container_width=True)

    # ── Summary stats ──
    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("Total Fees Paid", f"${total_fees:,.2f}")
    with col_b:
        net_after_fees = total_pnl - total_fees
        st.metric("Net After Fees", f"${net_after_fees:,.2f}")
