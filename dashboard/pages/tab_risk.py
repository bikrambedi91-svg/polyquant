"""Tab 5 — Risk Monitor: exposure gauges, drawdown meter, correlation."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sqlalchemy.orm import Session

from database.models import Trade
from config.constants import ASSETS


def render_risk(session: Session, settings):
    st.header("Risk Monitor")

    active = session.query(Trade).filter(Trade.status == "ACTIVE").all()
    closed = (
        session.query(Trade)
        .filter(Trade.status.in_(["CLOSED", "RESOLVED"]))
        .order_by(Trade.created_at)
        .all()
    )

    bankroll = settings.BANKROLL_USDC

    # ── Exposure Gauges ──
    st.subheader("Exposure")

    total_exposure = sum(t.size_usd for t in active)
    exposure_pct = total_exposure / bankroll * 100

    # Per-asset exposure
    asset_exp = defaultdict(float)
    for t in active:
        asset_exp[t.asset] += t.size_usd

    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Total Exposure",
        f"${total_exposure:,.0f}",
        f"{exposure_pct:.1f}% of bankroll",
    )
    c2.metric(
        "Max Allowed",
        f"${bankroll * settings.MAX_TOTAL_EXPOSURE_PCT:,.0f}",
        f"{settings.MAX_TOTAL_EXPOSURE_PCT:.0%}",
    )
    c3.metric(
        "Headroom",
        f"${bankroll * settings.MAX_TOTAL_EXPOSURE_PCT - total_exposure:,.0f}",
    )

    # Exposure gauge
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=exposure_pct,
        title={"text": "Total Exposure %"},
        delta={"reference": settings.MAX_TOTAL_EXPOSURE_PCT * 100},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "#636efa"},
            "steps": [
                {"range": [0, 40], "color": "#2d2d2d"},
                {"range": [40, 60], "color": "#3d3d1d"},
                {"range": [60, 100], "color": "#3d1d1d"},
            ],
            "threshold": {
                "line": {"color": "red", "width": 3},
                "thickness": 0.75,
                "value": settings.MAX_TOTAL_EXPOSURE_PCT * 100,
            },
        },
    ))
    fig_gauge.update_layout(height=250, template="plotly_dark", margin=dict(t=50, b=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

    # Per-asset exposure bars
    if asset_exp:
        st.subheader("Per-Asset Exposure")
        assets = list(asset_exp.keys())
        exp_vals = [asset_exp[a] for a in assets]
        max_per_asset = bankroll * settings.MAX_PER_ASSET_PCT

        fig_asset = go.Figure()
        fig_asset.add_trace(go.Bar(
            x=assets, y=exp_vals,
            name="Current",
            marker_color="#636efa",
            text=[f"${v:,.0f}" for v in exp_vals],
            textposition="auto",
        ))
        fig_asset.add_hline(y=max_per_asset, line_dash="dash", line_color="red",
                           annotation_text=f"Max ${max_per_asset:,.0f}")
        fig_asset.update_layout(
            height=250, template="plotly_dark",
            yaxis_title="Exposure ($)",
            margin=dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig_asset, use_container_width=True)

    # ── Daily Drawdown Meter ──
    st.subheader("Daily Drawdown")

    now = datetime.now(timezone.utc)
    # Compute daily P&L for last 14 days
    daily_pnl = defaultdict(float)
    for t in closed:
        if t.resolved_at:
            day_key = t.resolved_at.strftime("%m/%d")
            daily_pnl[day_key] += t.pnl_usd or 0.0

    if daily_pnl:
        days = list(daily_pnl.keys())[-14:]
        pnls = [daily_pnl[d] for d in days]
        dd_pcts = [abs(p) / bankroll * 100 if p < 0 else 0 for p in pnls]
        colors = ["#ef553b" if p < 0 else "#00cc96" for p in pnls]

        fig_dd = go.Figure()
        fig_dd.add_trace(go.Bar(
            x=days, y=pnls,
            marker_color=colors,
            text=[f"${p:,.0f}" for p in pnls],
            textposition="auto",
        ))
        fig_dd.add_hline(y=-bankroll * settings.DAILY_DRAWDOWN_HALT_PCT,
                        line_dash="dash", line_color="red",
                        annotation_text=f"Halt: -${bankroll * settings.DAILY_DRAWDOWN_HALT_PCT:,.0f}")
        fig_dd.update_layout(
            height=250, template="plotly_dark",
            yaxis_title="Daily P&L ($)",
            margin=dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig_dd, use_container_width=True)

        # Worst day
        worst = min(pnls)
        worst_pct = abs(worst) / bankroll * 100 if worst < 0 else 0
        st.metric(
            "Worst Day",
            f"${worst:,.2f}",
            f"-{worst_pct:.1f}% of bankroll" if worst < 0 else "No loss",
        )
    else:
        st.info("No daily P&L data yet.")

    # ── Asset Correlation Matrix ──
    st.subheader("Asset P&L Correlation")

    asset_daily = defaultdict(lambda: defaultdict(float))
    for t in closed:
        if t.resolved_at:
            day = t.resolved_at.strftime("%Y-%m-%d")
            asset_daily[t.asset][day] += t.pnl_usd or 0.0

    if len(asset_daily) >= 2:
        # Align days across assets
        all_days = sorted(set().union(*[set(d.keys()) for d in asset_daily.values()]))
        if len(all_days) >= 3:
            asset_names = sorted(asset_daily.keys())
            matrix = []
            for a in asset_names:
                matrix.append([asset_daily[a].get(d, 0.0) for d in all_days])

            arr = np.array(matrix)
            if arr.shape[1] >= 2:
                corr = np.corrcoef(arr)
                fig_corr = go.Figure(go.Heatmap(
                    z=corr,
                    x=asset_names,
                    y=asset_names,
                    colorscale="RdBu",
                    zmid=0,
                    text=np.round(corr, 2),
                    texttemplate="%{text}",
                ))
                fig_corr.update_layout(
                    height=300, template="plotly_dark",
                    margin=dict(l=20, r=20, t=20, b=20),
                )
                st.plotly_chart(fig_corr, use_container_width=True)

    # ── Hard Limits Status ──
    st.subheader("Hard Limits")
    limits = pd.DataFrame([
        {"Rule": "Max Single Position", "Limit": f"{settings.MAX_SINGLE_POSITION_PCT:.0%}", "Value": f"${bankroll * settings.MAX_SINGLE_POSITION_PCT:,.0f}"},
        {"Rule": "Max Per Asset", "Limit": f"{settings.MAX_PER_ASSET_PCT:.0%}", "Value": f"${bankroll * settings.MAX_PER_ASSET_PCT:,.0f}"},
        {"Rule": "Max Total Exposure", "Limit": f"{settings.MAX_TOTAL_EXPOSURE_PCT:.0%}", "Value": f"${bankroll * settings.MAX_TOTAL_EXPOSURE_PCT:,.0f}"},
        {"Rule": "Daily DD Halt", "Limit": f"{settings.DAILY_DRAWDOWN_HALT_PCT:.0%}", "Value": f"${bankroll * settings.DAILY_DRAWDOWN_HALT_PCT:,.0f}"},
        {"Rule": "Min Position", "Limit": "—", "Value": f"${settings.MIN_POSITION_USD:,.0f}"},
    ])
    st.dataframe(limits, use_container_width=True, hide_index=True)
