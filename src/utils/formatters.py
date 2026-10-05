"""
formatters.py
=============
Display and data-formatting utilities for the Auris compliance platform.

All functions are pure (no side effects) and safe to call from any layer
of the application.
"""

from __future__ import annotations

import uuid
import math
from datetime import datetime, date
from typing import Any


# ---------------------------------------------------------------------------
# Currency formatting
# ---------------------------------------------------------------------------


def format_inr(amount: float) -> str:
    """Format *amount* using the Indian numbering system with a ₹ symbol.

    Groups digits as: last three, then pairs from the right.

    Parameters
    ----------
    amount:
        Numeric value in Indian Rupees (fractional paise are shown to 2 dp
        if the amount has a meaningful decimal part).

    Returns
    -------
    str
        Formatted string, e.g. ``'₹1,23,45,678'`` or ``'₹45,678.50'``.

    Examples
    --------
    >>> format_inr(12345678)
    '₹1,23,45,678'
    >>> format_inr(1000)
    '₹1,000'
    >>> format_inr(500.75)
    '₹500.75'
    """
    # Separate integer and decimal parts
    int_part = int(math.floor(amount))
    dec_part = round(amount - int_part, 2)

    s = str(int_part)

    if len(s) <= 3:
        formatted = s
    else:
        # Last 3 digits
        formatted = s[-3:]
        s = s[:-3]
        while s:
            formatted = s[-2:] + "," + formatted
            s = s[:-2]

    if dec_part > 0:
        dec_str = f"{dec_part:.2f}"[1:]  # e.g. '.75'
        return f"₹{formatted}{dec_str}"
    return f"₹{formatted}"


# ---------------------------------------------------------------------------
# Risk badge
# ---------------------------------------------------------------------------


def format_risk_badge(score: int) -> str:
    """Return a coloured emoji badge for the given *score*.

    Parameters
    ----------
    score:
        Integer risk score in the range 0–100.

    Returns
    -------
    str
        - 0–40  → ``'🟢 LOW (score)'``
        - 41–70 → ``'🟡 MEDIUM (score)'``
        - 71–100 → ``'🔴 HIGH (score)'``

    Examples
    --------
    >>> format_risk_badge(25)
    '🟢 LOW (25)'
    >>> format_risk_badge(55)
    '🟡 MEDIUM (55)'
    >>> format_risk_badge(88)
    '🔴 HIGH (88)'
    """
    if score <= 40:
        return f"🟢 LOW ({score})"
    if score <= 70:
        return f"🟡 MEDIUM ({score})"
    return f"🔴 HIGH ({score})"


# ---------------------------------------------------------------------------
# Agent response formatter
# ---------------------------------------------------------------------------


def format_agent_response(agent_name: str, result: dict) -> str:
    """Format an agent's result dictionary into a clean Markdown string.

    Handles the following keys (all optional):

    - ``summary`` (str)
    - ``risk_score`` (int)
    - ``flagged_transactions`` (list[dict] — each with ``txn_id`` / ``amount`` / ``risk_score``)
    - ``citations`` (list[dict] — each with ``doc_name``, ``section``, ``content``)
    - ``recommendations`` (list[str])

    Parameters
    ----------
    agent_name:
        Display name for the agent (used in the heading).
    result:
        The agent's output dictionary.

    Returns
    -------
    str
        A Markdown-formatted string suitable for display in Streamlit or a
        terminal.
    """
    lines: list[str] = [f"## 🤖 {agent_name} — Analysis Result\n"]

    if "summary" in result:
        lines.append(f"### Summary\n{result['summary']}\n")

    if "risk_score" in result:
        badge = format_risk_badge(int(result["risk_score"]))
        lines.append(f"### Risk Assessment\n**Score:** {badge}\n")

    if "flagged_transactions" in result:
        txns: list[dict] = result["flagged_transactions"]
        if txns:
            lines.append(f"### Flagged Transactions ({len(txns)})\n")
            lines.append("| TXN ID | Amount | Risk Score |")
            lines.append("|--------|--------|------------|")
            for t in txns:
                tid = t.get("txn_id", "—")
                amt = format_inr(float(t.get("amount", 0)))
                score = int(t.get("risk_score", 0))
                lines.append(f"| `{tid}` | {amt} | {format_risk_badge(score)} |")
            lines.append("")

    if "citations" in result:
        cites: list[dict] = result["citations"]
        if cites:
            lines.append("### Regulatory Citations\n")
            for c in cites:
                doc_name = c.get("doc_name", "Unknown Document")
                section = c.get("section", "")
                content = c.get("content", "")
                lines.append(format_regulatory_citation(doc_name, section, content))
                lines.append("")

    if "recommendations" in result:
        recs: list[str] = result["recommendations"]
        if recs:
            lines.append("### Recommendations\n")
            for rec in recs:
                lines.append(f"- {rec}")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Audit record builder
