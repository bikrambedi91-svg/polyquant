"""PolyQuant Streamlit Dashboard — 8-tab trading dashboard.

Run: streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from database.models import init_db, Trade, Signal, LearningEvent, PipelineDecision
from config.settings import get_settings

from dashboard.pages.tab_overview import render_overview
from dashboard.pages.tab_positions import render_positions
from dashboard.pages.tab_history import render_history
from dashboard.pages.tab_analytics import render_analytics
from dashboard.pages.tab_risk import render_risk
from dashboard.pages.tab_signals import render_signals
from dashboard.pages.tab_learning import render_learning
from dashboard.pages.tab_decisions import render_decisions

# ── Page Config ──
st.set_page_config(
    page_title="PolyQuant Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Settings + DB ──
settings = get_settings()


@st.cache_resource
def get_db():
    """Initialize DB connection (cached across reruns)."""
    db_url = settings.DB_URL
    engine, session_factory = init_db(db_url)
    return session_factory


SessionFactory = get_db()


def get_session():
    return SessionFactory()


# ── Sidebar ──
with st.sidebar:
    st.title("PolyQuant")
    st.caption(f"Mode: **{settings.MODE.upper()}**")
    st.caption(f"Bankroll: **${settings.BANKROLL_USDC:,.0f}**")
    st.divider()

    # Auto-refresh
    refresh_rate = st.selectbox(
        "Auto-refresh",
        options=[30, 60, 120, 300],
        index=1,
        format_func=lambda x: f"{x}s",
    )

# ── Tabs ──
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "Overview",
    "Active Positions",
    "Trade History",
    "Analytics",
    "Risk Monitor",
    "Signal Health",
    "Learning Lab",
    "Live Decisions",
])

session = get_session()

try:
    with tab1:
        render_overview(session, settings)
    with tab2:
        render_positions(session, settings)
    with tab3:
        render_history(session, settings)
    with tab4:
        render_analytics(session, settings)
    with tab5:
        render_risk(session, settings)
    with tab6:
        render_signals(session, settings)
    with tab7:
        render_learning(session, settings)
    with tab8:
        render_decisions(session, settings)
finally:
    session.close()

# ── Auto-refresh via streamlit fragment ──
st.markdown(
    f"""<meta http-equiv="refresh" content="{refresh_rate}">""",
    unsafe_allow_html=True,
)
