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
    ENV = "local"
    CORTEX_MODEL = "mistral-large"
    USER_ROLES = {}
    def get_role_config(r):
        return {"level": 1, "label": r, "allowed_doc_categories": ["public_policy"], "can_see_pii": False, "visible_regions": ["West"]}

# ---------------------------------------------------------------------------
# Orchestrator (optional)
# ---------------------------------------------------------------------------
try:
    from src.orchestrator.orchestrator import AurisOrchestrator
    _orchestrator = AurisOrchestrator()
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
from mock_data import (
    get_mock_fraud_cases, get_mock_metrics, get_mock_regulatory_reports,
    get_mock_risk_timeseries, get_mock_structuring_groups,
    get_mock_transactions, get_regulatory_calendar,
    get_mock_risk_heatmap, get_mock_fraud_ring, get_mock_audit_trail,
    get_role_data_scope, filter_transactions_by_role,
)
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
    for k, v in {"user": _USERS[0], "chat": [], "sid": str(uuid.uuid4())[:8].upper(), "reviewed": set(), "aq": ""}.items():
        if k not in st.session_state:
            st.session_state[k] = v
_init()


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
    """Run orchestrator or mock."""
    u = st.session_state.user
    if _ORCHESTRATOR_OK and _orchestrator:
        return _orchestrator.run(query=q, user_identity=u, rag_results=None)
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
    if ENV == "local":
        st.markdown("**Local Mock Mode**")
        st.caption("Snowflake not connected")
    else:
        st.markdown("**Snowflake Connected**")
    st.caption(f"Model: `{CORTEX_MODEL}`")
    st.divider()

    # Quick actions
    st.markdown("##### Quick Actions")
    if st.button("AML Summary Report", use_container_width=True):
        st.session_state.aq = "Generate AML summary for October 2026"
        st.rerun()
    if st.button("Liquidity Check (LCR)", use_container_width=True):
        st.session_state.aq = "What is our current LCR status?"
        st.rerun()
    if st.button("Structuring Scan", use_container_width=True):
        st.session_state.aq = "Check for structuring patterns in recent NEFT transfers"
        st.rerun()


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
    if ENV == "local":
        st.markdown('<div style="text-align:right;padding-top:4px;"><span class="b b-md">LOCAL MODE</span></div>', unsafe_allow_html=True)


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
    st.caption("Ask anything about risk, fraud, or regulations. Auris invokes the relevant agents and synthesises a response.")

    # Chips
    chips = [
        "Flag transactions over ₹10L (7 days)",
        "What is our current LCR?",
        "KYC for high-risk customers",
        "Generate AML summary",
        "Check structuring patterns",
    ]
    chip_cols = st.columns(len(chips))
    clicked_chip = ""
    for col, chip in zip(chip_cols, chips):
        with col:
            if st.button(chip, key=f"c_{hash(chip)}"):
                clicked_chip = chip

    prefill = clicked_chip or st.session_state.pop("aq", "")
    query = st.text_area("Query", value=prefill, placeholder="Ask Auris anything…", height=100, label_visibility="collapsed")

    if st.button("Analyze", type="primary"):
        if query.strip():
            with st.spinner("Analyzing — invoking agents…"):
                res = _run_query(query.strip())

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
                    st.markdown(f"**Risk:** {_rb(score)}", unsafe_allow_html=True)
                with h2:
                    pills = " ".join(f'<span class="b b-agent">{a.replace("Agent","")}</span>' for a in agents)
                    st.markdown(f"**Agents:** {pills}", unsafe_allow_html=True)

                st.markdown(f'<div class="summary-card">{summary}</div>', unsafe_allow_html=True)

                if recs:
                    with st.expander("Recommendations", expanded=True):
                        for r in recs:
                            st.markdown(f"• {r}")

                if citations:
                    with st.expander("Source Citations"):
                        for c in citations:
                            st.markdown(f'<div class="citation"><b>{c.get("doc_name","")}</b> — {c.get("section","")}<br>{c.get("snippet","")}</div>', unsafe_allow_html=True)

                if flagged:
                    with st.expander(f"Flagged Items ({len(flagged)})"):
                        st.dataframe(pd.DataFrame(flagged), hide_index=True)

                st.session_state.chat.append({"q": query.strip(), "s": score, "t": datetime.now().strftime("%H:%M"), "a": agents})

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
            fig = px.bar(df_ts, x="DATE", y="TRANSACTION_COUNT", color="RISK_LEVEL", barmode="group",
                         color_discrete_map={"Low":"#10b981","Medium":"#f59e0b","High":"#ef4444"}, template="plotly_dark")
            fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=8,b=0), height=280, font=dict(family="Inter"), legend_title_text="")
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            st.markdown("**Amount vs Risk Score**")
            if not df_txn.empty:
                fig2 = px.scatter(df_txn, x="AMOUNT", y="RISK_SCORE", color="AML_FLAG",
                                  color_discrete_map={True:"#ef4444",False:"#10b981"},
                                  hover_data=["TXN_ID","CUSTOMER_NAME"], template="plotly_dark")
                fig2.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=8,b=0), height=280, font=dict(family="Inter"))
                st.plotly_chart(fig2, use_container_width=True)

    st.markdown("**High-Risk Transactions**")
    if not df_txn.empty:
        hr = df_txn[df_txn["RISK_LEVEL"]=="High"].head(10).copy()
        hr["AMOUNT"] = hr["AMOUNT"].apply(_inr)
        st.dataframe(hr[["TXN_ID","CUSTOMER_NAME","AMOUNT","RISK_SCORE","AML_FLAG","DATE"]], hide_index=True)
    else:
        st.info("No data.")


