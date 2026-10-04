# ⚡ RegIQ — Hackathon Ideation Document
### Snowflake CoCo CLI Hackathon 2026 · GCC Edition · Problem Statement #1

> **Risk, Fraud & Regulatory Intelligence Copilot**
> *A permission-aware, multi-agent RAG system for banking & NBFC compliance teams*

---

## 📋 Table of Contents
1. [What We're Building](#1-what-were-building)
2. [The Problem](#2-the-problem)
3. [Our Solution](#3-our-solution)
4. [Architecture](#4-architecture)
5. [The Three Agents](#5-the-three-agents)
6. [Data Layer & Strategy](#6-data-layer--strategy)
7. [Permission-Aware RAG](#7-permission-aware-rag)
8. [Output Surfaces](#8-output-surfaces)
9. [Tech Stack](#9-tech-stack)
10. [Hackathon Build Plan](#10-hackathon-build-plan)

---

## 1. What We're Building

**RegIQ** is a compliance copilot that sits on top of a bank's Snowflake data and gives compliance analysts a natural-language interface to their own data — with every response grounded in real policy documents and real transaction records, not hallucinations.

| | |
|---|---|
| 🏆 **Hackathon** | Snowflake CoCo CLI Hackathon 2026 — GCC Edition |
| 📌 **Problem Statement** | #1 — Risk, Fraud & Regulatory Intelligence |
| 💰 **Prize Pool** | $10,000 |
| 👥 **Team Size** | 1–4 members |
| 🌍 **Eligibility** | India GCC developers |

### Core Capabilities at a Glance

| Capability | What it does |
|---|---|
| 🧠 **Multi-Agent Brain** | Three specialised agents — Risk, Fraud, Regulatory — orchestrated together |
| 🔒 **Permission-Aware RAG** | Every retrieval respects the querying user's clearance level |
| 📋 **Audit-Ready Output** | Every response cites the exact regulatory clause it drew from |
| 💬 **Slack-Native Alerts** | Real-time fraud alerts pushed to the compliance team's Slack |
| ❄️ **Runs on Snowflake** | No external infra — vector search, LLM inference, alerts all inside Snowflake Cortex |
| ⚡ **Built with CoCo CLI** | CoCo CLI generates SQL, agent scaffolding, and Cortex pipelines from plain English |

---

## 2. The Problem

> *"Banking and NBFC teams manage real-time fraud, liquidity and credit risk, and regulatory reporting (AML, Basel, and local regulations), largely manual today."* — Hackathon Brief

### By the Numbers

| Stat | Figure |
|---|---|
| 💸 Estimated global money laundering per year | **$4.2 Trillion** |
| ⏱️ Average time to generate a manual AML report | **72 hours** |
| 📊 Compliance analyst time spent on data gathering (not analysis) | **60%** |
| 📈 Rise in regulatory filings expected by 2027 | **3–5x** |

### Root Causes

**🏚️ Data lives in silos**
Transaction data, customer KYC records, AML watchlists, Basel risk models, and internal policy docs all live in different systems with no unified query layer.

**🐌 Regulatory reporting is fully manual**
A compliance officer manually pulls transaction records, cross-references AML guidelines, fills regulatory templates, and gets approvals — each report taking days or weeks.

**🔍 Fraud signals get missed or spotted too late**
Risk thresholds are static and rules-based. By the time an analyst reviews a flagged transaction, the fraud ring has moved on. No real-time reasoning over live data.

**🤖 Generic AI hallucinates on regulatory questions**
Asking a generic LLM about Basel III liquidity requirements gives plausible-sounding answers — but they're not grounded in the bank's actual internal policies or the exact regulatory text that applies to them.

**🔐 Access control is ignored by most AI tools**
A junior analyst shouldn't be able to retrieve board-level risk reports or personal KYC data of high-profile customers. Most AI tools ignore this entirely.

---

## 3. Our Solution

### How RegIQ Works — Step by Step

```
Step 1 → Analyst types a natural language question
         (in Streamlit dashboard or Slack)

Step 2 → Orchestrator identifies which agent(s) to route to
         (Risk / Fraud / Regulatory — or a combination)

Step 3 → Permission-aware RAG retrieves grounded context
         (only docs + data the querying user is cleared to see)

Step 4 → Agent(s) reason over retrieved context via Cortex LLM
         (no hallucinations — every claim tied to a source)

Step 5 → Cited, audit-ready response returned
         (with regulatory clause ref, risk score, next action)
         (if risk score ≥ threshold → Slack alert fires)
```

### Sample Interaction

**👤 Compliance Analyst asks:**
> *"Flag all transactions over ₹10L from the past 7 days, score them for AML risk, and generate a FINTRAC-ready summary report with the applicable RBI circular cited."*

**🤖 RegIQ responds (3.2 seconds later):**
```
✅ 14 transactions flagged | 3 high-risk (score ≥ 80) | 1 Slack alert sent

📌 Regulation: RBI Master Direction – KYC, 2016 (Updated Feb 2024), Section 12(iii)

📋 Report generated: AML_Summary_2026-10-05.pdf

⚠️ TXN-8821, TXN-9034, TXN-7723 flagged for immediate review
   → Potential structuring pattern detected
```

### RegIQ vs The Status Quo

| | ✅ RegIQ | ❌ Status Quo / Generic AI |
|---|---|---|
| Accuracy | Grounded in YOUR policy docs — no hallucinations | Generic LLMs hallucinate on specific rules |
| Access control | Permission-aware — analyst sees only what they're cleared for | No access control — everyone sees everything |
| Citations | Cites the exact regulatory clause every time | No citations — no way to verify the answer |
| Speed | Fraud signals surfaced in real-time | Fraud spotted days after the fact |
| Data security | Runs entirely inside Snowflake — nothing leaves your environment | Data sent to external APIs — security risk |
| Report generation | Natural language → audit-ready report in seconds | Manual process takes 72+ hours |

---

## 4. Architecture

### System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    📥 DATA LAYER (in Snowflake)                 │
│                                                                 │
│  📊 Transaction Tables  👤 KYC Records  🚨 AML Watchlists      │
│  📄 Policy PDFs → Cortex Search Index   📑 Basel III/IV Docs   │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│              🔒 PERMISSION-AWARE RAG PIPELINE                   │
│                                                                 │
│  Query + User Identity → ACL Check → Cortex Search             │
│                       → Permission-filtered ranked chunks       │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│           🤖 MULTI-AGENT ORCHESTRATION (Snowflake Cortex)       │
│                                                                 │
│   🔵 Risk Assessment    🔴 Fraud Detection    🟢 Regulatory     │
│      Agent                 Agent                Report Agent   │
└─────────────────┬───────────────────────────────────┬───────────┘
                  │                                   │
                  ▼                                   ▼
┌─────────────────────────────┐   ┌───────────────────────────────┐
│  🖥️ Streamlit Dashboard     │   │  💬 Slack Alerts & Bot        │
│  (deep analysis + reports)  │   │  (real-time fraud alerts)     │
└─────────────────────────────┘   └───────────────────────────────┘
```

### Where CoCo CLI Fits

> ⚠️ **Important:** CoCo CLI is NOT a component of the final application. It's the development tool used to **build** everything faster.

```
You type in plain English
    ↓
"Create a Snowflake table for transaction records with risk scores and AML flags"
    ↓
CoCo CLI generates SQL DDL, Cortex Search setup, agent scaffolding, Alert definitions
    ↓
You deploy the generated code to Snowflake as your production system
```

CoCo CLI = your build-time accelerator, not a runtime dependency.

---

## 5. The Three Agents

### 🔵 Agent 1 — Risk Assessment Agent

**Purpose:** Assess liquidity risk, credit risk, and Basel compliance

| Task | Detail |
|---|---|
| Transaction risk scoring | Scores transactions against Basel III / IV risk thresholds |
| Liquidity monitoring | Watches LCR and NSFR metrics against regulatory minimums |
| Portfolio risk view | Surfaces anomalies across the customer risk portfolio |
| Regulatory comparison | Compares current risk exposure to RBI-mandated limits |
| Risk heatmaps | Generates visualisable risk distributions over time periods |

**Data sources:** Snowflake transaction tables + Basel docs in Cortex Search

---

### 🔴 Agent 2 — Fraud Detection Agent

**Purpose:** Real-time fraud signal detection and pattern analysis

| Task | Detail |
|---|---|
| AML watchlist matching | Cross-references transactions against OFAC / UN sanctioned entity lists |
| Fraud ring detection | Identifies relationship patterns between flagged accounts |
| Risk score assignment | Assigns 0–100 fraud risk score with explainability per transaction |
| Real-time alerting | Fires Snowflake Alert → Slack notification when score ≥ threshold (e.g. 70) |
| Structuring detection | Detects transaction structuring patterns (intentional sub-threshold splitting) |

**Data sources:** Snowflake transaction + KYC tables + AML watchlist table

---

### 🟢 Agent 3 — Regulatory Report Agent

**Purpose:** RAG-grounded regulatory Q&A and audit-ready report generation

| Task | Detail |
|---|---|
| Regulatory Q&A | Answers compliance questions grounded in RBI, Basel, SEBI docs |
| Citation | Every response includes exact section number and document source |
| Report generation | Produces submission-ready AML summary reports and Basel disclosures |
| Regulatory change tracking | Surfaces what changed in recent regulatory updates |
| Deadline tracking | Monitors open regulatory reporting obligations and deadlines |

**Data sources:** Cortex Search index of RBI Master Directions, Basel III/IV BIS docs, internal policy PDFs

---

## 6. Data Layer & Strategy

### Data Sources — Hackathon vs Production

| Data Type | Source | Stored as | Used by | Hackathon approach |
|---|---|---|---|---|
| Transaction records | Core banking | Snowflake table | All 3 agents | Synthetic data |
| Customer KYC profiles | KYC database | Snowflake table | Fraud Agent | Synthetic data |
| AML watchlists | Sanctioned entity lists | Snowflake table | Fraud Agent | Public data (OFAC, UN) |
| RBI AML Guidelines | rbi.org.in | Cortex Search index | Regulatory Agent | Public PDF |
| Basel III / IV docs | bis.org | Cortex Search index | Risk + Regulatory Agent | Public PDF |
| Internal risk policies | Bank internal | Cortex Search index | All 3 agents | Sample internal docs |
| User permission roles | Identity system | Snowflake ACL table | RAG filter | Hardcoded for demo |

### Production Data Ingestion (Beyond Hackathon)

For companies **already on Snowflake** (the GCC target audience):
- Data is already in Snowflake tables — no ingestion connectors needed
- Regulatory PDFs uploaded directly to Snowflake stage → indexed via Cortex Search

For companies **not on Snowflake**:
- Snowflake's native connectors (Google Drive, S3, Kafka, SharePoint) handle ingestion
- Our plug-and-play RAG pipeline (the original product) sits on top as the hosted backend

---

## 7. Permission-Aware RAG

This is the single most important differentiator. Most RAG systems retrieve everything and hope the application handles access control. RegIQ filters **before** ranking, not after.

### The Filter Flow

```
1. Query arrives with user identity token
   (role: Junior Analyst | Senior Analyst | Compliance Head)
          │
          ▼
2. ACL table lookup in Snowflake
   (returns: permitted document categories + data scopes for this user)
          │
          ▼
3. Permission-scoped Cortex Search query
   (similarity search runs ONLY over permitted document set)
          │
          ▼
4. Ranked results — all guaranteed within user's permissions
   (restricted docs never appear as candidates, let alone in responses)
          │
          ▼
5. Agent reasons only over what it received
   (no way to access data that didn't pass the filter)
```

### Why "filter before ranking" matters

| Approach | Risk |
|---|---|
| ❌ Rank all docs → filter results | A restricted doc may rank #1 → the agent sees it before filtering removes it from the response. The model "knows" the content even if it doesn't output it. |
| ✅ Filter first → rank permitted docs only | Restricted docs never enter the retrieval process at all. The agent is structurally incapable of seeing them. |

---

## 8. Output Surfaces

### 🖥️ Streamlit in Snowflake — Analyst Dashboard

- Natural language query interface
- Transaction risk heatmap & timeline view
- Fraud case viewer with fraud-ring relationship map
- Regulatory report builder with clause citations
- Full audit trail of all queries and responses
- Role-based UI (what you see = your clearance level)
- Export reports as PDF

### 💬 Slack Bot — Real-Time Alerts & Quick Queries

- Fraud alert posted to compliance channel when risk score ≥ threshold
- Daily risk summary posted automatically each morning
- Ask RegIQ questions directly from Slack (`@regiq what's our current LCR?`)
- Approval workflow for flagged transactions directly inside Slack
- Regulatory deadline reminders
- Each alert includes: transaction ID + risk score + reason + regulatory reference

> 💡 **Why Slack matters for the demo:** GCC compliance teams already live in Slack. Getting fraud alerts in their existing workflow — without opening another tool — is the "production-ready" detail that scores high on Solution Completeness (30% of evaluation).

---

## 9. Tech Stack

### Inside Snowflake (Runtime)

| Component | Tool | Purpose |
|---|---|---|
| Structured data store | Snowflake Tables | Transactions, KYC, watchlists, ACL |
| Vector search & RAG | Snowflake Cortex Search | Regulatory doc retrieval |
| LLM inference | Snowflake Cortex | Agent reasoning (Mistral / LLaMA / Arctic) |
| Real-time alerting | Snowflake Alerts | Fraud threshold triggers → Slack |
| Python agent logic | Snowpark Python | Agent orchestration code |
| UI | Streamlit in Snowflake | Analyst dashboard |
| Access control | Snowflake RBAC | Role-based data isolation |

### Build Tools (Development Only)

| Tool | Role |
|---|---|
| ⚡ Snowflake CoCo CLI | Generates SQL, agent scaffolding, Cortex setup from plain English prompts |
| 🐍 Python | Agent logic, orchestration |
| 📄 PDF parser | Ingesting regulatory PDFs into Cortex Search |
| 💬 Slack Webhooks | Alert delivery from Snowflake Alerts to Slack |

### Judging Rubric — How We Score

| Criterion | Weight | Our Position |
|---|---|---|
| **Technical Execution** | 40% | Multi-agent orchestration + permission-aware retrieval + Cortex Search + Alerts + Streamlit |
| **Real-World Relevance** | 30% | AML & Basel compliance are the most pressing pain points for Indian GCC banking teams |
| **Solution Completeness** | 30% | End-to-end: UI + Slack + PDF export + ACL + cited outputs = full production-grade system |

---

## 10. Hackathon Build Plan

### Key Dates

| Date | Event |
|---|---|
| 12 Aug 2026 | Workshop 1 — CoCo CLI Starter (attend this) |
| 19 Aug 2026 | Workshop 2 — CoCo CLI Hands-on (attend this) |
| 13 Sep – 4 Oct 2026 | **Prototype Submission Window** |
| 23 Oct 2026 | Shortlist Announcement |
| 26 Oct 2026 | Induction Session |
| 27–30 Oct 2026 | **Grand Finale Demo Days** |

### Week-by-Week Build Plan

**Week 1 — Data & Foundation**
- Set up Snowflake environment
- Create tables: transactions, KYC, AML watchlists, ACL/permissions
- Load synthetic banking transaction data
- Download and upload public PDFs: RBI Master Directions, BIS Basel III/IV
- Index regulatory PDFs into Cortex Search
- Use CoCo CLI to scaffold all table DDL and Cortex Search setup

**Week 2 — Permission-Aware RAG Pipeline**
- Implement Cortex Search indexing with document-level ACL tags
- Build the permission pre-filter logic in Snowpark Python
- Test that role-based access works correctly end-to-end
- Validate retrieval quality with a small golden query set (5–10 test queries)

**Week 3 — The Three Agents**
- Risk Assessment Agent: Basel metrics, liquidity risk scoring logic
- Fraud Detection Agent: AML watchlist matching, risk score assignment, Snowflake Alert setup
- Regulatory Report Agent: RAG-grounded Q&A with citation formatting
- Wire up the orchestrator to route queries to the right agent(s)

**Week 4 — UI + Slack Integration**
- Build Streamlit in Snowflake dashboard
- Add query interface, risk heatmap, fraud case viewer, report exporter
- Wire Snowflake Alerts to Slack webhook
- End-to-end testing with realistic queries

**Week 5 — Polish & Submit**
- Record demo walkthrough video
- Polish Streamlit UI
- Write up architecture for submission
- Prepare finale presentation
- Highlight permission-aware RAG and Slack integration as key differentiators

### Prize Targets

| Prize | Amount |
|---|---|
| 🥇 Winner | $4,300 / ₹4,00,000 |
| 🥈 1st Runner-up | $2,200 / ₹2,00,000 |
| 🥉 2nd Runner-up | $1,590 / ₹1,50,000 |
| 🎖️ Consolation (×5) | $530 / ₹50,000 each |

---

*Document version: PoC / Hackathon stage · Last updated: Oct 2026*
