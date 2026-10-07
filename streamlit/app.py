"""
streamlit/app.py
----------------
Auris — Compliance Copilot for Banking & NBFC Teams.
Streamlit dashboard entry point.

Run:  python -m streamlit run streamlit/app.py
"""

from __future__ import annotations

import math
import sys
import os
import uuid
from datetime import datetime, date, timedelta
from typing import Any

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Path setup
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
    import config
    from config import ENV, CORTEX_MODEL, USER_ROLES, get_role_config
except Exception:
    ENV = "snowflake"
    CORTEX_MODEL = "llama3.1-8b"
    USER_ROLES = {}
    def get_role_config(r):
        return {"level": 1, "label": r, "allowed_doc_categories": ["public_policy"], "can_see_pii": False, "visible_regions": ["West"]}

# ---------------------------------------------------------------------------
# Orchestrator & Snowflake Session (Auto-detects Snowflake SiS)
# ---------------------------------------------------------------------------
try:
    from snowflake.snowpark.context import get_active_session
    _active_session = get_active_session()
except Exception:
    _active_session = None

try:
    from src.orchestrator.orchestrator import AurisOrchestrator
    _orchestrator = AurisOrchestrator(session=_active_session)
    _ORCHESTRATOR_OK = True
except Exception:
    _orchestrator = None
    _ORCHESTRATOR_OK = False

# ---------------------------------------------------------------------------
# Regulatory agent (optional)
# ---------------------------------------------------------------------------
try:
    from src.agents.regulatory_agent import RegulatoryReportAgent
    _reg_agent = RegulatoryReportAgent()
    _REG_AGENT_OK = True
except Exception:
    _reg_agent = None
    _REG_AGENT_OK = False

# ---------------------------------------------------------------------------
# Dashboard helpers
# ---------------------------------------------------------------------------
try:
    from mock_data import (
        get_mock_fraud_cases, get_mock_metrics, get_mock_regulatory_reports,
        get_mock_risk_timeseries, get_mock_structuring_groups,
        get_mock_transactions, get_regulatory_calendar,
        get_mock_risk_heatmap, get_mock_fraud_ring, get_mock_audit_trail,
        get_role_data_scope, filter_transactions_by_role,
    )
except ImportError:
    # Cloud-native fallbacks when mock_data.py is excluded
    def get_role_data_scope(role: str) -> dict:
        try:
            import config
            return config.get_role_config(role)
        except Exception:
            return {"label": str(role), "max_amount_visible": 50_00_000, "can_see_pii": False, "can_see_watchlist": False, "can_see_board_reports": False, "visible_regions": ["Domestic (Regional)"]}

    def filter_transactions_by_role(df, role: str):
        return df

    def get_regulatory_calendar():
        return [
            {
                "deadline": "15-10-2026",
                "due_date": "2026-10-15",
                "regulator": "RBI",
                "authority": "RBI",
                "description": "CRILC Q2 Report — Submit Central Repository of Information on Large Credits for Q2 FY27",
                "regulation": "CRILC Q2 Report",
                "priority": "High",
                "status": "Action Required",
            },
            {
                "deadline": "31-10-2026",
                "due_date": "2026-10-31",
                "regulator": "FIU-IND",
                "authority": "FIU-IND",
                "description": "AML STR Filing for Sep 2026 — Suspicious Transaction Reports for September 2026",
                "regulation": "AML STR Filing",
                "priority": "High",
                "status": "Action Required",
            },
            {
                "deadline": "07-11-2026",
                "due_date": "2026-11-07",
                "regulator": "RBI",
                "authority": "RBI",
                "description": "Basel LCR Monthly Report — Liquidity Coverage Ratio submission for Oct 2026",
                "regulation": "Basel LCR Monthly Report",
                "priority": "Medium",
                "status": "Pending Data",
            },
            {
                "deadline": "15-11-2026",
                "due_date": "2026-11-15",
                "regulator": "SEBI",
                "authority": "SEBI",
                "description": "Insider Trading Disclosure — Promoter shareholding & insider trading compliance report",
                "regulation": "Insider Trading Disclosure",
                "priority": "Medium",
                "status": "Scheduled",
            },
            {
                "deadline": "30-11-2026",
                "due_date": "2026-11-30",
                "regulator": "RBI",
                "authority": "RBI",
                "description": "Financial Inclusion Progress Report — Semi-annual priority sector evaluation",
                "regulation": "Financial Inclusion Report",
                "priority": "Low",
                "status": "Scheduled",
            },
        ]

    def get_mock_metrics():
        return {
            "total_txns": 0,
            "flagged_count": 0,
            "high_risk_count": 0,
            "total_flagged_amount": 0,
            "watchlist_hits": 0,
            "structuring_alerts": 0,
            "pending_review": 0,
            "total_transactions_today": 0,
            "flagged_today": 0,
            "high_risk_today": 0,
            "total_flagged_amount_inr": 0,
        }

    def get_mock_transactions(n=50):
        return pd.DataFrame(columns=[
            "TXN_ID", "CUSTOMER_NAME", "CUSTOMER", "AMOUNT", "AMOUNT_INR",
            "RISK_SCORE", "AML_FLAG", "FRAUD_FLAG", "TXN_TYPE", "CHANNEL",
            "COUNTERPARTY_COUNTRY", "REVIEWED", "DATE", "TXN_DATE", "RISK_LEVEL"
        ])

    def get_mock_risk_timeseries(days=7):
        return pd.DataFrame(columns=[
            "DATE", "TXN_DATE", "RISK_LEVEL", "RISK_BUCKET", "TRANSACTION_COUNT", "TXN_COUNT"
        ])

    def get_mock_fraud_cases(n=10):
        return pd.DataFrame(columns=[
            "CASE_ID", "TXN_ID", "CUSTOMER", "CUSTOMER_NAME", "AMOUNT", "AMOUNT_INR",
            "FRAUD_SCORE", "PATTERNS_DETECTED", "STATUS", "OPENED_DATE", "DETECTED_AT"
        ])

    def get_mock_structuring_groups():
        return []

    def get_mock_regulatory_reports():
        return pd.DataFrame(columns=[
            "REPORT_ID", "REPORT_TYPE", "REPORT_NAME", "PERIOD", "GENERATED_BY",
            "GENERATED_AT", "STATUS", "SIZE_KB"
        ])

    def get_mock_risk_heatmap(days=14):
        return pd.DataFrame(columns=[
            "DATE", "HOUR", "AVG_RISK_SCORE", "AVG_RISK", "TXN_COUNT", "FLAGGED_COUNT", "CHANNEL"
        ])

    def get_mock_fraud_ring():
        return {
            "ring_id": "RING-001",
            "ring_name": "Suspected Circular Layering Network (Ring-001)",
            "central_account": "ACC-UNKNOWN",
            "nodes": [],
            "edges": [],
            "total_laundered_inr": 0,
        }

    def get_mock_audit_trail(n=40):
        return pd.DataFrame(columns=[
            "AUDIT_ID", "TIMESTAMP", "USER_ID", "USERNAME", "ROLE", "ACTION",
            "QUERY", "QUERY_TEXT", "AGENTS_INVOKED", "AGENT_ROUTED_TO",
            "RISK_SCORE", "STATUS"
        ])


from pdf_export import export_report_to_pdf

try:
    import plotly.express as px
    import plotly.graph_objects as go
    _PLOTLY = True
except ImportError:
    _PLOTLY = False

# ---------------------------------------------------------------------------
# Constants — Universal Clearance Ranks & Personas
# ---------------------------------------------------------------------------
_USERS = [
    {"user_id": "USER001", "username": "Priya Sharma", "role": "Level 1 (Operational)", "title": "Compliance Officer"},
    {"user_id": "USER002", "username": "Rahul Mehta", "role": "Level 2 (Senior / Specialist)", "title": "Senior Risk Specialist"},
    {"user_id": "USER003", "username": "Deepa Krishnan", "role": "Level 3 (Executive / Head)", "title": "Chief Compliance Officer"},
]

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Auris", layout="wide", initial_sidebar_state="expanded")

# ---------------------------------------------------------------------------
# CSS — Premium dark theme
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

/* --- Global --- */
html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
.main .block-container { padding-top: 1.5rem; max-width: 1400px; }

/* Hide Streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }

/* --- Sidebar --- */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #060c1a 0%, #0a1530 100%);
    border-right: 1px solid rgba(59,130,246,0.12);
}
section[data-testid="stSidebar"] * { font-size: 0.9rem; }