# ─── TAB 3: FRAUD & RINGS ─────────────────────────────────────────────────
with t_fraud:
    st.markdown("#### Fraud Cases & Ring Visualization")

    metrics_f = get_mock_metrics()
    f1, f2, f3 = st.columns(3)
    f1.metric("Watchlist Hits", metrics_f.get("watchlist_hits",0))
    f2.metric("Structuring Alerts", metrics_f.get("structuring_alerts",0))
    f3.metric("Pending Review", metrics_f.get("pending_review",0))

    # ── Fraud Ring Network ──
    if _PLOTLY:
        st.markdown("---")
        st.markdown("##### Fraud Ring — Network Graph")
        st.caption("Interactive network showing suspected fund-flow rings. Red = flagged, Yellow = watch, Green = normal.")

        ring = get_mock_fraud_ring()
        nodes, edges = ring["nodes"], ring["edges"]

        pos = {}
        r1 = [n for n in nodes if n["group"]==1]
        r2 = [n for n in nodes if n["group"]==2]
        for i, n in enumerate(r1):
            a = 2*math.pi*i/max(1,len(r1))
            pos[n["id"]] = (3*math.cos(a), 3*math.sin(a))
        for i, n in enumerate(r2):
            a = 2*math.pi*i/max(1,len(r2)) + math.pi/4
            pos[n["id"]] = (5.5*math.cos(a), 5.5*math.sin(a))

        ex, ey = [], []
        for e in edges:
            x0,y0 = pos.get(e["source"],(0,0)); x1,y1 = pos.get(e["target"],(0,0))
            ex += [x0,x1,None]; ey += [y0,y1,None]

        fig_r = go.Figure()
        # edges
        fig_r.add_trace(go.Scatter(x=ex,y=ey, mode="lines", line=dict(width=1.2, color="rgba(100,116,139,.45)"), hoverinfo="none"))
        # edge labels
        mx = [(pos.get(e["source"],(0,0))[0]+pos.get(e["target"],(0,0))[0])/2 for e in edges]
        my = [(pos.get(e["source"],(0,0))[1]+pos.get(e["target"],(0,0))[1])/2 for e in edges]
        fig_r.add_trace(go.Scatter(x=mx,y=my,mode="text",text=[e["label"] for e in edges],textfont=dict(size=8,color="#64748b"),hoverinfo="none"))
        # nodes
        nx_ = [pos.get(n["id"],(0,0))[0] for n in nodes]
        ny_ = [pos.get(n["id"],(0,0))[1] for n in nodes]
        nc = ["#ef4444" if n["flagged"] else ("#f59e0b" if n["risk_score"]>50 else "#10b981") for n in nodes]
        ns = [max(22,n["risk_score"]/2.8) for n in nodes]
        nt = [f'{n["label"]}<br>Risk: {n["risk_score"]}<br>Type: {n["type"]}' for n in nodes]
        nl = [n["label"].split()[0] for n in nodes]
        fig_r.add_trace(go.Scatter(x=nx_,y=ny_,mode="markers+text",marker=dict(size=ns,color=nc,line=dict(width=2,color="rgba(255,255,255,.2)")),text=nl,textposition="top center",textfont=dict(size=9,color="#cdd9f0"),hovertext=nt,hoverinfo="text"))
        fig_r.update_layout(showlegend=False, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", xaxis=dict(showgrid=False,zeroline=False,showticklabels=False), yaxis=dict(showgrid=False,zeroline=False,showticklabels=False), margin=dict(l=10,r=10,t=30,b=10), height=380, font=dict(family="Inter"), title=dict(text=f"{ring['ring_name']}", font=dict(size=13,color="#93c5fd"), x=0))
        st.plotly_chart(fig_r, use_container_width=True)

        lc1, lc2, lc3, lc4 = st.columns(4)
        lc1.markdown("Flagged (>70)")
        lc2.markdown("Watch (50-70)")
        lc3.markdown("Normal (<50)")
        lc4.markdown("━━ Fund Flow")

    # ── Fraud Cases ──
    st.markdown("---")
    st.markdown("##### Active Fraud Cases")
    df_fraud = get_mock_fraud_cases(n=8)
    if not df_fraud.empty:
        for _, row in df_fraud.iterrows():
            cid = row["CASE_ID"]
            reviewed = cid in st.session_state.reviewed
            tag = "Reviewed" if reviewed else row["STATUS"]
            with st.expander(f"{cid} | {row['CUSTOMER']} | Score: {row['FRAUD_SCORE']} | {tag}"):
                c1, c2, c3 = st.columns(3)
                c1.markdown(f"**TXN:** `{row['TXN_ID']}`")
                c2.markdown(f"**Amount:** {_inr(row['AMOUNT'])}")
                c3.markdown(f"**Opened:** {row['OPENED_DATE']}")
                st.markdown(f"**Patterns:** {row['PATTERNS_DETECTED']}")
                if not reviewed:
                    if st.button("Mark Reviewed", key=f"rv_{cid}"):
                        st.session_state.reviewed.add(cid)
                        st.rerun()

    # ── Structuring ──
    st.markdown("---")
    st.markdown("##### Structuring Groups")
    for g in get_mock_structuring_groups():
        with st.expander(f"{g['customer']} — {g['transaction_count']} txns, Total: {_inr(g['total_amount'])}"):
            st.dataframe(pd.DataFrame(g["transactions"]), hide_index=True)
            st.warning(f"{g['transaction_count']} txns totalling {_inr(g['total_amount'])} — possible structuring to avoid ₹10L threshold.")


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
            if _REG_AGENT_OK and _reg_agent:
                rr = _reg_agent.run(query=f"Generate {rtype} for {period}", user_identity=st.session_state.user)
                content = rr.get("report_text") or rr.get("summary","")
            else:
                content = f"""## {rtype}\n**Period:** {period} &nbsp;|&nbsp; **By:** {gen_by} &nbsp;|&nbsp; **Date:** {datetime.now().strftime('%d-%m-%Y')}\n\n---\n\n### Executive Summary\nAll data sourced from core banking and validated against RBI Master Directions.\n\n### Key Findings\n- Transactions processed: **42,350**\n- Flagged for AML: **87** (0.21%)\n- STRs filed: **12**\n- High-risk monitoring: **34** customers\n- Watchlist matches: **7**\n\n### AML Compliance\nInstitution remains compliant with PMLA 2002. All STRs filed within 7-day window. CDD reviews current for 98.3% of customer base.\n\n### Recommendations\n1. Complete KYC refresh for 67 dormant high-risk accounts by 31-10-2026.\n2. Review 3 pending STRs before filing deadline.\n3. Staff AML training refresh — Nov 2026."""

        if content:
            st.markdown("---")
            st.markdown(content)
            try:
                pdf = export_report_to_pdf(content, rtype, gen_by, period)
                st.download_button("Export PDF", pdf, f"Auris_{rtype.replace(' ','_')}.pdf", "application/pdf")
            except Exception as e:
                st.caption(f"PDF export needs `fpdf2`: {e}")

    st.markdown("---")
    st.markdown("##### Recent Reports")
    st.dataframe(get_mock_regulatory_reports(), hide_index=True)

    st.markdown("---")
    st.markdown("##### Regulatory Calendar")
    for item in get_regulatory_calendar():
        p = item.get("priority","Low")
        bc = {"High":"rgba(239,68,68,.12)","Medium":"rgba(245,158,11,.12)","Low":"rgba(16,185,129,.12)"}.get(p,"")
        tc = {"High":"#fca5a5","Medium":"#fcd34d","Low":"#6ee7b7"}.get(p,"#6ee7b7")
        bl = {"High":"#ef4444","Medium":"#f59e0b","Low":"#10b981"}.get(p,"#10b981")
        st.markdown(f'<div class="cal card" style="border-left:4px solid {bl};">'
                    f'<div class="cal-date">{item["deadline"]}</div>'
                    f'<div><span class="b" style="background:{bc};color:{tc};">{p}</span> '
                    f'<span class="b b-role">{item["regulator"]}</span><br>'
                    f'<span style="color:#94a3b8;font-size:.85rem;">{item["description"]}</span></div>'
                    f'</div>', unsafe_allow_html=True)


# ─── TAB 5: AUDIT TRAIL ───────────────────────────────────────────────────
with t_audit:
    st.markdown("#### Audit Trail")
    st.caption("Immutable record of all queries, agent invocations, and compliance actions.")

    df_a = get_mock_audit_trail(n=40)

    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1: fu = st.selectbox("User", ["All"]+sorted(df_a["USERNAME"].unique().tolist()), key="af_u")
    with fc2: fs = st.selectbox("Status", ["All","Completed","Error"], key="af_s")
    with fc3: fr = st.selectbox("Role", ["All"]+sorted(df_a["ROLE"].unique().tolist()), key="af_r")
    with fc4: fa = st.text_input("Agent", placeholder="e.g. Risk…", key="af_a")

    filt = df_a.copy()
    if fu != "All": filt = filt[filt["USERNAME"]==fu]
    if fs != "All": filt = filt[filt["STATUS"]==fs]
    if fr != "All": filt = filt[filt["ROLE"]==fr]
    if fa: filt = filt[filt["AGENTS_INVOKED"].str.contains(fa, case=False, na=False)]

    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Queries", len(filt))
    a2.metric("Completed", len(filt[filt["STATUS"]=="Completed"]))
    a3.metric("Errors", len(filt[filt["STATUS"]=="Error"]))
    a4.metric("Avg Risk", f'{filt["RISK_SCORE"].mean():.0f}' if len(filt) else "—")

    st.dataframe(filt[["AUDIT_ID","TIMESTAMP","USERNAME","ROLE","QUERY","AGENTS_INVOKED","RISK_SCORE","STATUS"]], hide_index=True, height=400)

    try:
        atxt = f"AUDIT TRAIL EXPORT\nGenerated: {datetime.now().strftime('%d-%m-%Y %H:%M')}\nRecords: {len(filt)}\n\n"
        for _, r in filt.head(50).iterrows():
            atxt += f"[{r['TIMESTAMP']}] {r['USERNAME']} ({r['ROLE']})\n  {r['QUERY']}\n  Agents: {r['AGENTS_INVOKED']} | Risk: {r['RISK_SCORE']} | {r['STATUS']}\n\n"
        apdf = export_report_to_pdf(atxt, "Audit Trail Export", st.session_state.user["username"],
                                     f"{filt['TIMESTAMP'].iloc[-1][:10]} to {filt['TIMESTAMP'].iloc[0][:10]}")
        st.download_button("Export Audit PDF", apdf, f"Auris_Audit_{datetime.now().strftime('%Y%m%d')}.pdf", "application/pdf")
    except Exception:
        pass


# ─── TAB 6: RISK HEATMAP ──────────────────────────────────────────────────
with t_heatmap:
    st.markdown("#### Risk Heatmap")
    st.caption("Temporal risk intensity — average risk score by hour × day. Darker = higher risk.")

    if _PLOTLY:
        df_h = get_mock_risk_heatmap(days=14)
        piv = df_h.pivot(index="HOUR", columns="DATE", values="AVG_RISK_SCORE")
        hrs = [f"{h:02d}:00" for h in range(24)]

        fig_h = go.Figure(go.Heatmap(
            z=piv.values, x=piv.columns.tolist(), y=hrs,
            colorscale=[[0,"#0a1530"],[.25,"#0d2f5e"],[.45,"#1a4080"],[.55,"#f59e0b"],[.75,"#ef4444"],[1,"#7f1d1d"]],
            hovertemplate="Date: %{x}<br>Hour: %{y}<br>Risk: %{z:.1f}<extra></extra>",
            colorbar=dict(title="Risk", titlefont=dict(color="#93c5fd"), tickfont=dict(color="#64748b")),
        ))
        fig_h.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter",color="#cdd9f0"),
                            xaxis=dict(title="Date",tickangle=45,tickfont=dict(size=9,color="#64748b")),
                            yaxis=dict(title="Hour",tickfont=dict(size=9,color="#64748b"),autorange="reversed"),
                            margin=dict(l=60,r=20,t=20,b=80), height=480)
        st.plotly_chart(fig_h, use_container_width=True)

        # Insight cards
        ha = df_h.groupby("HOUR")["AVG_RISK_SCORE"].mean()
        da = df_h.groupby("DATE")["AVG_RISK_SCORE"].mean()
        ph = int(ha.idxmax()); pr = ha.max()
        tf = df_h["FLAGGED_COUNT"].sum(); tt = df_h["TXN_COUNT"].sum()
        rd = da.idxmax()

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
                        f'<div style="color:#64748b;font-size:.75rem;">Avg: {da.max():.1f}</div></div>', unsafe_allow_html=True)

        st.markdown("**Flagged Volume by Hour**")
        hf = df_h.groupby("HOUR")["FLAGGED_COUNT"].sum().reset_index()
        fig_f = px.bar(hf, x="HOUR", y="FLAGGED_COUNT", template="plotly_dark",
                       color="FLAGGED_COUNT", color_continuous_scale=["#0d2f5e","#f59e0b","#ef4444"])
        fig_f.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=8,b=0),
                            height=220, font=dict(family="Inter"), coloraxis_showscale=False, xaxis=dict(dtick=1))
        st.plotly_chart(fig_f, use_container_width=True)
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
        st.dataframe(pd.DataFrame(matrix_rows), hide_index=True)

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
