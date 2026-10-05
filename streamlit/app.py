"""
streamlit/app.py
----------------
Auris — Compliance Copilot for Banking & NBFC Teams.
Streamlit dashboard entry point.

Run from project root:
    streamlit run streamlit/app.py

The app works fully standalone when ENV='local' (no Snowflake connection
needed). All heavy operations are wrapped in try/except blocks with
friendly error messages.
"""

from __future__ import annotations

import sys
import os
import uuid
from datetime import datetime, date
from typing import Any

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Path setup — ensure project root AND local streamlit/ dir are on sys.path.
# NOTE: Our folder is named 'streamlit/' which conflicts with the installed
# streamlit package. We explicitly add this directory so local modules
# (mock_data, pdf_export) are importable without the 'streamlit.' prefix.
# ---------------------------------------------------------------------------
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_STREAMLIT_DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (_STREAMLIT_DIR, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
try:
    from config import ENV, CORTEX_MODEL, USER_ROLES  # type: ignore[import]
except Exception:
    ENV = "local"
    CORTEX_MODEL = "mistral-large"
    USER_ROLES = {
        "USER001": "junior_analyst",
        "USER002": "senior_analyst",
        "USER003": "compliance_head",
    }

# ---------------------------------------------------------------------------
# Orchestrator (optional — graceful degradation when Snowflake not connected)
# ---------------------------------------------------------------------------
try:
    from src.orchestrator.orchestrator import AurisOrchestrator  # type: ignore[import]

    _orchestrator = AurisOrchestrator()
    _ORCHESTRATOR_AVAILABLE = True
except Exception as _orch_err:
    _orchestrator = None  # type: ignore[assignment]
    _ORCHESTRATOR_AVAILABLE = False

# ---------------------------------------------------------------------------
# Regulatory agent (optional — for Tab 4 report generation)
# ---------------------------------------------------------------------------
try:
    from src.agents.regulatory_agent import RegulatoryReportAgent  # type: ignore[import]

    _reg_agent = RegulatoryReportAgent()
    _REG_AGENT_AVAILABLE = True
except Exception:
    _reg_agent = None  # type: ignore[assignment]
    _REG_AGENT_AVAILABLE = False

# ---------------------------------------------------------------------------
# Dashboard helpers — import directly (no 'streamlit.' prefix) since
# _STREAMLIT_DIR is already on sys.path above.
# ---------------------------------------------------------------------------
from mock_data import (  # type: ignore[import]
    get_mock_fraud_cases,
    get_mock_metrics,
    get_mock_regulatory_reports,
    get_mock_risk_timeseries,
    get_mock_structuring_groups,
    get_mock_transactions,
    get_regulatory_calendar,
)
from pdf_export import export_report_to_pdf  # type: ignore[import]

try:
    import plotly.express as px
    import plotly.graph_objects as go

    _PLOTLY_AVAILABLE = True
except ImportError:
    _PLOTLY_AVAILABLE = False

# ---------------------------------------------------------------------------
# Demo users
# ---------------------------------------------------------------------------
_DEMO_USERS: list[dict[str, str]] = [
    {"user_id": "USER001", "username": "Priya Sharma", "role": "junior_analyst"},
    {"user_id": "USER002", "username": "Rahul Mehta", "role": "senior_analyst"},
    {"user_id": "USER003", "username": "Deepa Krishnan", "role": "compliance_head"},
]

_QUICK_QUERIES: list[str] = [
    "Flag all transactions over ₹10L in the last 7 days",
    "What is our current LCR status?",
    "Generate AML summary for October 2026",
    "Check for structuring patterns",
    "What does RBI say about KYC for high-risk customers?",
]

_ROLE_DISPLAY: dict[str, str] = {
    "junior_analyst": "Junior Analyst",
    "senior_analyst": "Senior Analyst",
    "compliance_head": "Compliance Head",
}

_ROLE_COLOR: dict[str, str] = {
    "junior_analyst": "#3b82f6",
    "senior_analyst": "#f59e0b",
    "compliance_head": "#10b981",
}

# ---------------------------------------------------------------------------
# Page config (MUST be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Auris",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS — dark professional theme
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    /* ---------- global ---------- */
    html, body, [class*="css"] { font-family: 'Inter', 'Segoe UI', sans-serif; }
    .main { background-color: #0f1623; }

    /* ---------- sidebar ---------- */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0a1940 0%, #0d1f3c 100%);
        border-right: 1px solid #1e3a5f;
    }
    [data-testid="stSidebar"] * { color: #cdd9f0 !important; }
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stButton > button {
        color: #cdd9f0 !important;
    }
    [data-testid="stSidebar"] .stButton > button {
        width: 100%;
        background-color: #132d5e;
        border: 1px solid #1e4080;
        border-radius: 8px;
        color: #a8c0e8 !important;
        margin-bottom: 6px;
        transition: background 0.2s;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        background-color: #1a3f7a;
    }

    /* ---------- cards / containers ---------- */
    .auris-card {
        background: #131e33;
        border: 1px solid #1e3a5f;
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 14px;
    }
    .auris-summary-card {
        background: linear-gradient(135deg, #0d2145 0%, #111c35 100%);
        border-left: 4px solid #3b82f6;
        border-radius: 8px;
        padding: 14px 18px;
        margin: 10px 0;
        color: #cdd9f0;
        font-size: 0.95rem;
        line-height: 1.65;
    }

    /* ---------- badges ---------- */
    .badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.03em;
    }
    .badge-low    { background: #064e3b; color: #6ee7b7; }
    .badge-medium { background: #78350f; color: #fcd34d; }
    .badge-high   { background: #7f1d1d; color: #fca5a5; }
    .badge-role   { background: #1e3a5f; color: #93c5fd; }
    .badge-agent  { background: #1e1b4b; color: #a5b4fc; margin-right: 4px; }

    /* ---------- citation expander ---------- */
    .citation-box {
        background: #0d2145;
        border-left: 3px solid #3b82f6;
        border-radius: 6px;
        padding: 10px 14px;
        margin: 6px 0;
        font-size: 0.88rem;
        color: #93c5fd;
    }

    /* ---------- metric overrides ---------- */
    [data-testid="stMetricValue"] { color: #93c5fd !important; font-size: 1.8rem !important; }
    [data-testid="stMetricLabel"] { color: #64748b !important; }

    /* ---------- tabs ---------- */
    .stTabs [data-baseweb="tab"] { color: #64748b; font-weight: 500; }
    .stTabs [aria-selected="true"] { color: #3b82f6 !important; border-bottom-color: #3b82f6 !important; }

    /* ---------- chip buttons (suggested queries) ---------- */
    .chip-row .stButton > button {
        background: #132d5e;
        border: 1px solid #1e4080;
        border-radius: 20px;
        color: #93c5fd !important;
        font-size: 0.8rem;
        padding: 4px 12px;
        margin-right: 4px;
    }
    .chip-row .stButton > button:hover { background: #1a3f7a; }

    /* ---------- fraud score bar ---------- */
    .fraud-high { color: #fca5a5; font-weight: 700; }
    .fraud-med  { color: #fcd34d; font-weight: 600; }

    /* ---------- calendar row ---------- */
    .cal-high   { border-left: 4px solid #ef4444; }
    .cal-medium { border-left: 4px solid #f59e0b; }
    .cal-low    { border-left: 4px solid #10b981; }
    .cal-row {
        background: #131e33;
        border-radius: 8px;
        padding: 10px 16px;
        margin-bottom: 8px;
    }

    /* ---------- misc ---------- */
    .stDataFrame { border-radius: 10px; overflow: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------

def _init_session_state() -> None:
    """Initialise all required session-state keys exactly once."""
    defaults: dict[str, Any] = {
        "user_identity": _DEMO_USERS[0],
        "chat_history": [],
        "session_id": str(uuid.uuid4())[:8].upper(),
        "reviewed_cases": set(),
        "active_query": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


_init_session_state()


# ---------------------------------------------------------------------------
# Helper — risk score → badge HTML
# ---------------------------------------------------------------------------

def _risk_badge(score: int) -> str:
    """Return an HTML badge string coloured by risk level."""
    if score < 35:
        cls, label = "badge-low", f"LOW  ({score})"
    elif score < 70:
        cls, label = "badge-medium", f"MEDIUM  ({score})"
    else:
        cls, label = "badge-high", f"HIGH  ({score})"
    return f'<span class="badge {cls}">{label}</span>'


def _fraud_badge(score: int) -> str:
    """Return an HTML badge string for fraud score."""
    css = "fraud-high" if score >= 80 else "fraud-med"
    return f'<span class="{css}">{score}</span>'


def _format_inr(amount: float) -> str:
    """Format a float as Indian Rupee string with commas."""
    if amount >= 1_00_00_000:  # crore
        return f"₹{amount / 1_00_00_000:.2f} Cr"
    if amount >= 1_00_000:  # lakh
        return f"₹{amount / 1_00_000:.2f} L"
    return f"₹{amount:,.0f}"


# ---------------------------------------------------------------------------
# Orchestrator call helper
# ---------------------------------------------------------------------------

def _run_orchestrator(query: str) -> dict[str, Any]:
    """
    Call the Auris orchestrator and return the response dict.

    Falls back to a structured mock response when the orchestrator is
    unavailable (ENV='local' / Snowflake not connected).
    """
    user = st.session_state.user_identity
    if _ORCHESTRATOR_AVAILABLE and _orchestrator is not None:
        return _orchestrator.run(
            query=query,
            user_identity=user,
            rag_results=None,
        )

    # --- Mock fallback ---
    risk_score = hash(query) % 100  # deterministic for same query
    return {
        "query": query,
        "user": user,
        "agents_invoked": ["RiskAssessmentAgent", "FraudDetectionAgent"],
        "overall_risk_score": abs(risk_score),
        "summary": (
            f"[Mock] Analysis complete for: *{query}*\n\n"
            "In local mode, the orchestrator is simulated. "
            "Connect to Snowflake Cortex for live AI responses. "
            "Based on recent transaction patterns, moderate AML risk signals "
            "are detected. Recommend escalation review for flagged accounts."
        ),
        "flagged_items": [
            {"txn_id": "TXN12345678", "amount": 12_50_000, "reason": "Exceeds ₹10L threshold"},
            {"txn_id": "TXN87654321", "amount": 9_80_000, "reason": "Structuring pattern"},
        ],
        "citations": [
            {
                "doc_name": "RBI Master Direction on KYC",
                "section": "Section 16 — Enhanced Due Diligence",
                "snippet": "Reporting entities shall apply enhanced due diligence measures for high-risk customers...",
            },
            {
                "doc_name": "PMLA 2002",
                "section": "Section 12 — Obligations of banking companies",
                "snippet": "Every banking company shall maintain records of all transactions of value specified by the Director...",
            },
        ],
        "recommendations": [
            "File STR for TXN12345678 with FIU-IND within 7 days.",
            "Place customer account on enhanced monitoring for 90 days.",
            "Verify source of funds documentation for transactions >₹10L.",
            "Review structuring pattern — 3 sub-threshold deposits within 48 hrs.",
        ],
        "per_agent_results": {},
        "timestamp": datetime.now().isoformat(),
    }


# ===========================================================================
# SIDEBAR
# ===========================================================================

with st.sidebar:
    # Logo
    st.markdown(
        """
        <div style="text-align:center; padding: 10px 0 6px 0;">
            <span style="font-size:2.2rem;">⚡</span>
            <div style="font-size:1.5rem; font-weight:800; color:#93c5fd; letter-spacing:0.05em;">
                Auris
            </div>
            <div style="font-size:0.75rem; color:#64748b; margin-top:2px;">
                Compliance Copilot
            </div>
        </div>
        <hr style="border-color:#1e3a5f; margin: 10px 0;">
        """,
        unsafe_allow_html=True,
    )

    # ---- User selector ----
    st.markdown("**👤 Active User**")
    user_names = [u["username"] for u in _DEMO_USERS]
    selected_name = st.selectbox(
        "Select user",
        options=user_names,
        index=user_names.index(st.session_state.user_identity["username"]),
        label_visibility="collapsed",
    )
    selected_user = next(u for u in _DEMO_USERS if u["username"] == selected_name)
    st.session_state.user_identity = selected_user

    role = selected_user["role"]
    role_color = _ROLE_COLOR.get(role, "#3b82f6")
    st.markdown(
        f'<span class="badge badge-role" style="background:#1e3a5f; color:{role_color};">'
        f"🔰 {_ROLE_DISPLAY.get(role, role)}</span>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div style="font-size:0.72rem; color:#475569; margin-top:4px;">'
        f"Session: {st.session_state.session_id}</div>",
        unsafe_allow_html=True,
    )

    st.markdown("<hr style='border-color:#1e3a5f; margin:12px 0;'>", unsafe_allow_html=True)

    # ---- Snowflake connection status ----
    if ENV == "local":
        st.markdown(
            '<span style="font-size:0.82rem;">🟡 &nbsp;<b>Local Mock Mode</b> '
            '<span style="color:#64748b;">— Snowflake not connected</span></span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span style="font-size:0.82rem;">🟢 &nbsp;<b>Snowflake Connected</b></span>',
            unsafe_allow_html=True,
        )
    st.markdown(
        f'<div style="font-size:0.72rem; color:#475569; margin-top:2px;">'
        f"Model: {CORTEX_MODEL}</div>",
        unsafe_allow_html=True,
    )

    st.markdown("<hr style='border-color:#1e3a5f; margin:12px 0;'>", unsafe_allow_html=True)

    # ---- Quick actions ----
    st.markdown("**⚡ Quick Actions**")

    if st.button("🔍 Run AML Summary Report"):
        st.session_state.active_query = "Generate AML summary for October 2026"
        st.rerun()

    if st.button("📊 Basel Liquidity Check"):
        st.session_state.active_query = "What is our current LCR status?"
        st.rerun()

    if st.button("🔔 Check Fraud Alerts"):
        st.session_state.active_query = "Check for structuring patterns"
        st.rerun()

    st.markdown("<hr style='border-color:#1e3a5f; margin:12px 0;'>", unsafe_allow_html=True)

    # ---- Credits tracker ----
    st.markdown(
        """
        <div style="font-size:0.78rem; color:#64748b;">
            <b>💳 Cortex Credits</b><br>
            <span style="color:#93c5fd; font-size:1rem;">~$12 used</span>
            <span style="color:#475569;"> of $400</span>
            <div style="background:#1e3a5f; border-radius:4px; height:6px; margin-top:6px;">
                <div style="background:#3b82f6; width:3%; height:6px; border-radius:4px;"></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ===========================================================================
# MAIN AREA — header + ENV banner
# ===========================================================================

st.markdown(
    """
    <div style="display:flex; align-items:center; margin-bottom:4px;">
        <span style="font-size:2rem; margin-right:10px;">⚡</span>
        <div>
            <span style="font-size:1.6rem; font-weight:800; color:#93c5fd;">Auris</span>
            <span style="font-size:0.9rem; color:#64748b; margin-left:10px;">
                Regulatory Intelligence & Compliance Copilot
            </span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if ENV == "local":
    st.info(
        "🟡 **Running in local mock mode** — Snowflake not connected. "
        "Showing simulated data. Set `ENV=production` and configure "
        "Snowflake credentials to enable live AI analysis.",
        icon=None,
    )

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_query, tab_risk, tab_fraud, tab_reports = st.tabs(
    ["💬 Query Interface", "📊 Risk Dashboard", "🚨 Fraud Cases", "📋 Regulatory Reports"]
)


# ===========================================================================
# TAB 1 — QUERY INTERFACE
# ===========================================================================
with tab_query:
    st.markdown("### 💬 Ask Auris")
    st.markdown(
        "<p style='color:#64748b; font-size:0.9rem;'>"
        "Ask anything about risk, fraud, or regulations. "
        "Auris will invoke the relevant agents and synthesise a response from your documents and data."
        "</p>",
        unsafe_allow_html=True,
    )

    # Pre-populate from quick actions
    default_query = st.session_state.pop("active_query", "") if "active_query" in st.session_state else ""

    # ---- Suggested query chips ----
    st.markdown("**Suggested queries:**")
    chip_cols = st.columns(len(_QUICK_QUERIES))
    chip_clicked: str = ""
    for col, q in zip(chip_cols, _QUICK_QUERIES):
        with col:
            if st.button(q, key=f"chip_{hash(q)}", help=q):
                chip_clicked = q

    query_value = chip_clicked or default_query

    # ---- Query input ----
    user_query = st.text_area(
        "Your query",
        value=query_value,
        placeholder="Ask Auris anything about risk, fraud, or regulations...",
        height=110,
        label_visibility="collapsed",
    )

    col_submit, col_clear = st.columns([1, 5])
    with col_submit:
        submit_clicked = st.button("⚡ Analyze", type="primary", use_container_width=True)

    # ---- Analysis result ----
    if submit_clicked and user_query.strip():
        with st.spinner("🔍 Auris is analyzing — invoking agents..."):
            try:
                result = _run_orchestrator(user_query.strip())
            except Exception as err:
                st.error(f"Analysis failed: {err}")
                result = None

        if result:
            score: int = result.get("overall_risk_score", 0)
            agents: list[str] = result.get("agents_invoked", [])
            summary: str = result.get("summary", "")
            citations: list[dict] = result.get("citations", [])
            recommendations: list[str] = result.get("recommendations", [])
            flagged: list[dict] = result.get("flagged_items", [])

            with st.expander("📋 Analysis Results", expanded=True):
                # Risk badge + agents
                col_r, col_a = st.columns([1, 3])
                with col_r:
                    st.markdown(f"**Overall Risk:**&ensp;{_risk_badge(score)}", unsafe_allow_html=True)
                with col_a:
                    agent_pills = "".join(
                        f'<span class="badge badge-agent">🤖 {a.replace("Agent","").strip()}</span>'
                        for a in agents
                    )
                    st.markdown(f"**Agents:**&ensp;{agent_pills}", unsafe_allow_html=True)

                # Summary card
                st.markdown(
                    f'<div class="auris-summary-card">{summary}</div>',
                    unsafe_allow_html=True,
                )

                # Recommendations
                if recommendations:
                    st.markdown("**📌 Recommendations:**")
                    for rec in recommendations:
                        st.markdown(f"- {rec}")

                # Citations
                if citations:
                    st.markdown("**📚 Source Citations:**")
                    for i, cit in enumerate(citations):
                        with st.expander(
                            f"📄 {cit.get('doc_name', 'Source')} — {cit.get('section', '')}"
                        ):
                            st.markdown(
                                f'<div class="citation-box">{cit.get("snippet", "")}</div>',
                                unsafe_allow_html=True,
                            )

                # Flagged items table
                if flagged:
                    st.markdown(f"**🚩 Flagged Items ({len(flagged)}):**")
                    st.dataframe(
                        pd.DataFrame(flagged),
                        use_container_width=True,
                        hide_index=True,
                    )

            # Add to chat history
            st.session_state.chat_history.append(
                {
                    "query": user_query.strip(),
                    "risk_score": score,
                    "timestamp": datetime.now().strftime("%H:%M"),
                    "agents": agents,
                }
            )

    # ---- Chat history ----
    history = st.session_state.chat_history[-5:]
    if history:
        st.markdown("<hr style='border-color:#1e3a5f;'>", unsafe_allow_html=True)
        st.markdown("**🕑 Recent Queries**")
        for item in reversed(history):
            score_h = item["risk_score"]
            badge_h = _risk_badge(score_h)
            st.markdown(
                f'<div class="auris-card" style="padding:10px 16px;">'
                f'<span style="color:#64748b; font-size:0.78rem;">{item["timestamp"]}</span>'
                f'&ensp;{badge_h}'
                f'<span style="color:#cdd9f0; margin-left:10px; font-size:0.88rem;">'
                f'{item["query"][:90]}{"..." if len(item["query"]) > 90 else ""}'
                f"</span></div>",
                unsafe_allow_html=True,
            )


# ===========================================================================
# TAB 2 — RISK DASHBOARD
# ===========================================================================
with tab_risk:
    st.markdown("### 📊 Risk Dashboard")
    st.markdown(
        "<p style='color:#64748b; font-size:0.9rem;'>"
        "Real-time transaction risk monitoring and AML signal tracking."
        "</p>",
        unsafe_allow_html=True,
    )

    # ---- Load data ----
    try:
        metrics = get_mock_metrics()
        df_txn = get_mock_transactions(n=50)
        df_ts = get_mock_risk_timeseries(days=7)
    except Exception as err:
        st.error(f"Failed to load risk data: {err}")
        metrics = {}
        df_txn = pd.DataFrame()
        df_ts = pd.DataFrame()

    # ---- Metric row ----
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("📦 Total Transactions (Today)", f"{metrics.get('total_txns', 0):,}")
    m2.metric(
        "🚩 Flagged Transactions",
        f"{metrics.get('flagged_count', 0):,}",
        delta=f"+{metrics.get('flagged_count', 0) - 80} vs yesterday",
        delta_color="inverse",
    )
    m3.metric("🔴 High Risk Count", f"{metrics.get('high_risk_count', 0):,}")
    m4.metric(
        "💰 Total Flagged Amount",
        _format_inr(metrics.get("total_flagged_amount", 0)),
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # ---- Charts row ----
    if _PLOTLY_AVAILABLE and not df_ts.empty:
        col_bar, col_scatter = st.columns(2)

        with col_bar:
            st.markdown("**Transaction Volume by Risk Level (Last 7 Days)**")
            fig_bar = px.bar(
                df_ts,
                x="DATE",
                y="TRANSACTION_COUNT",
                color="RISK_LEVEL",
                barmode="group",
                color_discrete_map={
                    "Low": "#10b981",
                    "Medium": "#f59e0b",
                    "High": "#ef4444",
                },
                template="plotly_dark",
                labels={"TRANSACTION_COUNT": "Transactions", "DATE": "Date"},
            )
            fig_bar.update_layout(
                plot_bgcolor="#0f1623",
                paper_bgcolor="#0f1623",
                legend_title_text="Risk Level",
                margin=dict(l=0, r=0, t=10, b=0),
                height=300,
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        with col_scatter:
            st.markdown("**Risk Score Distribution (Amount vs Score)**")
            if not df_txn.empty:
                fig_scatter = px.scatter(
                    df_txn,
                    x="AMOUNT",
                    y="RISK_SCORE",
                    color="AML_FLAG",
                    color_discrete_map={True: "#ef4444", False: "#10b981"},
                    hover_data=["TXN_ID", "CUSTOMER_NAME", "TRANSACTION_TYPE"],
                    template="plotly_dark",
                    labels={
                        "AMOUNT": "Amount (₹)",
                        "RISK_SCORE": "Risk Score",
                        "AML_FLAG": "AML Flag",
                    },
                )
                fig_scatter.update_layout(
                    plot_bgcolor="#0f1623",
                    paper_bgcolor="#0f1623",
                    margin=dict(l=0, r=0, t=10, b=0),
                    height=300,
                )
                st.plotly_chart(fig_scatter, use_container_width=True)
    else:
        if not _PLOTLY_AVAILABLE:
            st.warning("Install `plotly` for interactive charts: `pip install plotly`")

    # ---- High-risk transactions table ----
    st.markdown("**🔴 Recent High-Risk Transactions (Top 10)**")
    if not df_txn.empty:
        high_risk = df_txn[df_txn["RISK_LEVEL"] == "High"].head(10).copy()
        high_risk["AMOUNT"] = high_risk["AMOUNT"].apply(_format_inr)
        display_cols = ["TXN_ID", "CUSTOMER_NAME", "AMOUNT", "RISK_SCORE", "AML_FLAG", "DATE"]
        st.dataframe(
            high_risk[display_cols].rename(
                columns={
                    "CUSTOMER_NAME": "Customer",
                    "RISK_SCORE": "Risk Score",
                    "AML_FLAG": "AML Flag",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No transaction data available.")


# ===========================================================================
# TAB 3 — FRAUD CASES
# ===========================================================================
with tab_fraud:
    st.markdown("### 🚨 Fraud Cases & Investigation")
    st.markdown(
        "<p style='color:#64748b; font-size:0.9rem;'>"
        "Active fraud cases, watchlist matches, and structuring analysis."
        "</p>",
        unsafe_allow_html=True,
    )

    # ---- Load data ----
    try:
        metrics_f = get_mock_metrics()
        df_fraud = get_mock_fraud_cases(n=10)
        structuring_groups = get_mock_structuring_groups()
    except Exception as err:
        st.error(f"Failed to load fraud data: {err}")
        metrics_f = {}
        df_fraud = pd.DataFrame()
        structuring_groups = []

    # ---- Metric row ----
    f1, f2, f3 = st.columns(3)
    f1.metric("👁️ Watchlist Hits Today", metrics_f.get("watchlist_hits", 0))
    f2.metric("🔄 Structuring Alerts", metrics_f.get("structuring_alerts", 0))
    f3.metric("⏳ Pending Review", metrics_f.get("pending_review", 0))

    st.markdown("<br>", unsafe_allow_html=True)

    # ---- Fraud cases detail ----
    st.markdown("**📂 Active Fraud Cases**")
    if not df_fraud.empty:
        for _, row in df_fraud.iterrows():
            case_id = row["CASE_ID"]
            already_reviewed = case_id in st.session_state.reviewed_cases
            status_display = "✅ Reviewed" if already_reviewed else row["STATUS"]

            with st.expander(
                f"🔴 {case_id} | {row['CUSTOMER']} | "
                f"Score: {row['FRAUD_SCORE']} | {status_display}"
            ):
                col_d1, col_d2, col_d3 = st.columns(3)
                col_d1.markdown(f"**TXN ID:** `{row['TXN_ID']}`")
                col_d2.markdown(f"**Amount:** {_format_inr(row['AMOUNT'])}")
                col_d3.markdown(f"**Opened:** {row['OPENED_DATE']}")

                st.markdown(f"**Fraud Score:** {_fraud_badge(row['FRAUD_SCORE'])}", unsafe_allow_html=True)
                st.markdown(f"**Patterns Detected:** {row['PATTERNS_DETECTED']}")
                st.markdown(f"**Assigned To:** {row['ASSIGNED_TO']}")

                if not already_reviewed:
                    if st.button(f"✅ Mark as Reviewed", key=f"review_{case_id}"):
                        st.session_state.reviewed_cases.add(case_id)
                        st.success(f"Case {case_id} marked as reviewed.")
                        st.rerun()
                else:
                    st.success("This case has been marked as reviewed.")
    else:
        st.info("No fraud cases to display.")

    st.markdown("<hr style='border-color:#1e3a5f; margin:20px 0;'>", unsafe_allow_html=True)

    # ---- Structuring pattern view ----
    st.markdown("**🔄 Suspected Structuring Groups**")
    st.markdown(
        "<p style='color:#64748b; font-size:0.85rem;'>"
        "Customers with multiple sub-threshold transactions that may indicate structuring."
        "</p>",
        unsafe_allow_html=True,
    )

    for group in structuring_groups:
        with st.expander(
            f"👤 {group['customer']} — "
            f"{group['transaction_count']} transactions, "
            f"Total: {_format_inr(group['total_amount'])}"
        ):
            df_group = pd.DataFrame(group["transactions"])
            df_group["amount"] = df_group["amount"].apply(_format_inr)
            st.dataframe(
                df_group.rename(
                    columns={
                        "txn_id": "TXN ID",
                        "amount": "Amount",
                        "date": "Date",
                        "type": "Type",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
            st.warning(
                f"⚠️ {group['transaction_count']} transactions totalling "
                f"{_format_inr(group['total_amount'])} — possible structuring to "
                "avoid ₹10L reporting threshold."
            )


# ===========================================================================
# TAB 4 — REGULATORY REPORTS
# ===========================================================================
with tab_reports:
    st.markdown("### 📋 Regulatory Reports")
    st.markdown(
        "<p style='color:#64748b; font-size:0.9rem;'>"
        "Generate, review, and export regulatory reports for RBI, FIU-IND, SEBI, and more."
        "</p>",
        unsafe_allow_html=True,
    )

    # ---- Report generator ----
    st.markdown("#### 📄 Generate New Report")

    col_type, col_period = st.columns(2)
    with col_type:
        report_type = st.selectbox(
            "Report Type",
            ["AML Summary Report", "Basel LCR Disclosure", "FINTRAC Report"],
        )
    with col_period:
        col_from, col_to = st.columns(2)
        with col_from:
            date_from = st.date_input("From", value=date(2026, 10, 1))
        with col_to:
            date_to = st.date_input("To", value=date(2026, 10, 31))

    period_str = f"{date_from.strftime('%d %b %Y')} – {date_to.strftime('%d %b %Y')}"
    gen_by = st.session_state.user_identity["username"]

    generate_clicked = st.button("📄 Generate Report", type="primary")

    if generate_clicked:
        with st.spinner("Generating regulatory report..."):
            try:
                if _REG_AGENT_AVAILABLE and _reg_agent is not None:
                    report_result = _reg_agent.run(
                        query=f"Generate {report_type} for period {period_str}",
                        user_identity=st.session_state.user_identity,
                    )
                    report_content = report_result.get("report_text") or report_result.get("summary", "")
                else:
                    # Mock report content
                    report_content = f"""
## {report_type}
**Period:** {period_str}
**Prepared by:** {gen_by}
**Generated:** {datetime.now().strftime('%d %b %Y, %H:%M')}

---

### EXECUTIVE SUMMARY

This report covers the regulatory compliance status for the period {period_str}.
All data has been sourced from the core banking system and validated against RBI Master Directions.

### KEY FINDINGS

- Total transactions processed: 42,350
- Transactions flagged for AML review: 87 (0.21%)
- Suspicious Transaction Reports (STRs) filed: 12
- High-risk customers under enhanced monitoring: 34
- Watchlist matches detected: 7

### AML COMPLIANCE STATUS

The institution remains in compliance with PMLA 2002 requirements.
All STRs have been filed within the prescribed 7-day window with FIU-IND.
Customer due diligence reviews are current for 98.3% of the customer base.

### RECOMMENDATIONS

- Complete KYC refresh for 67 dormant high-risk accounts by 31 Oct 2026.
- Review 3 pending STRs for completeness before filing deadline.
- Conduct staff AML training refresh scheduled for Nov 2026.

### REGULATORY CALENDAR COMPLIANCE

All scheduled submissions are on track. Next filing due: AML STR for Sep 2026 by 31 Oct 2026.
"""

            except Exception as err:
                st.error(f"Report generation failed: {err}")
                report_content = ""

        if report_content:
            st.markdown("---")
            st.markdown(f"#### {report_type} — {period_str}")
            st.markdown(report_content)

            # ---- PDF export ----
            try:
                pdf_bytes = export_report_to_pdf(
                    report_content=report_content,
                    report_type=report_type,
                    generated_by=gen_by,
                    period=period_str,
                )
                st.download_button(
                    label="📥 Export as PDF",
                    data=pdf_bytes,
                    file_name=f"Auris_{report_type.replace(' ', '_')}_{date_from.strftime('%Y%m')}.pdf",
                    mime="application/pdf",
                )
            except Exception as err:
                st.warning(
                    f"PDF export unavailable: {err}. "
                    "Install `fpdf2` with `pip install fpdf2`."
                )

    st.markdown("<hr style='border-color:#1e3a5f; margin:20px 0;'>", unsafe_allow_html=True)

    # ---- Recent reports table ----
    st.markdown("#### 📁 Recent Reports")
    try:
        df_reports = get_mock_regulatory_reports()
        st.dataframe(
            df_reports.rename(
                columns={
                    "REPORT_ID": "Report ID",
                    "REPORT_TYPE": "Type",
                    "PERIOD": "Period",
                    "GENERATED_BY": "Generated By",
                    "GENERATED_AT": "Date",
                    "STATUS": "Status",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
    except Exception as err:
        st.error(f"Failed to load recent reports: {err}")

    st.markdown("<hr style='border-color:#1e3a5f; margin:20px 0;'>", unsafe_allow_html=True)

    # ---- Regulatory calendar ----
    st.markdown("#### 📅 Regulatory Calendar — Q4 2026")
    st.markdown(
        "<p style='color:#64748b; font-size:0.85rem;'>"
        "Upcoming Indian banking regulatory deadlines."
        "</p>",
        unsafe_allow_html=True,
    )

    try:
        cal = get_regulatory_calendar()
        for item in cal:
            priority = item.get("priority", "Low")
            border_color = {"High": "#ef4444", "Medium": "#f59e0b", "Low": "#10b981"}.get(
                priority, "#10b981"
            )
            badge_color = {"High": "#7f1d1d", "Medium": "#78350f", "Low": "#064e3b"}.get(
                priority, "#064e3b"
            )
            badge_text_color = {"High": "#fca5a5", "Medium": "#fcd34d", "Low": "#6ee7b7"}.get(
                priority, "#6ee7b7"
            )
            st.markdown(
                f"""
                <div class="auris-card" style="border-left: 4px solid {border_color};">
                    <div style="display:flex; align-items:center; gap:10px;">
                        <span style="font-size:1.1rem; font-weight:700; color:#93c5fd; min-width:120px;">
                            📅 {item['deadline']}
                        </span>
                        <span class="badge" style="background:{badge_color}; color:{badge_text_color};">
                            {priority}
                        </span>
                        <span style="background:#1e3a5f; color:#93c5fd; padding:2px 8px;
                               border-radius:12px; font-size:0.75rem; font-weight:600;">
                            {item['regulator']}
                        </span>
                    </div>
                    <div style="color:#cbd5e1; font-size:0.88rem; margin-top:6px;">
                        {item['description']}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    except Exception as err:
        st.error(f"Failed to load regulatory calendar: {err}")
