"""
streamlit/mock_data.py
----------------------
Mock data generators for the Auris Streamlit dashboard.

All functions return pandas DataFrames or dicts with realistic synthetic
banking / compliance data so the dashboard works fully offline (ENV='local').
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Seed for reproducibility within a session
# ---------------------------------------------------------------------------
_RNG = np.random.default_rng(seed=42)
random.seed(42)

# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------
_CUSTOMER_NAMES: list[str] = [
    "Arjun Kapoor", "Meera Nair", "Suresh Iyer", "Priya Bhatia",
    "Vikram Singh", "Anita Desai", "Rajesh Gupta", "Sunita Rao",
    "Harish Menon", "Kavya Sharma", "Aditya Joshi", "Pooja Verma",
    "Nitin Kulkarni", "Deepa Reddy", "Sameer Khan", "Lalitha Krishnan",
    "Ravi Pillai", "Smita Patil", "Mohit Agrawal", "Neha Choudhary",
]

_BANKS: list[str] = [
    "HDFC Bank", "ICICI Bank", "SBI", "Axis Bank", "Kotak Mahindra",
    "Yes Bank", "IndusInd Bank", "Punjab National Bank", "Bank of Baroda",
]

_TRANSACTION_TYPES: list[str] = [
    "NEFT", "RTGS", "IMPS", "UPI", "Wire Transfer", "Cash Deposit",
    "Cash Withdrawal", "Cheque",
]

_FRAUD_PATTERNS: list[str] = [
    "Structuring", "Round-Trip Transactions", "Rapid Movement",
    "Multiple Small Deposits", "Layering", "Shell Company",
    "Dormant Account Activity", "Velocity Spike",
]

_CASE_STATUSES: list[str] = ["Pending", "Reviewed", "Escalated"]

_REPORT_TYPES: list[str] = [
    "AML Summary Report", "Basel Disclosure", "FINTRAC Report",
    "CRILC Submission", "LCR Monthly Report",
]

_REPORT_STATUSES: list[str] = ["Draft", "Submitted", "Approved"]


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _random_txn_id() -> str:
    """Generate a realistic-looking transaction ID."""
    prefix = random.choice(["TXN", "REF", "UTR"])
    num = _RNG.integers(10_000_000, 99_999_999)
    return f"{prefix}{num}"


def _random_date(start: datetime, end: datetime) -> datetime:
    """Return a random datetime between *start* and *end*."""
    delta = (end - start).total_seconds()
    return start + timedelta(seconds=float(_RNG.integers(0, int(delta))))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_mock_transactions(n: int = 50) -> pd.DataFrame:
    """
    Generate *n* synthetic banking transactions.

    Returns
    -------
    pd.DataFrame
        Columns: TXN_ID, CUSTOMER_NAME, AMOUNT, RISK_SCORE, AML_FLAG,
                 TRANSACTION_TYPE, BANK, DATE, STATUS
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)

    records: list[dict[str, Any]] = []
    for _ in range(n):
        amount = float(_RNG.integers(5_000, 50_000_000))
        risk_score = int(_RNG.integers(0, 100))
        aml_flag = bool(risk_score > 70 or amount > 10_000_000)

        if risk_score < 35:
            risk_level = "Low"
        elif risk_score < 70:
            risk_level = "Medium"
        else:
            risk_level = "High"

        records.append(
            {
                "TXN_ID": _random_txn_id(),
                "CUSTOMER_NAME": random.choice(_CUSTOMER_NAMES),
                "AMOUNT": round(amount, 2),
                "RISK_SCORE": risk_score,
                "RISK_LEVEL": risk_level,
                "AML_FLAG": aml_flag,
                "TRANSACTION_TYPE": random.choice(_TRANSACTION_TYPES),
                "BANK": random.choice(_BANKS),
                "DATE": _random_date(start_date, end_date).strftime(
                    "%Y-%m-%d %H:%M"
                ),
                "STATUS": random.choice(["Completed", "Pending", "Flagged"]),
            }
        )

    df = pd.DataFrame(records)
    df.sort_values("DATE", ascending=False, inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def get_mock_metrics() -> dict[str, Any]:
    """
    Return a dict of high-level dashboard metrics.

    Returns
    -------
    dict
        Keys: total_txns, flagged_count, high_risk_count,
              total_flagged_amount, watchlist_hits,
              structuring_alerts, pending_review
    """
    return {
        "total_txns": int(_RNG.integers(1_800, 2_500)),
        "flagged_count": int(_RNG.integers(30, 120)),
        "high_risk_count": int(_RNG.integers(10, 45)),
        "total_flagged_amount": round(float(_RNG.integers(5_000_000, 80_000_000)), 2),
        "watchlist_hits": int(_RNG.integers(3, 18)),
        "structuring_alerts": int(_RNG.integers(2, 12)),
        "pending_review": int(_RNG.integers(5, 30)),
    }


def get_mock_fraud_cases(n: int = 10) -> pd.DataFrame:
    """
    Generate *n* synthetic fraud investigation cases.

    Returns
    -------
    pd.DataFrame
        Columns: CASE_ID, TXN_ID, CUSTOMER, AMOUNT, FRAUD_SCORE,
                 PATTERNS_DETECTED, STATUS, ASSIGNED_TO, OPENED_DATE
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=14)

    records: list[dict[str, Any]] = []
    for i in range(n):
        fraud_score = int(_RNG.integers(60, 100))
        num_patterns = int(_RNG.integers(1, 4))
        patterns = random.sample(_FRAUD_PATTERNS, num_patterns)

        records.append(
            {
                "CASE_ID": f"CASE{1000 + i:04d}",
                "TXN_ID": _random_txn_id(),
                "CUSTOMER": random.choice(_CUSTOMER_NAMES),
                "AMOUNT": round(float(_RNG.integers(500_000, 20_000_000)), 2),
                "FRAUD_SCORE": fraud_score,
                "PATTERNS_DETECTED": ", ".join(patterns),
                "STATUS": random.choice(_CASE_STATUSES),
                "ASSIGNED_TO": random.choice(
                    ["Priya Sharma", "Rahul Mehta", "Deepa Krishnan"]
                ),
                "OPENED_DATE": _random_date(start_date, end_date).strftime(
                    "%Y-%m-%d"
                ),
            }
        )

    df = pd.DataFrame(records)
    df.sort_values("FRAUD_SCORE", ascending=False, inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def get_mock_risk_timeseries(days: int = 7) -> pd.DataFrame:
    """
    Generate a daily transaction-volume-by-risk-level DataFrame
    for the last *days* days.

    Returns
    -------
    pd.DataFrame
        Columns: DATE, RISK_LEVEL, TRANSACTION_COUNT, TOTAL_AMOUNT
    """
    end_date = datetime.now().date()
    records: list[dict[str, Any]] = []

    for d in range(days):
        date = end_date - timedelta(days=(days - 1 - d))
        for risk_level in ["Low", "Medium", "High"]:
            if risk_level == "Low":
                count = int(_RNG.integers(300, 700))
                base_amount = 200_000
            elif risk_level == "Medium":
                count = int(_RNG.integers(80, 200))
                base_amount = 1_500_000
            else:
                count = int(_RNG.integers(10, 50))
                base_amount = 8_000_000

            records.append(
                {
                    "DATE": str(date),
                    "RISK_LEVEL": risk_level,
                    "TRANSACTION_COUNT": count,
                    "TOTAL_AMOUNT": round(
                        float(_RNG.integers(base_amount, base_amount * 3)), 2
                    ),
                }
            )

    return pd.DataFrame(records)


def get_mock_regulatory_reports() -> pd.DataFrame:
    """
    Return a DataFrame of recently generated regulatory reports.

    Returns
    -------
    pd.DataFrame
        Columns: REPORT_ID, REPORT_TYPE, PERIOD, GENERATED_BY,
                 GENERATED_AT, STATUS
    """
    end_date = datetime.now()
    records: list[dict[str, Any]] = []

    for i in range(8):
        gen_date = end_date - timedelta(days=int(_RNG.integers(0, 30)))
        records.append(
            {
                "REPORT_ID": f"RPT{2000 + i:04d}",
                "REPORT_TYPE": random.choice(_REPORT_TYPES),
                "PERIOD": random.choice(
                    ["Sep 2026", "Oct 2026", "Q2 FY27", "Q3 FY27"]
                ),
                "GENERATED_BY": random.choice(
                    ["Priya Sharma", "Rahul Mehta", "Deepa Krishnan"]
                ),
                "GENERATED_AT": gen_date.strftime("%Y-%m-%d %H:%M"),
                "STATUS": random.choice(_REPORT_STATUSES),
            }
        )

    df = pd.DataFrame(records)
    df.sort_values("GENERATED_AT", ascending=False, inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def get_regulatory_calendar() -> list[dict[str, str]]:
    """
    Return a list of upcoming Indian banking regulatory deadlines for Q4 2026.

    Returns
    -------
    list[dict]
        Each dict has keys: deadline, regulator, description, priority
    """
    return [
        {
            "deadline": "15 Oct 2026",
            "regulator": "RBI",
            "description": "CRILC Q2 Report — Submit Central Repository of Information on Large Credits for Q2 FY27",
            "priority": "High",
        },
        {
            "deadline": "31 Oct 2026",
            "regulator": "FIU-IND",
            "description": "AML STR Filing for Sep 2026 — Suspicious Transaction Reports for September 2026",
            "priority": "High",
        },
        {
            "deadline": "7 Nov 2026",
            "regulator": "RBI",
            "description": "Basel LCR Monthly Report — Liquidity Coverage Ratio submission for Oct 2026",
            "priority": "Medium",
        },
        {
            "deadline": "15 Nov 2026",
            "regulator": "SEBI",
            "description": "Insider Trading Disclosure — Promoter shareholding & insider trading compliance report",
            "priority": "Medium",
        },
        {
            "deadline": "30 Nov 2026",
            "regulator": "RBI",
            "description": "Financial Inclusion Report — Progress report on financial inclusion targets",
            "priority": "Low",
        },
        {
            "deadline": "15 Dec 2026",
            "regulator": "FIU-IND",
            "description": "AML STR Filing for Nov 2026 — Suspicious Transaction Reports for November 2026",
            "priority": "High",
        },
        {
            "deadline": "31 Dec 2026",
            "regulator": "RBI",
            "description": "Annual KYC Review — Complete periodic KYC review for high-risk customers",
            "priority": "High",
        },
    ]


def get_mock_structuring_groups() -> list[dict[str, Any]]:
    """
    Return a list of suspected structuring groups — customers with multiple
    transactions designed to stay below reporting thresholds.

    Returns
    -------
    list[dict]
        Each dict has keys: customer, total_amount, transaction_count,
                            transactions (list[dict])
    """
    groups: list[dict[str, Any]] = []
    for _ in range(4):
        customer = random.choice(_CUSTOMER_NAMES)
        num_txns = int(_RNG.integers(4, 9))
        threshold = 1_000_000  # ₹10L reporting threshold

        txns = []
        total = 0.0
        for t in range(num_txns):
            amt = round(float(_RNG.integers(80_000, 990_000)), 2)
            total += amt
            txns.append(
                {
                    "txn_id": _random_txn_id(),
                    "amount": amt,
                    "date": (
                        datetime.now() - timedelta(days=int(_RNG.integers(0, 7)))
                    ).strftime("%Y-%m-%d"),
                    "type": random.choice(_TRANSACTION_TYPES),
                }
            )

        groups.append(
            {
                "customer": customer,
                "total_amount": round(total, 2),
                "transaction_count": num_txns,
                "transactions": txns,
            }
        )

    return groups


# ---------------------------------------------------------------------------
# Risk Heatmap data
# ---------------------------------------------------------------------------

def get_mock_risk_heatmap(days: int = 14) -> pd.DataFrame:
    """
    Generate a risk score heatmap matrix (hour × day).

    Returns
    -------
    pd.DataFrame
        Columns: DATE, HOUR, AVG_RISK_SCORE, TXN_COUNT, FLAGGED_COUNT
    """
    end_date = datetime.now().date()
    records: list[dict[str, Any]] = []

    for d in range(days):
        current_date = end_date - timedelta(days=(days - 1 - d))
        for hour in range(24):
            # Simulate higher risk during late night and early morning
            if 0 <= hour <= 5:
                base_risk = float(_RNG.integers(40, 75))
                txn_count = int(_RNG.integers(5, 25))
            elif 9 <= hour <= 17:
                base_risk = float(_RNG.integers(15, 55))
                txn_count = int(_RNG.integers(80, 300))
            else:
                base_risk = float(_RNG.integers(20, 60))
                txn_count = int(_RNG.integers(20, 80))

            flagged = int(txn_count * (base_risk / 200))

            records.append({
                "DATE": str(current_date),
                "HOUR": hour,
                "AVG_RISK_SCORE": round(base_risk, 1),
                "TXN_COUNT": txn_count,
                "FLAGGED_COUNT": flagged,
            })

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Fraud Ring / Network Graph data
# ---------------------------------------------------------------------------

_ACCOUNT_IDS: list[str] = [
    "ACC001", "ACC002", "ACC003", "ACC004", "ACC005",
    "ACC006", "ACC007", "ACC008", "ACC009", "ACC010",
    "ACC011", "ACC012", "ACC013", "ACC014", "ACC015",
]

def get_mock_fraud_ring() -> dict[str, Any]:
    """
    Generate a fraud ring network graph dataset.

    Returns
    -------
    dict
        Keys:
        - ``nodes``: list[dict] with ``id``, ``label``, ``type``,
          ``risk_score``, ``flagged``
        - ``edges``: list[dict] with ``source``, ``target``, ``amount``,
          ``txn_count``, ``label``
        - ``ring_name``: str
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    # Ring 1: Main ring (6 nodes)
    ring1_customers = random.sample(_CUSTOMER_NAMES, 6)
    ring1_accounts = random.sample(_ACCOUNT_IDS, 6)

    for i, (name, acc) in enumerate(zip(ring1_customers, ring1_accounts)):
        risk = int(_RNG.integers(55, 98))
        nodes.append({
            "id": acc,
            "label": name,
            "type": "individual" if i < 4 else "shell_company",
            "risk_score": risk,
            "flagged": risk > 70,
            "group": 1,
        })

    # Circular flow within ring
    for i in range(len(ring1_accounts)):
        target_idx = (i + 1) % len(ring1_accounts)
        amount = round(float(_RNG.integers(200_000, 900_000)), 2)
        edges.append({
            "source": ring1_accounts[i],
            "target": ring1_accounts[target_idx],
            "amount": amount,
            "txn_count": int(_RNG.integers(2, 8)),
            "label": f"₹{amount/100_000:.1f}L ({int(_RNG.integers(2,8))} txns)",
        })

    # Ring 2: Satellite nodes (4 feeder accounts)
    ring2_customers = random.sample(
        [n for n in _CUSTOMER_NAMES if n not in ring1_customers], 4
    )
    ring2_accounts = [a for a in _ACCOUNT_IDS if a not in ring1_accounts][:4]

    for name, acc in zip(ring2_customers, ring2_accounts):
        risk = int(_RNG.integers(40, 80))
        nodes.append({
            "id": acc,
            "label": name,
            "type": "feeder",
            "risk_score": risk,
            "flagged": risk > 70,
            "group": 2,
        })

    # Feeders connect to ring nodes
    for i, acc in enumerate(ring2_accounts):
        target = ring1_accounts[i % len(ring1_accounts)]
        amount = round(float(_RNG.integers(100_000, 500_000)), 2)
        edges.append({
            "source": acc,
            "target": target,
            "amount": amount,
            "txn_count": int(_RNG.integers(1, 5)),
            "label": f"₹{amount/100_000:.1f}L",
        })

    return {
        "nodes": nodes,
        "edges": edges,
        "ring_name": "Suspected Layering Network — West Region",
    }


# ---------------------------------------------------------------------------
# Audit Trail data
# ---------------------------------------------------------------------------

_AGENT_NAMES: list[str] = [
    "RiskAssessmentAgent", "FraudDetectionAgent", "RegulatoryReportAgent",
]

_AUDIT_QUERIES: list[str] = [
    "Flag all transactions over ₹10L in the last 7 days",
    "What is our current LCR status?",
    "Generate AML summary for September 2026",
    "Check for structuring patterns in NEFT transfers",
    "What does RBI say about KYC for high-risk customers?",
    "Show Basel III capital adequacy ratios",
    "List all watchlist matches this week",
    "Generate FINTRAC report for Q2 FY27",
    "Check fraud alerts for Arjun Kapoor",
    "What are the STR filing requirements under PMLA?",
    "Run risk assessment on cash deposits > ₹5L",
    "Show pending compliance deadlines",
]


def get_mock_audit_trail(n: int = 30) -> pd.DataFrame:
    """
    Generate *n* synthetic audit trail entries.

    Returns
    -------
    pd.DataFrame
        Columns: AUDIT_ID, TIMESTAMP, USER_ID, USERNAME, ROLE,
                 QUERY, AGENTS_INVOKED, RISK_SCORE, STATUS,
                 RESPONSE_PREVIEW
    """
    end_date = datetime.now()
    records: list[dict[str, Any]] = []

    for i in range(n):
        user = random.choice(
            [
                {"user_id": "USER001", "username": "Priya Sharma", "role": "junior_analyst"},
                {"user_id": "USER002", "username": "Rahul Mehta", "role": "senior_analyst"},
                {"user_id": "USER003", "username": "Deepa Krishnan", "role": "compliance_head"},
            ]
        )
        query = random.choice(_AUDIT_QUERIES)
        num_agents = int(_RNG.integers(1, 4))
        agents = random.sample(_AGENT_NAMES, min(num_agents, len(_AGENT_NAMES)))
        risk = int(_RNG.integers(0, 100))
        ts = _random_date(end_date - timedelta(days=14), end_date)

        records.append({
            "AUDIT_ID": f"AUD{10000 + i:05d}",
            "TIMESTAMP": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "USER_ID": user["user_id"],
            "USERNAME": user["username"],
            "ROLE": user["role"],
            "QUERY": query,
            "AGENTS_INVOKED": ", ".join(a.replace("Agent", "") for a in agents),
            "RISK_SCORE": risk,
            "STATUS": random.choice(["Completed", "Completed", "Completed", "Error"]),
            "RESPONSE_PREVIEW": f"Analysis complete. {risk}% risk. {len(agents)} agent(s) invoked.",
        })

    df = pd.DataFrame(records)
    df.sort_values("TIMESTAMP", ascending=False, inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


# ---------------------------------------------------------------------------
# Role-based filtered data helper
# ---------------------------------------------------------------------------

def get_role_data_scope(role: str) -> dict[str, Any]:
    """
    Return the data visibility scope for a given user role or clearance level.

    Returns
    -------
    dict
        Keys: max_amount_visible, can_see_pii, can_see_watchlist,
              can_see_board_reports, visible_regions
    """
    try:
        import config
        return config.get_role_config(role)
    except Exception:
        return {
            "max_amount_visible": 50_00_000,
            "can_see_pii": False,
            "can_see_watchlist": False,
            "can_see_board_reports": False,
            "visible_regions": ["West"],
        }


def filter_transactions_by_role(
    df: pd.DataFrame, role: str
) -> pd.DataFrame:
    """
    Filter a transactions DataFrame according to role-based access rules.

    Parameters
    ----------
    df : pd.DataFrame
        Raw transactions DataFrame.
    role : str
        User role string.

    Returns
    -------
    pd.DataFrame
        Filtered DataFrame respecting the role's data scope.
    """
    scope = get_role_data_scope(role)
    filtered = df.copy()

    # Amount cap: junior analysts can't see very high-value transactions
    max_amount = scope["max_amount_visible"]
    if max_amount < float("inf"):
        filtered = filtered[filtered["AMOUNT"] <= max_amount]

    # Mask customer names for junior analysts (show only initials)
    if not scope["can_see_pii"]:
        filtered["CUSTOMER_NAME"] = filtered["CUSTOMER_NAME"].apply(
            lambda name: " ".join(
                word[0] + "***" if len(word) > 1 else word
                for word in name.split()
            )
        )

    return filtered
