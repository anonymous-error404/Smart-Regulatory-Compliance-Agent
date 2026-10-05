"""
slack_alerts.py
===============
Slack alerting module for the Auris compliance platform.

All messages use Slack's Block Kit format for rich, structured notifications.
The module exposes a :class:`SlackAlerter` class and a module-level singleton
``alerter`` that is pre-configured from ``config.SLACK_WEBHOOK_URL``.

Usage
-----
    from src.alerts.slack_alerts import alerter

    alerter.send_fraud_alert(
        txn_id="TXN-00123",
        customer_id="CUST-0042",
        amount_inr=1_250_000.0,
        risk_score=85,
        fraud_reasons=["Structuring detected", "High-risk jurisdiction"],
        regulatory_ref="RBI Master Direction – KYC 2016, Section 12(iii)",
    )
"""

from __future__ import annotations

import json
import logging
import sys
import os
from datetime import date
from typing import Any

import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Ensure project root is importable
# ---------------------------------------------------------------------------
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config  # noqa: E402

logger = logging.getLogger(__name__)

# Deep-link base URL for the Streamlit review dashboard
_STREAMLIT_BASE_URL = "http://localhost:8501"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _inr(amount: float) -> str:
    """Format *amount* in Indian Rupee notation with the ₹ symbol.

    Examples
    --------
    >>> _inr(1_23_45_678)
    '₹1,23,45,678'
    """
    # Split into integer and fractional parts
    s = f"{int(round(amount))}"
    # Indian grouping: last 3 digits, then groups of 2
    if len(s) <= 3:
        return f"₹{s}"
    result = s[-3:]
    s = s[:-3]
    while s:
        result = s[-2:] + "," + result
        s = s[:-2]
    return f"₹{result}"


def _risk_emoji(score: int) -> str:
    """Return a coloured circle emoji representing the risk level."""
    if score >= 80:
        return "🔴"
    if score >= 41:
        return "🟡"
    return "🟢"


# ---------------------------------------------------------------------------
# SlackAlerter
# ---------------------------------------------------------------------------


