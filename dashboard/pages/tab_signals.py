"""Tab 6 — Signal Health: 4x7 heatmap, model status badges."""

from collections import defaultdict

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sqlalchemy.orm import Session

from database.models import Signal, LearningEvent
from config.constants import ASSETS, MARKET_TIMEFRAMES, MODEL_NAMES


def render_signals(session: Session, settings):
    st.header("Signal Health")

    # ── Latest Signals Heatmap (Asset x Model) ──
    st.subheader("Latest Signals — Prob Up Heatmap")
    st.caption("Rows = Assets, Columns = Models. Color = prob_up (red=bearish, green=bullish)")

    # Get latest signal per (asset, timeframe, model)
    signals = session.query(Signal).order_by(Signal.created_at.desc()).limit(2000).all()

    # For heatmap, pick one timeframe to show
    tf_choice = st.selectbox("Timeframe", MARKET_TIMEFRAMES, index=2, key="sig_tf")

    # Build matrix: asset x model
    latest = {}
    for sig in signals:
        key = (sig.asset, sig.timeframe, sig.model_name)
        if key not in latest:
            latest[key] = sig

    matrix = []
    hover = []
    for asset in ASSETS:
        row = []
        hover_row = []
        for model in MODEL_NAMES:
            key = (asset, tf_choice, model)
            if key in latest:
                sig = latest[key]
                row.append(sig.prob_up)
                hover_row.append(
                    f"{asset} | {model}<br>"
                    f"Prob: {sig.prob_up:.2f}<br>"
                    f"Conf: {sig.confidence}"
                )
            else:
                row.append(0.5)
                hover_row.append(f"{asset} | {model}<br>No data")
        matrix.append(row)
        hover.append(hover_row)

    if matrix:
        fig = go.Figure(go.Heatmap(
            z=matrix,
            x=MODEL_NAMES,
            y=ASSETS,
            colorscale=[[0, "#ef553b"], [0.5, "#ffffff"], [1, "#00cc96"]],
            zmid=0.5,
            text=np.round(matrix, 2),
            texttemplate="%{text}",
            hovertext=hover,
            hoverinfo="text",
        ))
        fig.update_layout(
            height=250, template="plotly_dark",
            margin=dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Confidence Heatmap ──
    st.subheader("Confidence Heatmap")

    conf_matrix = []
    for asset in ASSETS:
        row = []
        for model in MODEL_NAMES:
            key = (asset, tf_choice, model)
            if key in latest:
                row.append(latest[key].confidence)
            else:
                row.append(0)
        conf_matrix.append(row)

    if conf_matrix:
        fig2 = go.Figure(go.Heatmap(
            z=conf_matrix,
            x=MODEL_NAMES,
            y=ASSETS,
            colorscale="Blues",
            text=conf_matrix,
            texttemplate="%{text}",
        ))
        fig2.update_layout(
            height=250, template="plotly_dark",
            margin=dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig2, use_container_width=True)

    # ── Model Status Badges ──
    st.subheader("Model Status")
    st.caption("🟢 ACTIVE | 🟡 WARNING | 🔴 CRITICAL | ⚫ RETIRED | 🔵 PROBATION")

    # Check learning events for model health
    events = (
        session.query(LearningEvent)
        .filter(LearningEvent.event_type.in_([
            "model_warning", "model_critical", "model_retired", "model_promoted",
        ]))
        .order_by(LearningEvent.created_at.desc())
        .limit(100)
        .all()
    )

    # Latest status per model
    model_status = {}
    for ev in events:
        if ev.model_name and ev.model_name not in model_status:
            if ev.event_type == "model_warning":
                model_status[ev.model_name] = ("WARNING", "🟡")
            elif ev.event_type == "model_critical":
                model_status[ev.model_name] = ("CRITICAL", "🔴")
            elif ev.event_type == "model_retired":
                model_status[ev.model_name] = ("RETIRED", "⚫")
            elif ev.event_type == "model_promoted":
                model_status[ev.model_name] = ("ACTIVE", "🟢")

    rows = []
    for model in MODEL_NAMES:
        status, icon = model_status.get(model, ("ACTIVE", "🟢"))
        rows.append({
            "Model": model,
            "Status": f"{icon} {status}",
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── Ensemble Prob by Asset ──
    st.subheader("Ensemble Probability by Asset")
    ensemble_data = {}
    for sig in signals:
        if sig.timeframe == tf_choice and sig.ensemble_prob:
            key = sig.asset
            if key not in ensemble_data:
                ensemble_data[key] = sig.ensemble_prob

    if ensemble_data:
        assets = sorted(ensemble_data.keys())
        probs = [ensemble_data[a] for a in assets]
        colors = ["#00cc96" if p > 0.55 else "#ef553b" if p < 0.45 else "#636efa" for p in probs]

        fig3 = go.Figure(go.Bar(
            x=assets, y=probs,
            marker_color=colors,
            text=[f"{p:.2f}" for p in probs],
            textposition="auto",
        ))
        fig3.add_hline(y=0.5, line_dash="dash", line_color="gray")
        fig3.update_layout(
            height=250, template="plotly_dark",
            yaxis_title="Ensemble Prob Up",
            yaxis_range=[0, 1],
            margin=dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig3, use_container_width=True)
