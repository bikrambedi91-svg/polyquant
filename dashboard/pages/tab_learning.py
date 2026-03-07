"""Tab 7 — Learning Lab: evolution timeline, TP/SL comparison, graveyard/nursery."""

import json

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy.orm import Session

from database.models import Trade, LearningEvent
from config.constants import MODEL_NAMES, ASSETS, MARKET_TIMEFRAMES


def render_learning(session: Session, settings):
    st.header("Learning Lab")

    # ── Learning Status ──
    all_closed = (
        session.query(Trade)
        .filter(Trade.status.in_(["CLOSED", "RESOLVED"]))
        .all()
    )
    total_trades = len(all_closed)
    cold_start = total_trades < 50
    optuna_ready = total_trades >= 80

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Closed Trades", str(total_trades))
    c2.metric("Cold Start", "Yes" if cold_start else "No")
    c3.metric("Optuna Ready", "Yes" if optuna_ready else f"Need {80 - total_trades} more")
    c4.metric("Learning", "DORMANT" if cold_start else "ACTIVE")

    # ── Evolution Timeline ──
    st.subheader("Evolution Timeline")

    events = (
        session.query(LearningEvent)
        .order_by(LearningEvent.created_at)
        .all()
    )

    if events:
        event_colors = {
            "recalibration": "#636efa",
            "weight_update": "#00cc96",
            "param_mutation": "#ffa15a",
            "model_warning": "#ffff00",
            "model_critical": "#ef553b",
            "model_retired": "#000000",
            "model_promoted": "#00cc96",
            "sl_updated": "#ab63fa",
            "tp_updated": "#19d3f3",
        }

        dates = [e.created_at for e in events]
        types = [e.event_type for e in events]
        colors = [event_colors.get(t, "#888888") for t in types]
        labels = [f"{e.event_type}: {e.model_name or '—'}" for e in events]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates,
            y=[1] * len(dates),
            mode="markers+text",
            marker=dict(size=12, color=colors),
            text=labels,
            textposition="top center",
            textfont=dict(size=9),
            hovertext=[
                f"{e.event_type}<br>{e.model_name or '—'}<br>{e.created_at}"
                for e in events
            ],
        ))
        fig.update_layout(
            height=200,
            template="plotly_dark",
            showlegend=False,
            yaxis=dict(visible=False),
            margin=dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Event table
        rows = []
        for e in reversed(events):
            details = ""
            if e.details_json:
                try:
                    d = json.loads(e.details_json)
                    details = str(d)
                except (json.JSONDecodeError, TypeError):
                    details = e.details_json or ""
            rows.append({
                "Date": e.created_at.strftime("%m/%d %H:%M") if e.created_at else "",
                "Event": e.event_type,
                "Model": e.model_name or "—",
                "Details": details[:80],
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=300)
    else:
        st.info("No learning events yet.")

    # ── TP/SL Comparison: Default vs Learned ──
    st.subheader("TP/SL: Default vs Learned")

    default_trades = [t for t in all_closed if not t.was_sl_learned]
    learned_trades = [t for t in all_closed if t.was_sl_learned]

    if default_trades and learned_trades:
        def _wr(trades):
            w = sum(1 for t in trades if t.result == "WON")
            return w / len(trades) * 100 if trades else 0

        def _avg_pnl(trades):
            return sum(t.pnl_usd or 0 for t in trades) / len(trades) if trades else 0

        comp = pd.DataFrame([
            {
                "SL/TP Type": "📏 Default",
                "Trades": len(default_trades),
                "Win Rate": f"{_wr(default_trades):.1f}%",
                "Avg P&L": f"${_avg_pnl(default_trades):,.2f}",
                "Total P&L": f"${sum(t.pnl_usd or 0 for t in default_trades):,.2f}",
            },
            {
                "SL/TP Type": "🧠 Learned",
                "Trades": len(learned_trades),
                "Win Rate": f"{_wr(learned_trades):.1f}%",
                "Avg P&L": f"${_avg_pnl(learned_trades):,.2f}",
                "Total P&L": f"${sum(t.pnl_usd or 0 for t in learned_trades):,.2f}",
            },
        ])
        st.dataframe(comp, use_container_width=True, hide_index=True)
    elif all_closed:
        st.caption("All trades use same SL/TP type — comparison unavailable.")

    # ── MAE/MFE Distribution ──
    st.subheader("MAE / MFE Distribution")
    maes = [t.max_adverse_excursion for t in all_closed if t.max_adverse_excursion]
    mfes = [t.max_favorable_excursion for t in all_closed if t.max_favorable_excursion]

    if maes and mfes:
        fig_mae = go.Figure()
        fig_mae.add_trace(go.Histogram(
            x=maes, name="MAE",
            marker_color="#ef553b", opacity=0.7,
            nbinsx=20,
        ))
        fig_mae.add_trace(go.Histogram(
            x=mfes, name="MFE",
            marker_color="#00cc96", opacity=0.7,
            nbinsx=20,
        ))
        fig_mae.update_layout(
            height=250, template="plotly_dark",
            barmode="overlay",
            xaxis_title="Excursion",
            yaxis_title="Count",
            margin=dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig_mae, use_container_width=True)

    # ── Recalibration Cycles ──
    st.subheader("Recalibration History")
    recals = [e for e in events if e.event_type == "recalibration"] if events else []
    if recals:
        rows = []
        for e in recals:
            details = {}
            if e.details_json:
                try:
                    details = json.loads(e.details_json)
                except (json.JSONDecodeError, TypeError):
                    pass
            rows.append({
                "Date": e.created_at.strftime("%m/%d %H:%M") if e.created_at else "",
                "Cycle": details.get("cycle", "—"),
                "Trades": details.get("total_trades", "—"),
                "Models Evaluated": details.get("models_evaluated", "—"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.caption("No recalibration cycles yet.")

    # ── Safety Rails ──
    st.subheader("Safety Rails")
    rails = pd.DataFrame([
        {"Rule": "Max models mutated/cycle", "Value": "1"},
        {"Rule": "Max models retired/cycle", "Value": "1"},
        {"Rule": "Min active models", "Value": "4"},
        {"Rule": "Min trades for SL opt", "Value": str(settings.MIN_TRADES_FOR_SL_OPTIMIZATION)},
        {"Rule": "Min trades for Optuna", "Value": str(settings.MIN_TRADES_FOR_PARAM_MUTATION)},
        {"Rule": "Max param change", "Value": f"{settings.MAX_PARAM_CHANGE_PCT:.0%}"},
        {"Rule": "Max SL/TP change/cycle", "Value": "3 cents"},
        {"Rule": "Max weight change/cycle", "Value": "15%"},
    ])
    st.dataframe(rails, use_container_width=True, hide_index=True)