# ---------------------------------------------------------------------------


def build_audit_record(
    user_id: str,
    query: str,
    agent: str,
    response: dict,
    session_id: str = "",
) -> dict:
    """Build a dict that matches the ``AUDIT_TRAIL`` Snowflake table schema."""
    risk_score = response.get("risk_score", None)
    flagged = response.get("flagged_transactions", response.get("flagged_items", []))
    flagged_count = len(flagged) if isinstance(flagged, list) else 0

    # Truncate summary to 500 chars for the Snowflake VARCHAR column
    summary_raw: str = response.get("summary", str(response))
    summary_truncated = summary_raw[:500] if len(summary_raw) > 500 else summary_raw
    audit_uuid = str(uuid.uuid4())
    now_iso = datetime.utcnow().isoformat() + "Z"

    return {
        "AUDIT_ID": audit_uuid,
        "audit_id": audit_uuid,
        "USER_ID": user_id,
        "user_id": user_id,
        "SESSION_ID": session_id,
        "session_id": session_id,
        "AGENT_NAME": agent,
        "agent": agent,
        "QUERY_TEXT": query,
        "query": query,
        "RESPONSE_SUMMARY": summary_truncated,
        "summary": summary_truncated,
        "RISK_SCORE": risk_score,
        "risk_score": risk_score,
        "FLAGGED_COUNT": flagged_count,
        "flagged_count": flagged_count,
        "CREATED_AT": now_iso,
        "created_at": now_iso,
    }


# ---------------------------------------------------------------------------
# Regulatory citation formatter
# ---------------------------------------------------------------------------


def format_regulatory_citation(
    doc_name: str,
    section: str,
    content_snippet: str,
) -> str:
    """Format a regulatory citation as a Markdown block-quote.

    Parameters
    ----------
    doc_name:
        Full name of the regulatory document.
    section:
        Section identifier (e.g. ``'12(iii)'``).
    content_snippet:
        Excerpt from the section (will be shown as a block-quote).

    Returns
    -------
    str
        Formatted string in the form::

            📌 [doc_name], Section [section]:
            > [content_snippet]

    Examples
    --------
    >>> print(format_regulatory_citation(
    ...     "RBI Master Direction – KYC 2016", "12(iii)",
    ...     "Banks shall carry out enhanced due diligence…"
    ... ))
    📌 RBI Master Direction – KYC 2016, Section 12(iii):
    > Banks shall carry out enhanced due diligence…
    """
    return f"📌 **{doc_name}**, Section {section}:\n> {content_snippet}"


# ---------------------------------------------------------------------------
# Transaction display row
# ---------------------------------------------------------------------------


def txn_to_display_row(txn: dict) -> dict:
    """Convert a raw transaction dict into a display-friendly version.

    Formats monetary amounts with :func:`format_inr`, risk scores with
    :func:`format_risk_badge`, and dates into a human-readable string.

    Parameters
    ----------
    txn:
        Raw transaction dict.  Expected keys (all optional with fallbacks):
        ``TXN_ID``, ``TXN_DATE``, ``AMOUNT``, ``TXN_TYPE``,
        ``CUSTOMER_ID``, ``COUNTERPARTY_COUNTRY``, ``RISK_SCORE``,
        ``AML_FLAG``.

    Returns
    -------
    dict
        Display-ready dict with the same keys plus ``AMOUNT_DISPLAY``,
        ``RISK_BADGE``, ``DATE_DISPLAY``, and ``AML_STATUS``.
    """
    display = dict(txn)  # shallow copy so we don't mutate the original

    # Formatted amount
    raw_amount: float = float(txn.get("AMOUNT", txn.get("amount", 0)))
    display["AMOUNT_DISPLAY"] = format_inr(raw_amount)

    # Risk badge
    raw_score = int(txn.get("RISK_SCORE", txn.get("risk_score", 0)))
    display["RISK_BADGE"] = format_risk_badge(raw_score)

    # Date
    raw_date: Any = txn.get("TXN_DATE", txn.get("txn_date", ""))
    if isinstance(raw_date, (datetime, date)):
        display["DATE_DISPLAY"] = raw_date.strftime("%d %b %Y")
    elif isinstance(raw_date, str) and raw_date:
        try:
            parsed = datetime.fromisoformat(raw_date[:10])
            display["DATE_DISPLAY"] = parsed.strftime("%d %b %Y")
        except ValueError:
            display["DATE_DISPLAY"] = raw_date
    else:
        display["DATE_DISPLAY"] = "—"

    # AML status label
    aml_flag = txn.get("AML_FLAG", txn.get("aml_flag", False))
    display["AML_STATUS"] = "🚨 Flagged" if aml_flag else "✅ Clear"

    return display