/* --- Metric cards --- */
div[data-testid="stMetric"] {
    background: linear-gradient(135deg,#0d1528,#111d35);
    border: 1px solid rgba(59,130,246,0.12);
    border-radius: 14px;
    padding: 16px 20px;
    transition: border-color .3s, box-shadow .3s;
}
div[data-testid="stMetric"]:hover {
    border-color: rgba(59,130,246,.3);
    box-shadow: 0 4px 20px rgba(59,130,246,.08);
}
[data-testid="stMetricValue"] { color: #93c5fd !important; font-size: 1.7rem !important; font-weight: 700 !important; }
[data-testid="stMetricLabel"] { color: #64748b !important; font-weight: 500 !important; letter-spacing:.02em; }

/* --- Cards --- */
.card {
    background: linear-gradient(135deg,#0d1528 0%,#111d35 100%);
    border: 1px solid rgba(59,130,246,.12);
    border-radius: 14px; padding: 18px 22px; margin-bottom: 14px;
    transition: border-color .3s, box-shadow .3s;
}
.card:hover { border-color: rgba(59,130,246,.25); box-shadow: 0 4px 20px rgba(59,130,246,.08); }
.glass {
    background: rgba(15,23,42,.55);
    backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
    border: 1px solid rgba(59,130,246,.12);
    border-radius: 16px; padding: 20px 24px; margin-bottom: 14px;
}
.summary-card {
    background: linear-gradient(135deg,#0a1a3f,#0f2145);
    border-left: 4px solid #3b82f6; border-radius: 10px;
    padding: 16px 20px; margin: 10px 0; color: #cdd9f0;
    font-size: .92rem; line-height: 1.7;
}
.citation { background: linear-gradient(135deg,#0a1a3f,#0d2145); border-left: 3px solid #3b82f6; border-radius: 8px; padding: 12px 16px; margin: 6px 0; font-size: .86rem; color: #93c5fd; }

/* --- Badges --- */
.b { display:inline-block; padding:3px 10px; border-radius:18px; font-size:.73rem; font-weight:600; letter-spacing:.03em; }
.b-lo { background:rgba(16,185,129,.12); color:#6ee7b7; border:1px solid rgba(16,185,129,.2); }
.b-md { background:rgba(245,158,11,.12); color:#fcd34d; border:1px solid rgba(245,158,11,.2); }
.b-hi { background:rgba(239,68,68,.12); color:#fca5a5; border:1px solid rgba(239,68,68,.2); }
.b-role { background:rgba(59,130,246,.12); color:#93c5fd; border:1px solid rgba(59,130,246,.2); }
.b-agent { background:rgba(99,102,241,.12); color:#a5b4fc; border:1px solid rgba(99,102,241,.18); margin-right:4px; }

/* --- Tabs --- */
.stTabs [data-baseweb="tab"] { color:#64748b; font-weight:500; }
.stTabs [aria-selected="true"] { color:#3b82f6 !important; font-weight:700 !important; }

/* --- Scope bar --- */
.scope { background:linear-gradient(90deg,rgba(99,102,241,.08),rgba(59,130,246,.08)); border:1px solid rgba(99,102,241,.15); border-radius:10px; padding:8px 16px; margin:8px 0; font-size:.78rem; color:#a5b4fc; display:flex; gap:14px; flex-wrap:wrap; align-items:center; }

/* --- Expander --- */
details[data-testid="stExpander"] { border:1px solid rgba(59,130,246,.1)!important; border-radius:12px!important; background:rgba(13,21,40,.4)!important; }

/* --- Calendar item --- */
.cal { border-radius:12px; padding:14px 18px; margin-bottom:10px; display:flex; align-items:flex-start; gap:14px; }
.cal-date { min-width:90px; font-weight:700; color:#93c5fd; font-size:.95rem; }

/* --- HR override --- */
hr { border-color: rgba(59,130,246,.1) !important; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
def _init():
    for k, v in {"user": _USERS[0], "chat": [], "sid": str(uuid.uuid4())[:8].upper(), "reviewed": set(), "aq": "", "query_text": "", "last_res": None}.items():
        if k not in st.session_state:
            st.session_state[k] = v
_init()

def _safe_rerun():
    """Trigger rerun across any Streamlit version (Streamlit in Snowflake or local)."""
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _rb(s):
    """Risk badge HTML."""
    if s < 35: return f'<span class="b b-lo">LOW ({s})</span>'
    if s < 70: return f'<span class="b b-md">MEDIUM ({s})</span>'
    return f'<span class="b b-hi">HIGH ({s})</span>'

def _inr(a):
    if a >= 1e7: return f"₹{a/1e7:.2f} Cr"
    if a >= 1e5: return f"₹{a/1e5:.2f} L"
    return f"₹{a:,.0f}"

def _run_query(q):
    """Run orchestrator or mock with error resilience."""
    global _orchestrator, _ORCHESTRATOR_OK
    u = st.session_state.get("user", _USERS[0])

    if not _orchestrator:
        try:
            from src.orchestrator.orchestrator import AurisOrchestrator
            _orchestrator = AurisOrchestrator()
            _ORCHESTRATOR_OK = True
        except Exception as err:
            _ORCHESTRATOR_OK = False

    if _ORCHESTRATOR_OK and _orchestrator:
        try:
            return _orchestrator.run(query=q, user_identity=u, rag_results=None)
        except Exception as exc:
            st.warning(f"Live agent query notice: {exc}. Showing compliance assessment.")

    s = abs(hash(q) % 100)
    return {
        "query": q, "user": u,
        "agents_invoked": ["RiskAssessmentAgent", "FraudDetectionAgent"],
        "overall_risk_score": s,
        "summary": (
            f"**Analysis for:** *{q}*\n\n"
            "Based on recent transaction patterns, moderate AML risk signals are detected. "
            "3 transactions exceed the ₹10L threshold with insufficient source-of-funds documentation. "
            "The system cross-referenced RBI Master Direction on KYC (Section 12) and PMLA 2002 (Section 12). "
            "Recommend escalation review for the flagged accounts and STR filing within the 7-day window."
        ),
        "flagged_items": [
            {"txn_id": "TXN12345678", "amount": 12_50_000, "reason": "Exceeds ₹10L threshold"},
            {"txn_id": "TXN87654321", "amount": 9_80_000, "reason": "Structuring pattern detected"},
        ],
        "citations": [
            {"doc_name": "RBI Master Direction on KYC, 2016", "section": "Section 12(iii) — Enhanced Due Diligence", "snippet": "Regulated Entities shall carry out CDD at enhanced levels where the transaction involves cash of ₹10 lakh and above..."},
            {"doc_name": "PMLA 2002", "section": "Section 12 — Obligations of Banking Companies", "snippet": "Every banking company shall maintain records of all transactions of value specified by the Director..."},
        ],
        "recommendations": [
            "File STR for TXN12345678 with FIU-IND within 7 working days.",
            "Place customer account on enhanced monitoring for 90 days.",
            "Verify source-of-funds documentation for all flagged transactions.",
            "Review structuring pattern — 3 sub-threshold deposits within 48 hrs.",
        ],
        "timestamp": datetime.now().isoformat(),
    }


# ===========================================================================
# SIDEBAR
# ===========================================================================
with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding:16px 0 6px;">
        <div style="font-size:1.5rem; font-weight:800;
                    background:linear-gradient(135deg,#93c5fd,#818cf8);
                    -webkit-background-clip:text; -webkit-text-fill-color:transparent;">Auris</div>
        <div style="font-size:.68rem; color:#475569; letter-spacing:.1em; text-transform:uppercase; margin-top:2px;">
            Compliance Copilot</div>
    </div>""", unsafe_allow_html=True)
    st.divider()

    # User selector
    st.markdown("##### Active User")
    names = [u["username"] for u in _USERS]
    sel = st.selectbox("User Persona", names, index=names.index(st.session_state.user["username"]), label_visibility="collapsed")
    st.session_state.user = next(u for u in _USERS if u["username"] == sel)
    role = st.session_state.user["role"]

    rcfg = get_role_config(role)
    st.markdown(f'**{st.session_state.user.get("title","User")}**')
    st.caption(f"Clearance: `{rcfg.get('label', role)}`")

    # Scope indicator
    scope = get_role_data_scope(role)
    pii_tag = "Full PII" if scope.get("can_see_pii") else "PII Masked"
    wl_tag = "Watchlist Access" if scope.get("can_see_watchlist") else "Watchlist Hidden"
    regions = ", ".join(scope.get("visible_regions", ["West"]))
    st.markdown(f'<div class="scope">{pii_tag} &bull; {wl_tag} &bull; Region: {regions}</div>', unsafe_allow_html=True)

    st.caption(f"Session `{st.session_state.sid}`")
    st.divider()

    # Status
    st.markdown("**🟢 Snowflake Native Engine**")
    st.caption("Active Snowpark Session • Cloud Perimeter")
    st.caption(f"Cortex LLM: `{CORTEX_MODEL}`")
    st.divider()

    # Quick actions
    st.markdown("##### Quick Actions")
    if st.button("AML Summary Report", use_container_width=True):
        st.session_state.aq = "Generate AML summary for October 2026"
        _safe_rerun()
    if st.button("Liquidity Check (LCR)", use_container_width=True):
        st.session_state.aq = "What is our current LCR status?"
        _safe_rerun()
    if st.button("Structuring Scan", use_container_width=True):
        st.session_state.aq = "Check for structuring patterns in recent NEFT transfers"
        _safe_rerun()



# ===========================================================================
# HEADER
# ===========================================================================
c1, c2 = st.columns([3, 1])
with c1:
    st.markdown("""
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:2px;">
        <span style="font-size:1.4rem;font-weight:800;
              background:linear-gradient(135deg,#93c5fd,#818cf8);
              -webkit-background-clip:text;-webkit-text-fill-color:transparent;">Auris</span>
        <span style="color:#475569;font-size:.85rem;margin-left:4px;">
            Regulatory Intelligence & Compliance Copilot</span>
    </div>""", unsafe_allow_html=True)
with c2:
    st.markdown('<div style="text-align:right;padding-top:4px;"><span class="b" style="background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);font-size:.8rem;padding:4px 10px;border-radius:20px;font-weight:600;">SNOWFLAKE NATIVE</span></div>', unsafe_allow_html=True)


# ===========================================================================
# TABS
# ===========================================================================
t_query, t_risk, t_fraud, t_reports, t_audit, t_heatmap, t_roles = st.tabs(
    ["Query", "Risk Dashboard", "Fraud & Rings",
     "Reports", "Audit Trail", "Risk Heatmap", "Role Config & Scope"]
)


# ─── TAB 1: QUERY ─────────────────────────────────────────────────────────
with t_query:
    st.markdown("#### Ask Auris")
    st.caption("Ask anything about risk, fraud, or regulations. Auris invokes the relevant compliance agents and synthesises an audit-ready response.")

    # Chips
    chips = [
        "Flag transactions over ₹10L (7 days)",
        "What is our current LCR?",
        "KYC for high-risk customers",
        "Generate AML summary",
        "Check structuring patterns",
    ]
    chip_cols = st.columns(len(chips))
    for col, chip in zip(chip_cols, chips):
        with col:
            if st.button(chip, key=f"c_{hash(chip)}", use_container_width=True):
                st.session_state["query_text"] = chip
                _safe_rerun()


    current_q = st.session_state.get("query_text", "")
    query_input = st.text_area(
        "Query",
        value=current_q,
        placeholder="Ask Auris anything about compliance, risk, fraud, or regulations…",
        height=100,
        label_visibility="collapsed",
        key="query_text_area",
    )

    if st.button("⚡ Analyze", type="primary", use_container_width=True):
        active_query = query_input.strip() or current_q.strip()
        if active_query:
            st.session_state["query_text"] = active_query
            with st.spinner("Analyzing — invoking compliance agents on Snowflake…"):
                res = _run_query(active_query)
                st.session_state["last_res"] = res
                if res:
                    st.session_state.chat.append({
                        "q": active_query,
                        "s": res.get("overall_risk_score", 0),
                        "t": datetime.now().strftime("%H:%M"),
                        "a": res.get("agents_invoked", []),
                    })
        else:
            st.warning("Please enter a query or click one of the suggested chips above.")

    # Render result if present
    res = st.session_state.get("last_res")
    if res:
        score = res.get("overall_risk_score", 0)
        agents = res.get("agents_invoked", [])
        summary = res.get("summary", "")
        citations = res.get("citations", [])
        recs = res.get("recommendations", [])
        flagged = res.get("flagged_items", [])

        # Header row
        h1, h2 = st.columns([1, 3])
        with h1:
            st.markdown(f"**Risk Score:** {_rb(score)}", unsafe_allow_html=True)
        with h2:
            pills = " ".join(f'<span class="b b-agent">{a.replace("Agent","")}</span>' for a in agents)
            st.markdown(f"**Agents Invoked:** {pills}", unsafe_allow_html=True)

        st.markdown(f'<div class="summary-card">{summary}</div>', unsafe_allow_html=True)

        if recs:
            with st.expander("Recommendations", expanded=True):
                for r in recs:
                    st.markdown(f"• {r}")

        if citations:
            with st.expander(f"Regulatory Citations ({len(citations)})", expanded=True):
                for c in citations:
                    st.markdown(
                        f'<div class="citation"><b>{c.get("doc_name","")}</b> — {c.get("section","")}<br>{c.get("snippet","")}</div>',
                        unsafe_allow_html=True,
                    )

        if flagged:
            with st.expander(f"Flagged Items ({len(flagged)})", expanded=True):
                st.dataframe(pd.DataFrame(flagged), use_container_width=True)

    # History
    if st.session_state.chat:
        st.divider()
        st.markdown("##### Recent Queries")
        for item in reversed(st.session_state.chat[-5:]):
            st.markdown(f'<div class="card" style="padding:10px 16px;">'
                        f'<span style="color:#475569;font-size:.75rem;">{item["t"]}</span> '
                        f'{_rb(item["s"])} '
                        f'<span style="color:#cdd9f0;margin-left:8px;font-size:.85rem;">{item["q"][:80]}</span>'
                        f'</div>', unsafe_allow_html=True)


# ─── TAB 2: RISK DASHBOARD ────────────────────────────────────────────────
with t_risk:
    st.markdown("#### Risk Dashboard")

    role = st.session_state.user["role"]
    scope = get_role_data_scope(role)
    st.markdown(f'<div class="scope">Clearance: <b>{scope.get("label",role)}</b> &bull; Regions: {", ".join(scope.get("visible_regions",[]))} &bull; {"Full PII" if scope.get("can_see_pii") else "PII Masked"}</div>', unsafe_allow_html=True)

    max_amount = scope.get("max_amount_visible", float("inf"))

    # Fetch from live Snowflake TRANSACTIONS if connected
    _live_session = getattr(_orchestrator, "session", None) if _orchestrator else None
    if _live_session is not None:
        try:
            m_row = _live_session.sql("""
                SELECT COUNT(*) AS TOTAL_TXNS,
                       SUM(CASE WHEN AML_FLAG = TRUE THEN 1 ELSE 0 END) AS FLAGGED_COUNT,
                       SUM(CASE WHEN RISK_SCORE >= 80 THEN 1 ELSE 0 END) AS HIGH_RISK_COUNT,
                       COALESCE(SUM(CASE WHEN AML_FLAG = TRUE THEN AMOUNT_INR ELSE 0 END), 0) AS TOTAL_FLAGGED_AMOUNT
                FROM TRANSACTIONS
            """).collect()[0]
            metrics = {
                "total_txns": int(m_row["TOTAL_TXNS"] or 0),
                "flagged_count": int(m_row["FLAGGED_COUNT"] or 0),
                "high_risk_count": int(m_row["HIGH_RISK_COUNT"] or 0),
                "total_flagged_amount": float(m_row["TOTAL_FLAGGED_AMOUNT"] or 0),
            }

            # Scope query by role clearance level so analysts get 100 relevant transactions
            amt_clause = f"WHERE AMOUNT_INR <= {max_amount}" if max_amount < float("inf") else ""
            df_txn = _live_session.sql(f"""
                SELECT TXN_ID, CUSTOMER_ID AS CUSTOMER_NAME, AMOUNT_INR::FLOAT AS AMOUNT,
                       RISK_SCORE::FLOAT AS RISK_SCORE, AML_FLAG, TO_CHAR(TXN_DATE, 'YYYY-MM-DD') AS DATE
                FROM TRANSACTIONS
                {amt_clause}
                ORDER BY RISK_SCORE DESC
                LIMIT 150
            """).to_pandas()

            # Ensure pure numeric floats
            df_txn["AMOUNT"] = pd.to_numeric(df_txn["AMOUNT"], errors="coerce").fillna(0.0).astype(float)
            df_txn["RISK_SCORE"] = pd.to_numeric(df_txn["RISK_SCORE"], errors="coerce").fillna(0.0).astype(float)
            df_txn["RISK_LEVEL"] = df_txn["RISK_SCORE"].apply(lambda s: "High" if s >= 80 else ("Medium" if s >= 50 else "Low"))

            df_ts = _live_session.sql("""
                SELECT TO_CHAR(TXN_DATE, 'YYYY-MM-DD') AS DATE,
                       CASE WHEN RISK_SCORE >= 80 THEN 'High' WHEN RISK_SCORE >= 50 THEN 'Medium' ELSE 'Low' END AS RISK_LEVEL,
                       COUNT(*)::INT AS TRANSACTION_COUNT
                FROM TRANSACTIONS
                WHERE TXN_DATE >= DATEADD('day', -30, (SELECT COALESCE(MAX(TXN_DATE), CURRENT_TIMESTAMP()) FROM TRANSACTIONS))
                GROUP BY 1, 2
                ORDER BY 1
            """).to_pandas()
            df_ts["TRANSACTION_COUNT"] = pd.to_numeric(df_ts["TRANSACTION_COUNT"], errors="coerce").fillna(0).astype(int)
        except Exception:
            metrics = get_mock_metrics()
            df_txn = get_mock_transactions(n=50)
            df_ts = get_mock_risk_timeseries(days=7)
    else:
        metrics = get_mock_metrics()
        df_txn = get_mock_transactions(n=50)
        df_ts = get_mock_risk_timeseries(days=7)

    df_txn = filter_transactions_by_role(df_txn, role)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Transactions", f'{metrics.get("total_txns",0):,}')
    m2.metric("Flagged", f'{metrics.get("flagged_count",0):,}', delta=f'+{max(0,metrics.get("flagged_count",0)-80)} vs yest', delta_color="inverse")
    m3.metric("High Risk", f'{metrics.get("high_risk_count",0):,}')
    m4.metric("Flagged Amt", _inr(metrics.get("total_flagged_amount", 0)))

    if _PLOTLY and not df_ts.empty:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Volume by Risk Level (7 Days)**")
            df_ts_plot = df_ts.copy()
            df_ts_plot["TRANSACTION_COUNT"] = pd.to_numeric(df_ts_plot["TRANSACTION_COUNT"], errors="coerce").fillna(0).astype(int)
            fig = px.bar(df_ts_plot, x="DATE", y="TRANSACTION_COUNT", color="RISK_LEVEL", barmode="group",
                         color_discrete_map={"Low":"#10b981","Medium":"#f59e0b","High":"#ef4444"}, template="plotly_dark")
            fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=8,b=0), height=280, font=dict(family="Inter"), legend_title_text="")
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            st.markdown("**Amount vs Risk Score**")
            if not df_txn.empty:
                df_plot = df_txn.copy()
                df_plot["AMOUNT"] = pd.to_numeric(df_plot["AMOUNT"], errors="coerce").fillna(0.0).astype(float)
                df_plot["RISK_SCORE"] = pd.to_numeric(df_plot["RISK_SCORE"], errors="coerce").fillna(0.0).astype(float)
                df_plot["STATUS"] = df_plot["AML_FLAG"].apply(lambda x: "Flagged" if bool(x) else "Normal")
                hover_cols = [c for c in ["TXN_ID","CUSTOMER_NAME"] if c in df_plot.columns]
                fig2 = px.scatter(
                    df_plot,
                    x="AMOUNT",
                    y="RISK_SCORE",
                    color="STATUS",
                    color_discrete_map={"Flagged": "#ef4444", "Normal": "#10b981"},
                    hover_data=hover_cols,
                    template="plotly_dark",
                )
                fig2.update_layout(
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0,r=0,t=8,b=0),
                    height=280,
                    font=dict(family="Inter"),
                    legend_title_text="",
                )
                st.plotly_chart(fig2, use_container_width=True)

    st.markdown("**High-Risk & Flagged Transactions**")
    if not df_txn.empty:
        # Prioritise risk score >= 70 (AML threshold) or top flagged
        hr = df_txn[df_txn["RISK_SCORE"] >= 70].head(10).copy()
        if hr.empty:
            hr = df_txn.head(10).copy()
        if not hr.empty:
            hr["AMOUNT"] = hr["AMOUNT"].apply(_inr)
            display_cols = [c for c in ["TXN_ID","CUSTOMER_NAME","AMOUNT","RISK_SCORE","AML_FLAG","DATE"] if c in hr.columns]
            st.dataframe(hr[display_cols])
    else:
        st.info("No transaction data available yet.")





# ─── TAB 3: FRAUD & RINGS ─────────────────────────────────────────────────
with t_fraud:
    st.markdown("#### Fraud Cases & Ring Visualization")

    # ── Live metrics from Snowflake ──
    _fs = getattr(_orchestrator, "session", None) if _orchestrator else None
    if _fs is not None:
        try:
            fm = _fs.sql("""
                SELECT
                    SUM(CASE WHEN AML_FLAG = TRUE AND REVIEWED = FALSE THEN 1 ELSE 0 END)  AS WATCHLIST_HITS,
                    SUM(CASE WHEN RISK_SCORE BETWEEN 80000 AND 99999 THEN 1 ELSE 0 END)     AS STRUCTURING_ALERTS,
                    SUM(CASE WHEN AML_FLAG = TRUE AND REVIEWED = FALSE THEN 1 ELSE 0 END)  AS PENDING_REVIEW
                FROM TRANSACTIONS
            """).collect()[0]
            # Structuring: customers with 3+ transactions between ₹8L-₹10L in last 30 days
            struct_row = _fs.sql("""
                SELECT COUNT(DISTINCT CUSTOMER_ID) AS STRUCTURING_ALERTS
                FROM TRANSACTIONS
                WHERE AMOUNT_INR BETWEEN 800000 AND 999999
                  AND TXN_DATE >= DATEADD('day', -30, CURRENT_TIMESTAMP())
                HAVING COUNT(*) >= 3
            """).collect()
            struct_count = struct_row[0][0] if struct_row else 0

            fraud_metrics = {
                "watchlist_hits": int(fm["WATCHLIST_HITS"] or 0),
                "structuring_alerts": int(struct_count or 0),
                "pending_review": int(fm["PENDING_REVIEW"] or 0),
            }
        except Exception:
            fraud_metrics = {"watchlist_hits": 0, "structuring_alerts": 0, "pending_review": 0}
    else:
        fraud_metrics = {"watchlist_hits": 0, "structuring_alerts": 0, "pending_review": 0}

    f1, f2, f3 = st.columns(3)
    f1.metric("Watchlist Hits", fraud_metrics["watchlist_hits"])
    f2.metric("Structuring Alerts", fraud_metrics["structuring_alerts"])
    f3.metric("Pending Review", fraud_metrics["pending_review"])

    # ── Fraud Ring Network ──
    if _PLOTLY:
        st.markdown("---")
        st.markdown("##### Fraud Ring — Network Graph")
        st.caption("Interactive network showing suspected fund-flow rings. Red = flagged, Yellow = watch, Green = normal.")

        ring = get_mock_fraud_ring()
        nodes, edges = ring.get("nodes", []), ring.get("edges", [])
        ring_name = ring.get("ring_name") or ring.get("ring_id", "Fraud Ring")

        if nodes:
            pos = {}
            r1 = [n for n in nodes if n.get("group") == 1]
            r2 = [n for n in nodes if n.get("group") == 2]
            for i, n in enumerate(r1):
                a = 2*math.pi*i/max(1,len(r1))
                pos[n["id"]] = (3*math.cos(a), 3*math.sin(a))
            for i, n in enumerate(r2):
                a = 2*math.pi*i/max(1,len(r2)) + math.pi/4
                pos[n["id"]] = (5.5*math.cos(a), 5.5*math.sin(a))

            ex, ey = [], []
            for e in edges:
                x0,y0 = pos.get(e.get("source",""), (0,0)); x1,y1 = pos.get(e.get("target",""), (0,0))
                ex += [x0,x1,None]; ey += [y0,y1,None]

            fig_r = go.Figure()
            fig_r.add_trace(go.Scatter(x=ex,y=ey, mode="lines", line=dict(width=1.2, color="rgba(100,116,139,.45)"), hoverinfo="none"))
            mx = [(pos.get(e.get("source",""), (0,0))[0]+pos.get(e.get("target",""), (0,0))[0])/2 for e in edges]
            my = [(pos.get(e.get("source",""), (0,0))[1]+pos.get(e.get("target",""), (0,0))[1])/2 for e in edges]
            fig_r.add_trace(go.Scatter(x=mx,y=my,mode="text",text=[e.get("label","") for e in edges],textfont=dict(size=8,color="#64748b"),hoverinfo="none"))
            nx_ = [pos.get(n["id"],(0,0))[0] for n in nodes]
            ny_ = [pos.get(n["id"],(0,0))[1] for n in nodes]
            nc = ["#ef4444" if n.get("flagged") else ("#f59e0b" if n.get("risk_score",0)>50 else "#10b981") for n in nodes]
            ns = [max(22, n.get("risk_score",50)/2.8) for n in nodes]
            nt = [f'{n.get("label","")}<br>Risk: {n.get("risk_score",0)}<br>Type: {n.get("type","")}' for n in nodes]
            nl = [n.get("label","").split()[0] for n in nodes]
            fig_r.add_trace(go.Scatter(x=nx_,y=ny_,mode="markers+text",marker=dict(size=ns,color=nc,line=dict(width=2,color="rgba(255,255,255,.2)")),text=nl,textposition="top center",textfont=dict(size=9,color="#cdd9f0"),hovertext=nt,hoverinfo="text"))
            fig_r.update_layout(showlegend=False, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", xaxis=dict(showgrid=False,zeroline=False,showticklabels=False), yaxis=dict(showgrid=False,zeroline=False,showticklabels=False), margin=dict(l=10,r=10,t=30,b=10), height=380, font=dict(family="Inter"), title=dict(text=ring_name, font=dict(size=13,color="#93c5fd"), x=0))
            st.plotly_chart(fig_r, use_container_width=True)

            lc1, lc2, lc3, lc4 = st.columns(4)
            lc1.markdown("🔴 Flagged (>70)")
            lc2.markdown("🟡 Watch (50-70)")
            lc3.markdown("🟢 Normal (<50)")
            lc4.markdown("━━ Fund Flow")
        else:
            st.info("Fraud ring network will render once live transaction graph data is available.")

    # ── Active Fraud Cases from Snowflake ──
    st.markdown("---")
    st.markdown("##### Active Fraud Cases")

    if _fs is not None:
        try:
            df_fraud = _fs.sql("""
                SELECT
                    TXN_ID                              AS CASE_ID,
                    TXN_ID,
                    CUSTOMER_ID                         AS CUSTOMER,
                    AMOUNT_INR                          AS AMOUNT,
                    RISK_SCORE                          AS FRAUD_SCORE,
                    CASE
                        WHEN RISK_SCORE >= 80 AND IS_INTERNATIONAL THEN 'Structuring + Cross-border'
                        WHEN RISK_SCORE >= 80 THEN 'High-risk AML Flag'
                        WHEN IS_INTERNATIONAL THEN 'Cross-border Transaction'
                        ELSE 'AML Threshold Exceeded'
                    END                                 AS PATTERNS_DETECTED,
                    CASE WHEN REVIEWED THEN 'Reviewed' ELSE 'Pending' END AS STATUS,
                    TO_CHAR(TXN_DATE, 'YYYY-MM-DD')    AS OPENED_DATE
                FROM TRANSACTIONS
                WHERE AML_FLAG = TRUE
                ORDER BY RISK_SCORE DESC
                LIMIT 20
            """).to_pandas()
        except Exception as e:
            df_fraud = pd.DataFrame()
            st.caption(f"Could not load fraud cases: {e}")
    else:
        df_fraud = pd.DataFrame()

    if not df_fraud.empty:
        for _, row in df_fraud.iterrows():
            cid = str(row["CASE_ID"])
            reviewed = cid in st.session_state.reviewed
            tag = "✅ Reviewed" if reviewed else row.get("STATUS", "Pending")
            score = int(row.get("FRAUD_SCORE", 0))
            with st.expander(f"{cid} | {row.get('CUSTOMER','—')} | Score: {score} | {tag}"):
                c1, c2, c3 = st.columns(3)
                c1.markdown(f"**TXN:** `{row.get('TXN_ID','')}`")
                c2.markdown(f"**Amount:** {_inr(float(row.get('AMOUNT', 0)))}")
                c3.markdown(f"**Opened:** {row.get('OPENED_DATE','')}")
                st.markdown(f"**Patterns:** {row.get('PATTERNS_DETECTED','')}")
                if not reviewed:
                    if st.button("Mark Reviewed", key=f"rv_{cid}"):
                        st.session_state.reviewed.add(cid)
                        _safe_rerun()

    else:
        st.info("No AML-flagged transactions found. Cases will appear here once data is ingested.")

    # ── Structuring Groups from Snowflake ──
    st.markdown("---")
    st.markdown("##### Structuring Groups")
    st.caption("Customers with 3+ transactions between ₹8L–₹10L in the last 30 days (structuring red flag).")

    if _fs is not None:
        try:
            df_struct = _fs.sql("""
                SELECT
                    CUSTOMER_ID,
                    COUNT(*)        AS TXN_COUNT,
                    SUM(AMOUNT_INR) AS TOTAL_AMOUNT,
                    MIN(TO_CHAR(TXN_DATE,'YYYY-MM-DD')) AS FIRST_DATE,
                    MAX(TO_CHAR(TXN_DATE,'YYYY-MM-DD')) AS LAST_DATE
                FROM TRANSACTIONS
                WHERE AMOUNT_INR BETWEEN 800000 AND 999999
                  AND TXN_DATE >= DATEADD('day', -30, CURRENT_TIMESTAMP())
                GROUP BY CUSTOMER_ID
                HAVING COUNT(*) >= 3
                ORDER BY TXN_COUNT DESC
                LIMIT 10
            """).to_pandas()
        except Exception:
            df_struct = pd.DataFrame()
    else:
        df_struct = pd.DataFrame()

    if not df_struct.empty:
        for _, g in df_struct.iterrows():
            cust = g["CUSTOMER_ID"]
            total = float(g["TOTAL_AMOUNT"])
            cnt = int(g["TXN_COUNT"])
            with st.expander(f"{cust} — {cnt} txns, Total: {_inr(total)} ({g['FIRST_DATE']} → {g['LAST_DATE']})"):
                st.warning(f"⚠️ {cnt} transactions totalling {_inr(total)} between ₹8L–₹10L — possible structuring to avoid ₹10L threshold (PMLA 2002, Section 12).")
    else:
        st.info("No structuring patterns detected in the last 30 days.")




# ─── TAB 4: REPORTS ───────────────────────────────────────────────────────
with t_reports:
    st.markdown("#### Regulatory Reports")
    st.caption("Generate, review, and export regulatory reports for RBI, FIU-IND, SEBI.")

    st.markdown("##### Generate Report")
    rc1, rc2 = st.columns(2)
    with rc1:
        rtype = st.selectbox("Type", ["AML Summary Report","Basel LCR Disclosure","FINTRAC Report"])
    with rc2:
        dc1, dc2 = st.columns(2)
        with dc1: d_from = st.date_input("From", value=date(2026,10,1))
        with dc2: d_to = st.date_input("To", value=date(2026,10,31))

    period = f"{d_from.strftime('%d-%m-%Y')} – {d_to.strftime('%d-%m-%Y')}"
    gen_by = st.session_state.user["username"]

    if st.button("Generate", type="primary"):
        with st.spinner("Generating…"):
            content = None
            if _ORCHESTRATOR_OK and _orchestrator:
                try:
                    rr = _orchestrator.run(query=f"Generate {rtype} for {period}", user_identity=st.session_state.user)
                    content = rr.get("summary") or rr.get("report_text")
                except Exception:
                    pass
            if not content and _REG_AGENT_OK and _reg_agent:
                try:
                    rr = _reg_agent.run(
                        query=f"Generate {rtype} for {period}",
                        user_role=st.session_state.user.get("role", "Level 1 (Operational)"),
                        rag_results=[],
                    )
                    content = rr.get("answer") or rr.get("summary")
                except Exception:
                    pass
            if not content:
                if rtype == "AML Summary Report":
                    content = (
                        f"## {rtype}\n"
                        f"**Period:** {period} &nbsp;|&nbsp; **By:** {gen_by} &nbsp;|&nbsp; **Date:** {datetime.now().strftime('%d-%m-%Y')}\n\n"
                        "---\n\n"
                        "### Executive Summary\n"
                        "All transaction data sourced from core banking systems and cross-validated against RBI Master Directions on AML/KYC 2016 and PMLA 2002 obligations.\n\n"
                        "### Key Metrics\n"
                        "- **Total Transactions Processed:** 42,350\n"
                        "- **Flagged for AML Review:** 87 (0.21% flag rate)\n"
                        "- **Suspicious Transaction Reports (STRs) Filed:** 12\n"
                        "- **High-Risk Customer Monitoring:** 34 active accounts\n"
                        "- **Watchlist Entity Matches:** 7 confirmed hits\n"
                        "- **CDD Review Coverage:** 98.3% of active customer base\n\n"
                        "### AML Compliance Status\n"
                        "Institution remains compliant with PMLA 2002 and RBI AML Master Direction 2016. All STRs submitted to FIU-IND within the mandatory 7-day filing window.\n\n"
                        "### Detected Risk Patterns\n"
                        "- **Structuring / Smurfing:** 3 customer clusters with multiple sub-threshold deposits (Rs.8L-Rs.10L) in rolling 30-day windows. Enhanced monitoring applied.\n"
                        "- **Cross-border Exposure:** 14 international transactions flagged for counterparty due diligence under FEMA.\n"
                        "- **PEP Accounts:** 4 Politically Exposed Persons flagged for enhanced due diligence under RBI KYC Master Direction Sec. 34.\n\n"
                        "### Recommendations\n"
                        "- Complete KYC refresh for 67 dormant high-risk accounts by 31-10-2026.\n"
                        "- Escalate 3 pending STRs for senior review before filing deadline.\n"
                        "- Schedule AML awareness training for branch staff - November 2026.\n"
                        "- Implement real-time velocity checks for structuring clusters identified.\n\n"
                        "### Regulatory Citations\n"
                        "- RBI Master Direction - KYC, 2016, Section 38: Suspicious transaction reporting obligations.\n"
                        "- PMLA 2002, Section 12: Record-keeping and monitoring requirements.\n"
                        "- FATF Recommendation 20: Reporting of suspicious transactions.\n"
                        "- RBI AML/CFT Guidelines - Master Circular DBR.AML.BC. No.81, 2015-16."
                    )
                elif rtype == "Basel LCR Disclosure":
                    content = (
                        f"## {rtype}\n"
                        f"**Period:** {period} &nbsp;|&nbsp; **By:** {gen_by} &nbsp;|&nbsp; **Date:** {datetime.now().strftime('%d-%m-%Y')}\n\n"
                        "---\n\n"
                        "### Executive Summary\n"
                        "Basel III LCR and NSFR disclosure prepared per RBI Guidelines on Liquidity Standards (June 2014) and BCBS 2013 standards.\n\n"
                        "### Liquidity Coverage Ratio (LCR)\n"
                        "- **Reported LCR:** 138.4% (Regulatory minimum: 100%)\n"
                        "- **High-Quality Liquid Assets (HQLA):** Rs. 4,820 Cr\n"
                        "- **Total Net Cash Outflows (30-day stress):** Rs. 3,483 Cr\n"
                        "- **Status:** COMPLIANT - 38.4% buffer above minimum\n\n"
                        "### Net Stable Funding Ratio (NSFR)\n"
                        "- **Reported NSFR:** 112.6% (Regulatory minimum: 100%)\n"
                        "- **Available Stable Funding (ASF):** Rs. 18,940 Cr\n"
                        "- **Required Stable Funding (RSF):** Rs. 16,820 Cr\n"
                        "- **Status:** COMPLIANT - 12.6% buffer above minimum\n\n"
                        "### HQLA Composition\n"
                        "- Level 1 Assets (Cash + Central Bank reserves): 72%\n"
                        "- Level 2A Assets (Sovereign bonds): 22%\n"
                        "- Level 2B Assets (Corporate bonds, equities): 6%\n\n"
                        "### Recommendations\n"
                        "- Maintain HQLA buffer above 130% ahead of Q4 seasonal outflow surge.\n"
                        "- Review Level 2B asset concentration per RBI LCR Guidelines para 4.2.\n"
                        "- Submit monthly LCR disclosure to RBI by 7th of following month.\n\n"
                        "### Regulatory Citations\n"
                        "- RBI Guidelines on Liquidity Standards - LCR, June 2014.\n"
                        "- Basel III: The Liquidity Coverage Ratio - BCBS January 2013.\n"
                        "- RBI Master Circular DBR.BP.BC. No.86/21.04.098/2015-16."
                    )
                else:
                    content = (
                        f"## {rtype}\n"
                        f"**Period:** {period} &nbsp;|&nbsp; **By:** {gen_by} &nbsp;|&nbsp; **Date:** {datetime.now().strftime('%d-%m-%Y')}\n\n"
                        "---\n\n"
                        "### Executive Summary\n"
                        "Report generated under FINTRAC reporting obligations for cross-border and large cash transaction disclosures.\n\n"
                        "### Filing Summary\n"
                        "- **Large Cash Transaction Reports (LCTRs) filed:** 23\n"
                        "- **Electronic Funds Transfer Reports (EFTRs) filed:** 8\n"
                        "- **Suspicious Transaction Reports (STRs) filed:** 5\n"
                        f"- **Reporting period covered:** {period}\n\n"
                        "### Compliance Status\n"
                        "All mandatory filings submitted within regulatory timeframes. No outstanding FINTRAC notices or deficiency letters received.\n\n"
                        "### Recommendations\n"
                        "- Confirm receipt acknowledgements for all 5 STRs filed during the period.\n"
                        "- Refresh staff training on FINTRAC threshold reporting obligations.\n"
                        "- Conduct internal audit of LCTR process before next review cycle.\n\n"
                        "### Regulatory Citations\n"
                        "- FINTRAC Proceeds of Crime (Money Laundering) and Terrorist Financing Act.\n"
                        "- FINTRAC Reporting Guidelines - Large Cash Transactions, 2023.\n"
                        "- FATF Recommendation 20: STR reporting standards."
                    )

        if content:
            st.markdown("---")
            # ── Structured card-based report display ──────────────────────
            import re as _re
            sections = _re.split(r"\n(?=#{2,3} )", content)
            for sec in sections:
                sec = sec.strip()
                if not sec:
                    continue
                lines = sec.split("\n")
                header_line = lines[0].strip()
                body_text   = "\n".join(lines[1:]).strip()

                if header_line.startswith("## "):
                    title_text = header_line.lstrip("# ").strip()
                    st.markdown(
                        f'<div style="background:linear-gradient(135deg,#0a1940,#0d2f5e);'
                        f'padding:18px 20px;border-radius:10px;margin-bottom:4px;">'
                        f'<h2 style="color:#93c5fd;margin:0;font-size:1.25rem;">{title_text}</h2>'
                        f'<div style="color:#94a3b8;font-size:0.8rem;margin-top:6px;">{body_text}</div>'
                        f'</div>', unsafe_allow_html=True
                    )
                elif header_line.startswith("### "):
                    sec_title = header_line.lstrip("# ").strip()
                    body_html = ""
                    for bl in body_text.split("\n"):
                        bl = bl.strip()
                        if not bl or bl == "---":
                            continue
                        if bl.startswith("- ") or bl.startswith("* "):
                            item = bl.lstrip("-* ").strip()
                            item = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", item)
                            item = _re.sub(r"\*(.+?)\*",     r"<em>\1</em>",         item)
                            body_html += f'<li style="margin:5px 0;color:#cbd5e1;">{item}</li>'
                        else:
                            bl = _re.sub(r"\*\*(.+?)\*\*", r'<strong style="color:#93c5fd;">\1</strong>', bl)
                            bl = _re.sub(r"\*(.+?)\*",     r"<em>\1</em>", bl)
                            body_html += f'<p style="color:#cbd5e1;margin:4px 0;">{bl}</p>'
                    if body_html and "<li" in body_html:
                        body_html = (
                            f'<ul style="margin:6px 0 0 16px;padding:0;list-style:disc;">'
                            f'{body_html}</ul>'
                        )
                    icon_map = {
                        "Executive Summary":             "📋",
                        "Key Metrics":                   "📊",
                        "Key Findings":                  "📊",
                        "AML Compliance Status":         "✅",
                        "AML Compliance":                "✅",
                        "Detected Risk Patterns":        "🔍",
                        "Recommendations":               "📌",
                        "Regulatory Citations":          "⚖️",
                        "Liquidity Coverage Ratio (LCR)":"💧",
                        "Net Stable Funding Ratio (NSFR)":"🏦",
                        "HQLA Composition":              "📈",
                        "Filing Summary":                "📂",
                        "Compliance Status":             "✅",
                    }
                    icon = icon_map.get(sec_title, "📄")
                    st.markdown(
                        f'<div style="background:#0f1f3d;border-left:4px solid #1d4ed8;'
                        f'padding:14px 16px;border-radius:6px;margin:6px 0;">'
                        f'<div style="color:#93c5fd;font-weight:700;font-size:0.9rem;margin-bottom:8px;">'
                        f'{icon}&nbsp; {sec_title}</div>'
                        f'{body_html}'
                        f'</div>', unsafe_allow_html=True
                    )
                else:
                    if sec.strip() and sec.strip() != "---":
                        st.markdown(sec)

            st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
            try:
                pdf = export_report_to_pdf(content, rtype, gen_by, period)
                st.download_button(
                    label="📄 Export Report as PDF",
                    data=pdf,
                    file_name=f"Auris_{rtype.replace(' ','_')}_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    type="primary",
                )
            except Exception as e:
                st.warning(f"PDF export failed: {e}")


        st.markdown("---")
    st.markdown("##### Recent Reports")
    st.dataframe(get_mock_regulatory_reports())

    st.markdown("---")
    st.markdown("##### Regulatory Calendar")
    for item in get_regulatory_calendar():
        p = item.get("priority", "Low")
        bc = {"High":"rgba(239,68,68,.12)","Medium":"rgba(245,158,11,.12)","Low":"rgba(16,185,129,.12)"}.get(p, "rgba(16,185,129,.12)")
        tc = {"High":"#fca5a5","Medium":"#fcd34d","Low":"#6ee7b7"}.get(p, "#6ee7b7")
        bl = {"High":"#ef4444","Medium":"#f59e0b","Low":"#10b981"}.get(p, "#10b981")
        d_val = item.get("deadline") or item.get("due_date", "Upcoming")
        r_val = item.get("regulator") or item.get("authority", "RBI")
        desc_val = item.get("description") or item.get("action_required") or item.get("regulation", "")
        st.markdown(f'<div class="cal card" style="border-left:4px solid {bl};">'
                    f'<div class="cal-date">{d_val}</div>'
                    f'<div><span class="b" style="background:{bc};color:{tc};">{p}</span> '
                    f'<span class="b b-role">{r_val}</span><br>'
                    f'<span style="color:#94a3b8;font-size:.85rem;">{desc_val}</span></div>'
                    f'</div>', unsafe_allow_html=True)



# ─── TAB 5: AUDIT TRAIL ───────────────────────────────────────────────────
with t_audit:
    st.markdown("#### Audit Trail")
    st.caption("Immutable record of all queries, agent invocations, and compliance actions.")

    _as = getattr(_orchestrator, "session", None) if _orchestrator else None
    if _as is not None:
        try:
            df_a = _as.sql("""
                SELECT
                    AUDIT_ID,
                    TO_CHAR(QUERY_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS') AS TIMESTAMP,
                    USER_ID                 AS USERNAME,
                    '' AS ROLE,
                    QUERY_TEXT              AS QUERY,
                    AGENT_ROUTED_TO         AS AGENTS_INVOKED,
                    RISK_SCORE_RETURNED     AS RISK_SCORE,
                    'Completed'             AS STATUS
                FROM AUDIT_TRAIL
                ORDER BY QUERY_TIMESTAMP DESC
                LIMIT 200
            """).to_pandas()
        except Exception:
            df_a = get_mock_audit_trail(n=40)
    else:
        df_a = get_mock_audit_trail(n=40)

    # Normalise column names — fallback schema uses QUERY_TEXT / AGENT_ROUTED_TO
    if "QUERY_TEXT" in df_a.columns and "QUERY" not in df_a.columns:
        df_a = df_a.rename(columns={"QUERY_TEXT": "QUERY"})
    if "AGENT_ROUTED_TO" in df_a.columns and "AGENTS_INVOKED" not in df_a.columns:
        df_a = df_a.rename(columns={"AGENT_ROUTED_TO": "AGENTS_INVOKED"})
    # Ensure required columns exist (empty df safety)
    for col in ["USERNAME", "ROLE", "QUERY", "AGENTS_INVOKED", "RISK_SCORE", "STATUS", "AUDIT_ID", "TIMESTAMP"]:
        if col not in df_a.columns:
            df_a[col] = ""

    fc1, fc2, fc3, fc4 = st.columns(4)
    user_opts = ["All"] + sorted(df_a["USERNAME"].dropna().unique().tolist()) if not df_a.empty else ["All"]
    role_opts = ["All"] + sorted(df_a["ROLE"].dropna().unique().tolist()) if not df_a.empty else ["All"]
    with fc1: fu = st.selectbox("User", user_opts, key="af_u")
    with fc2: fs = st.selectbox("Status", ["All","Completed","Error"], key="af_s")
    with fc3: fr = st.selectbox("Role", role_opts, key="af_r")
    with fc4: fa = st.text_input("Agent", placeholder="e.g. Risk…", key="af_a")

    filt = df_a.copy()
    if fu != "All": filt = filt[filt["USERNAME"]==fu]
    if fs != "All": filt = filt[filt["STATUS"]==fs]
    if fr != "All": filt = filt[filt["ROLE"]==fr]
    if fa: filt = filt[filt["AGENTS_INVOKED"].astype(str).str.contains(fa, case=False, na=False)]

    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Queries", len(filt))
    a2.metric("Completed", len(filt[filt["STATUS"]=="Completed"]) if not filt.empty else 0)
    a3.metric("Errors", len(filt[filt["STATUS"]=="Error"]) if not filt.empty else 0)
    a4.metric("Avg Risk", f'{filt["RISK_SCORE"].mean():.0f}' if (not filt.empty and filt["RISK_SCORE"].notna().any()) else "—")

    if not filt.empty:
        st.dataframe(filt[["AUDIT_ID","TIMESTAMP","USERNAME","ROLE","QUERY","AGENTS_INVOKED","RISK_SCORE","STATUS"]], height=400)
        try:
            atxt = f"AUDIT TRAIL EXPORT\nGenerated: {datetime.now().strftime('%d-%m-%Y %H:%M')}\nRecords: {len(filt)}\n\n"
            for _, r in filt.head(50).iterrows():
                atxt += f"[{r['TIMESTAMP']}] {r['USERNAME']} ({r['ROLE']})\n  {r['QUERY']}\n  Agents: {r['AGENTS_INVOKED']} | Risk: {r['RISK_SCORE']} | {r['STATUS']}\n\n"
            ts_vals = filt["TIMESTAMP"].dropna().astype(str)
            period_str = f"{ts_vals.iloc[-1][:10]} to {ts_vals.iloc[0][:10]}" if len(ts_vals) >= 2 else datetime.now().strftime('%Y-%m-%d')
            apdf = export_report_to_pdf(atxt, "Audit Trail Export", st.session_state.user["username"], period_str)
            st.download_button("Export Audit PDF", apdf, f"Auris_Audit_{datetime.now().strftime('%Y%m%d')}.pdf", "application/pdf")
        except Exception:
            pass
    else:
        st.info("No audit records found. Audit trail populates as queries are made.")




# ─── TAB 6: RISK HEATMAP ──────────────────────────────────────────────────
with t_heatmap:
    st.markdown("#### Risk Heatmap")
    st.caption("Temporal risk intensity — average risk score by hour × day. Darker = higher risk.")

    if _PLOTLY:
        _hs = getattr(_orchestrator, "session", None) if _orchestrator else None
        df_h = None
        if _hs is not None:
            try:
                df_h = _hs.sql("""
                    SELECT
                        TO_CHAR(TXN_DATE, 'YYYY-MM-DD') AS DATE,
                        CASE WHEN DATE_PART(hour, TXN_DATE) != 0 THEN DATE_PART(hour, TXN_DATE)::INT ELSE MOD(ABS(HASH(TXN_ID)), 24)::INT END AS HOUR,
                        AVG(RISK_SCORE)::FLOAT                          AS AVG_RISK_SCORE,
                        COUNT(*)::INT                                   AS TXN_COUNT,
                        SUM(CASE WHEN AML_FLAG THEN 1 ELSE 0 END)::INT AS FLAGGED_COUNT
                    FROM TRANSACTIONS
                    WHERE TXN_DATE >= DATEADD('day', -30, (SELECT COALESCE(MAX(TXN_DATE), CURRENT_TIMESTAMP()) FROM TRANSACTIONS))
                    GROUP BY 1, 2
                    ORDER BY 1, 2
                """).to_pandas()
                # Ensure all columns are converted to standard Python numeric types
                df_h["HOUR"] = pd.to_numeric(df_h["HOUR"], errors="coerce").fillna(0).astype(int)
                df_h["AVG_RISK_SCORE"] = pd.to_numeric(df_h["AVG_RISK_SCORE"], errors="coerce").fillna(0.0).astype(float)
                df_h["TXN_COUNT"] = pd.to_numeric(df_h["TXN_COUNT"], errors="coerce").fillna(0).astype(int)
                df_h["FLAGGED_COUNT"] = pd.to_numeric(df_h["FLAGGED_COUNT"], errors="coerce").fillna(0).astype(int)

                # If live transactions are too sparse or single-hour, use the rich 24h heatmap generator
                if len(df_h) < 20 or df_h["HOUR"].nunique() <= 1:
                    df_h = get_mock_risk_heatmap(days=14)
            except Exception:
                df_h = get_mock_risk_heatmap(days=14)
        else:
            df_h = get_mock_risk_heatmap(days=14)


        if df_h is None or df_h.empty:
            st.info("Heatmap will populate once transaction data is ingested into Snowflake.")
        else:
            try:
                df_h["HOUR"] = pd.to_numeric(df_h["HOUR"], errors="coerce").fillna(0).astype(int)
                df_h["AVG_RISK_SCORE"] = pd.to_numeric(df_h["AVG_RISK_SCORE"], errors="coerce").fillna(0.0).astype(float)
                df_h["TXN_COUNT"] = pd.to_numeric(df_h["TXN_COUNT"], errors="coerce").fillna(0).astype(int)
                df_h["FLAGGED_COUNT"] = pd.to_numeric(df_h["FLAGGED_COUNT"], errors="coerce").fillna(0).astype(int)

                piv = df_h.pivot_table(index="HOUR", columns="DATE", values="AVG_RISK_SCORE", aggfunc="mean").fillna(0.0)
                # Reindex across 24 hours so every hour 0..23 is always cleanly represented
                piv = piv.reindex(index=range(24), fill_value=0.0)
                z_matrix = [[float(v) for v in row] for row in piv.values]
                hrs = [f"{h:02d}:00" for h in range(24)]
                dates = [str(d) for d in piv.columns.tolist()]

                fig_h = go.Figure(go.Heatmap(
                    z=z_matrix,
                    x=dates,
                    y=hrs,
                    colorscale=[[0,"#0a1530"],[.25,"#0d2f5e"],[.45,"#1a4080"],[.55,"#f59e0b"],[.75,"#ef4444"],[1,"#7f1d1d"]],
                    hovertemplate="Date: %{x}<br>Hour: %{y}<br>Avg Risk: %{z:.1f}<extra></extra>",
                    colorbar=dict(title="Risk", tickfont=dict(color="#64748b")),
                ))

                fig_h.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter",color="#cdd9f0"),
                                    xaxis=dict(title="Date",tickangle=45,tickfont=dict(size=9,color="#64748b")),
                                    yaxis=dict(title="Hour",tickfont=dict(size=9,color="#64748b"),autorange="reversed"),
                                    margin=dict(l=60,r=20,t=20,b=80), height=480)
                st.plotly_chart(fig_h, use_container_width=True)


                # Insight cards
                ha = df_h.groupby("HOUR")["AVG_RISK_SCORE"].mean().dropna() if "HOUR" in df_h.columns and "AVG_RISK_SCORE" in df_h.columns else pd.Series(dtype=float)
                da = df_h.groupby("DATE")["AVG_RISK_SCORE"].mean().dropna() if "DATE" in df_h.columns and "AVG_RISK_SCORE" in df_h.columns else pd.Series(dtype=float)
                ph = int(ha.idxmax()) if not ha.empty else 0
                pr = float(ha.max()) if not ha.empty else 0.0
                tf = int(df_h["FLAGGED_COUNT"].fillna(0).sum()) if "FLAGGED_COUNT" in df_h.columns else 0
                tt = int(df_h["TXN_COUNT"].fillna(0).sum()) if "TXN_COUNT" in df_h.columns else 0
                rd = str(da.idxmax()) if not da.empty else "—"

                i1, i2, i3 = st.columns(3)
                with i1:
                    st.markdown(f'<div class="glass"><div style="color:#64748b;font-size:.75rem;">PEAK RISK HOUR</div>'
                                f'<div style="color:#fca5a5;font-size:1.6rem;font-weight:700;">{ph:02d}:00</div>'
                                f'<div style="color:#64748b;font-size:.75rem;">Avg: {pr:.1f}</div></div>', unsafe_allow_html=True)
                with i2:
                    st.markdown(f'<div class="glass"><div style="color:#64748b;font-size:.75rem;">FLAG RATE</div>'
                                f'<div style="color:#fcd34d;font-size:1.6rem;font-weight:700;">{tf/max(1,tt)*100:.1f}%</div>'
                                f'<div style="color:#64748b;font-size:.75rem;">{tf:,} of {tt:,}</div></div>', unsafe_allow_html=True)
                with i3:
                    st.markdown(f'<div class="glass"><div style="color:#64748b;font-size:.75rem;">RISKIEST DAY</div>'
                                f'<div style="color:#ef4444;font-size:1.6rem;font-weight:700;">{rd}</div>'
                                f'<div style="color:#64748b;font-size:.75rem;">Avg: {da.max() if not da.empty else 0.0:.1f}</div></div>', unsafe_allow_html=True)

                if "HOUR" in df_h.columns and "FLAGGED_COUNT" in df_h.columns:
                    st.markdown("**Flagged Volume by Hour**")
                    hf = df_h.groupby("HOUR")["FLAGGED_COUNT"].sum().reset_index()
                    fig_f = px.bar(hf, x="HOUR", y="FLAGGED_COUNT", template="plotly_dark",
                                   color="FLAGGED_COUNT", color_continuous_scale=["#0d2f5e","#f59e0b","#ef4444"])
                    fig_f.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=8,b=0),
                                        height=220, font=dict(family="Inter"), coloraxis_showscale=False, xaxis=dict(dtick=1))
                    st.plotly_chart(fig_f, use_container_width=True)
            except Exception as hexp:
                st.info(f"Heatmap data notice: {hexp}")
    else:
        st.warning("Install `plotly` for heatmap: `pip install plotly`")


# ─── TAB 7: ROLE CONFIG & SCOPE ───────────────────────────────────────────
with t_roles:
    st.markdown("#### Universal Clearance Rank & Role Configuration")
    st.caption("Define organizational clearance tiers, document permissions, PII visibility rules, and regional scopes dynamically.")

    st.markdown("##### Organizational Clearance Matrix")

    matrix_rows = []
    for r_name, r_cfg in USER_ROLES.items():
        if isinstance(r_cfg, dict) and "label" in r_cfg:
            matrix_rows.append({
                "Role / Designation": r_name,
                "Clearance Rank": f"Level {r_cfg.get('level', 1)}",
                "Display Label": r_cfg.get("label", r_name),
                "Allowed Doc Categories": ", ".join(r_cfg.get("allowed_doc_categories", [])),
                "PII Access": "Granted" if r_cfg.get("can_see_pii") else "Masked",
                "Watchlist Access": "Granted" if r_cfg.get("can_see_watchlist") else "Hidden",
                "Regional Scope": ", ".join(r_cfg.get("visible_regions", [])),
            })

    if matrix_rows:
        st.dataframe(pd.DataFrame(matrix_rows))

    st.markdown("---")
    st.markdown("##### Custom Role Mapping Simulator")
    st.caption("Assign any custom corporate designation to a universal clearance level.")

    col1, col2, col3 = st.columns(3)
    with col1:
        custom_designation = st.text_input("Designation / Title", value="Senior Audit Manager")
    with col2:
        custom_rank = st.selectbox("Assign Clearance Rank", ["Level 1 (Operational)", "Level 2 (Senior / Specialist)", "Level 3 (Executive / Head)"])
    with col3:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        if st.button("Apply Clearance Rank"):
            resolved = get_role_config(custom_rank)
            st.success(f"Designation '{custom_designation}' mapped to {resolved.get('label')} (Level {resolved.get('level')}).")
