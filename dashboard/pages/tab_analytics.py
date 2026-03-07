"""Tab 4 — Analytics: calibration chart, Brier per model, fee impact analysis."""

from collections import defaultdict

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sqlalchemy.orm import Session

from database.models import Trade, Signal
from config.constants import MODEL_NAMES


def render_analytics(session: Session, settings):
    st.header("Analytics")

    all_trades = (
        session.query(Trade)
        .filter(Trade.status.in_(["CLOSED", "RESOLVED"]))
        .order_by(Trade.created_at)
        .all()
    )

    if not all_trades:
        st.info("No closed trades for analytics.")
        return

    # ── Calibration Chart ──
    st.subheader("Calibration Chart")
    st.caption("Predicted probability vs actual win rate (binned)")

    # Bin trades by predicted prob
    bins = np.arange(0.3, 1.0, 0.1)
    bin_labels = [f"{b:.0%}-{b + 0.1:.0%}" for b in bins[:-1]]
    predicted = []
    actual = []

    for i in range(len(bins) - 1):
        lo, hi = bins[i], bins[i + 1]
        bucket = [
            t for t in all_trades
            if t.your_prob and lo <= t.your_prob < hi
        ]
        if bucket:
            avg_pred = np.mean([t.your_prob for t in bucket])
            avg_actual = np.mean([1.0 if t.result == "WON" else 0.0 for t in bucket])
            predicted.append(avg_pred)
            actual.append(avg_actual)

    if predicted:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=predicted, y=actual,
            mode="markers+lines",
            name="Actual vs Predicted",
            marker=dict(size=10, color="#636efa"),
        ))
        fig.add_trace(go.Scatter(
            x=[0.3, 0.9], y=[0.3, 0.9],
            mode="lines",
            name="Perfect Calibration",
            line=dict(dash="dash", color="gray"),
        ))
        fig.update_layout(
            height=350,
            xaxis_title="Predicted Probability",
            yaxis_title="Actual Win Rate",
            template="plotly_dark",
            margin=dict(l=20, r=20, t=30, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Brier Score by Model ──
    st.subheader("Brier Score by Model")
    st.caption("Lower is better. WARNING > 0.28, CRITICAL > 0.35")

    # Get recent signals with outcomes (approximate via trade matching)
    # For dashboard purposes, compute from trade-level data
    signals = session.query(Signal).order_by(Signal.created_at.desc()).limit(1000).all()

    model_preds = defaultdict(list)
    for sig in signals:
        model_preds[sig.model_name].append(sig.prob_up)

    # Approximate Brier using trade outcomes
    trade_outcomes = defaultdict(list)
    for t in all_trades:
        outcome = 1.0 if t.result == "WON" else 0.0
        trade_outcomes[t.asset].append((t.your_prob or 0.5, outcome))

    # Overall Brier
    if trade_outcomes:
        all_brier_pairs = []
        for pairs in trade_outcomes.values():
            all_brier_pairs.extend(pairs)
        overall_brier = np.mean([(p - o) ** 2 for p, o in all_brier_pairs])
        st.metric("Overall Ensemble Brier", f"{overall_brier:.3f}")

    # Model signal distribution
    if model_preds:
        models = sorted(model_preds.keys())
        avg_probs = [np.mean(model_preds[m]) for m in models]
        fig2 = go.Figure(go.Bar(
            x=models, y=avg_probs,
            marker_color="#636efa",
            text=[f"{p:.2f}" for p in avg_probs],
            textposition="auto",
        ))
        fig2.update_layout(
            height=250,
            yaxis_title="Avg Prob Up",
            template="plotly_dark",
            margin=dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig2, use_container_width=True)

    # ── Fee Impact Analysis ──
    st.subheader("Fee Impact Analysis")

    tf_fees = defaultdict(lambda: {"fees": 0.0, "pnl": 0.0, "count": 0})
    for t in all_trades:
        tf = t.timeframe
        tf_fees[tf]["fees"] += t.taker_fee_paid or 0.0
        tf_fees[tf]["pnl"] += t.pnl_usd or 0.0
        tf_fees[tf]["count"] += 1

    if tf_fees:
        rows = []
        for tf in sorted(tf_fees.keys()):
            d = tf_fees[tf]
            rows.append({
                "Timeframe": tf,
                "Trades": d["count"],
                "Total Fees": f"${d['fees']:,.2f}",
                "Total P&L": f"${d['pnl']:,.2f}",
                "P&L After Fees": f"${d['pnl'] - d['fees']:,.2f}",
                "Fee % of P&L": f"{d['fees'] / abs(d['pnl']) * 100:.1f}%" if d["pnl"] != 0 else "—",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── Win Rate by Timeframe ──
    st.subheader("Win Rate by Timeframe")
    tf_stats = defaultdict(lambda: {"wins": 0, "total": 0})
    for t in all_trades:
        tf_stats[t.timeframe]["total"] += 1
        if t.result == "WON":
            tf_stats[t.timeframe]["wins"] += 1

    if tf_stats:
        tfs = sorted(tf_stats.keys())
        wrs = [tf_stats[tf]["wins"] / tf_stats[tf]["total"] * 100 for tf in tfs]
        colors = ["#00cc96" if wr >= 54 else "#ef553b" for wr in wrs]

        fig3 = go.Figure(go.Bar(
            x=tfs, y=wrs,
            marker_color=colors,
            text=[f"{wr:.1f}%" for wr in wrs],
            textposition="auto",
        ))
        fig3.add_hline(y=54, line_dash="dash", line_color="yellow",
                       annotation_text="54% threshold")
        fig3.update_layout(
            height=250,
            yaxis_title="Win Rate (%)",
            template="plotly_dark",
            margin=dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig3, use_container_width=True)