class SlackAlerter:
    """Send structured Slack notifications for Auris compliance events.

    Parameters
    ----------
    webhook_url:
        Incoming Webhook URL.  Falls back to ``config.SLACK_WEBHOOK_URL`` when
        not provided.  If neither is set the alerter operates in *silent* mode
        (all sends are no-ops that log a warning).
    """

    def __init__(self, webhook_url: str | None = None) -> None:
        self._webhook_url: str | None = webhook_url or getattr(
            config, "SLACK_WEBHOOK_URL", None
        )
        if not self._webhook_url:
            logger.warning(
                "[SlackAlerter] No webhook URL configured. "
                "All Slack sends will be silent no-ops. "
                "Set SLACK_WEBHOOK_URL in your environment or config.py."
            )

    # ------------------------------------------------------------------
    # Public send methods
    # ------------------------------------------------------------------

    def send_fraud_alert(
        self,
        txn_id: str,
        customer_id: str,
        amount_inr: float = 0.0,
        risk_score: int = 50,
        fraud_reasons: list[str] | None = None,
        regulatory_ref: str = "",
        amount: float | None = None,
        fraud_score: int | None = None,
        **kwargs: Any,
    ) -> bool:
        """Send a fraud-alert Block Kit message to Slack.

        Parameters
        ----------
        txn_id:
            Transaction identifier (e.g. ``'TXN-00123'``).
        customer_id:
            Customer identifier (e.g. ``'CUST-0042'``).
        amount_inr:
            Transaction amount in Indian Rupees.
        risk_score:
            Integer risk score 0-100.
        fraud_reasons:
            Human-readable list of reasons for the alert.
        regulatory_ref:
            Regulatory citation string (e.g. regulation + section).

        Returns
        -------
        bool
            ``True`` if Slack returned HTTP 200, ``False`` otherwise.
        """
        if amount is not None:
            amount_inr = amount
        if fraud_score is not None:
            risk_score = fraud_score
        if fraud_reasons is None:
            fraud_reasons = []

        emoji = _risk_emoji(risk_score)
        reasons_text = "\n".join(f"• {r}" for r in fraud_reasons)
        review_url = f"{_STREAMLIT_BASE_URL}?page=review&txn={txn_id}"

        payload: dict[str, Any] = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🚨 FRAUD ALERT — Auris",
                        "emoji": True,
                    },
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Transaction:*\n`{txn_id}`"},
                        {"type": "mrkdwn", "text": f"*Customer:*\n`{customer_id}`"},
                        {"type": "mrkdwn", "text": f"*Amount:*\n{_inr(amount_inr)}"},
                        {
                            "type": "mrkdwn",
                            "text": f"*Risk Score:*\n{emoji} *{risk_score}/100*",
                        },
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Fraud Indicators:*\n{reasons_text}",
                    },
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"📌 *Regulation:* {regulatory_ref}",
                        }
                    ],
                },
                {"type": "divider"},
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "🔍 Review Now",
                                "emoji": True,
                            },
                            "style": "danger",
                            "url": review_url,
                            "action_id": "review_fraud_alert",
                        }
                    ],
                },
            ]
        }
        return self._post(payload)

    def send_daily_summary(self, stats: dict) -> bool:
        """Send a daily risk-digest Block Kit message to Slack.

        Parameters
        ----------
        stats:
            Dictionary with the following keys:

            - ``date`` (str | date): Report date.
            - ``total_txns`` (int): Total transactions processed.
            - ``flagged_count`` (int): Number of flagged transactions.
            - ``high_risk_count`` (int): Number of high-risk transactions.
            - ``total_flagged_amount`` (float): Sum of flagged amounts (INR).
            - ``top_risk_txns`` (list[dict]): Top flagged transactions.
              Each dict should have ``txn_id``, ``amount``, ``risk_score``.

        Returns
        -------
        bool
            ``True`` if Slack returned HTTP 200, ``False`` otherwise.
        """
        report_date = stats.get("date", date.today().isoformat())
        total_txns = stats.get("total_txns", 0)
        flagged_count = stats.get("flagged_count", 0)
        high_risk_count = stats.get("high_risk_count", 0)
        total_flagged_amount = stats.get("total_flagged_amount", 0.0)
        top_risk_txns: list[dict] = stats.get("top_risk_txns", [])

        # Build top-3 table rows
        table_lines: list[str] = ["`TXN ID         | Amount         | Risk`"]
        for txn in top_risk_txns[:3]:
            tid = txn.get("txn_id", "—")
            amt = _inr(txn.get("amount", 0))
            score = txn.get("risk_score", 0)
            badge = _risk_emoji(score)
            table_lines.append(f"`{tid:<15}| {amt:<15}| {badge} {score}`")

        table_text = "\n".join(table_lines) if top_risk_txns else "_No flagged transactions today._"

        # Amounts in Crores for readability
        flagged_cr = total_flagged_amount / 1_00_00_000
        flagged_cr_str = f"₹{flagged_cr:,.2f} Cr"

        payload: dict[str, Any] = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"📊 Auris Daily Risk Summary — {report_date}",
                        "emoji": True,
                    },
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Total Transactions:*\n{total_txns:,}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Flagged:*\n🟡 {flagged_count:,}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*High Risk:*\n🔴 {high_risk_count:,}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Total Flagged Amount:*\n{flagged_cr_str}",
                        },
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Top Flagged Transactions:*\n{table_text}",
                    },
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": (
                                "Generated by Auris Compliance Platform | "
                                "<http://localhost:8501|Open Dashboard>"
                            ),
                        }
                    ],
                },
            ]
        }
        return self._post(payload)

    def send_regulatory_deadline_reminder(self, deadline_info: dict) -> bool:
        """Send a regulatory deadline reminder to Slack.

        Parameters
        ----------
        deadline_info:
            Dict with keys:

            - ``regulation_name`` (str): Name of the regulation.
            - ``deadline_date`` (str): ISO-format deadline date.
            - ``days_remaining`` (int): Days until the deadline.
            - ``action_required`` (str): What the team needs to do.

        Returns
        -------
        bool
            ``True`` if Slack returned HTTP 200, ``False`` otherwise.
        """
        regulation = deadline_info.get("regulation_name", "Unknown Regulation")
        deadline_date = deadline_info.get("deadline_date", "—")
        days_remaining = deadline_info.get("days_remaining", 0)
        action_required = deadline_info.get("action_required", "No action specified.")

        urgency_emoji = "🔴" if days_remaining <= 3 else ("🟡" if days_remaining <= 7 else "🟢")

        payload: dict[str, Any] = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"⏰ Regulatory Deadline Reminder — Auris",
                        "emoji": True,
                    },
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Regulation:*\n{regulation}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Deadline Date:*\n📅 {deadline_date}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Days Remaining:*\n{urgency_emoji} *{days_remaining} day(s)*",
                        },
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Action Required:*\n{action_required}",
                    },
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "Auris Regulatory Calendar | <http://localhost:8501?page=calendar|View Calendar>",
                        }
                    ],
                },
            ]
        }
        return self._post(payload)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _post(self, payload: dict) -> bool:
        """POST *payload* as JSON to the configured Slack Incoming Webhook.

        Parameters
        ----------
        payload:
            Block Kit payload dict.

        Returns
        -------
        bool
            ``True`` on HTTP 200, ``False`` on any error (network, HTTP, etc.).
        """
        if not self._webhook_url:
            logger.debug("[SlackAlerter] No webhook configured — skipping send.")
            return False

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._webhook_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status
                if status == 200:
                    logger.info("[SlackAlerter] Message delivered (HTTP 200).")
                    return True
                logger.warning("[SlackAlerter] Unexpected HTTP status: %d", status)
                return False
        except urllib.error.HTTPError as exc:
            logger.error("[SlackAlerter] HTTP error posting to Slack: %s %s", exc.code, exc.reason)
            return False
        except urllib.error.URLError as exc:
            logger.error("[SlackAlerter] Network error posting to Slack: %s", exc.reason)
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error("[SlackAlerter] Unexpected error posting to Slack: %s", exc)
            return False


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

alerter = SlackAlerter()
