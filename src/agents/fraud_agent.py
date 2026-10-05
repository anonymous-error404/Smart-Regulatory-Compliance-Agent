"""
src/agents/fraud_agent.py
-------------------------
AML / CFT Fraud Detection Agent for Auris.

Identifies fraud patterns (structuring / smurfing, layering, round-tripping,
watchlist hits) in transaction data, scores each transaction, and triggers
Slack alerts for scores above FRAUD_ALERT_THRESHOLD.
"""

import logging
import re
from typing import Any

from src.agents.base_agent import BaseAgent
from src.alerts.slack_alerts import alerter
from src.utils.formatters import format_inr, format_risk_badge

import config

logger = logging.getLogger(__name__)

# Structuring window: transactions just under the ₹10L CTR threshold
_STRUCTURING_LOWER_INR = 800_000   # ₹8,00,000
_STRUCTURING_UPPER_INR = 1_000_000  # ₹10,00,000 (RBI Cash Transaction Report threshold)

# ------------------------------------------------------------------ #
#  System prompt                                                       #
# ------------------------------------------------------------------ #

_SYSTEM_PROMPT = """You are an expert AML/CFT (Anti-Money Laundering / Counter Financing of Terrorism) specialist for Indian banking, with deep knowledge of RBI AML guidelines, PMLA 2002, and FATF Recommendations.

Your task is to analyse the provided transaction data, detected patterns, and regulatory context, then produce a structured fraud risk assessment.

REGULATORY FRAMEWORK:
- RBI Master Direction on KYC (Updated 2023)
- Prevention of Money Laundering Act (PMLA) 2002 & PMLA Rules 2005
- RBI AML/CFT Guidelines for Banks
- FATF 40 Recommendations (especially R.20 Suspicious Transaction Reporting)
- RBI Cash Transaction Report (CTR) threshold: ₹10,00,000
- RBI Suspicious Transaction Report (STR) obligations

FRAUD PATTERNS TO DETECT:
1. STRUCTURING (Smurfing): Multiple transactions just below the ₹10L CTR threshold
2. LAYERING: Rapid movement of funds through multiple accounts to obscure origin
3. ROUND-TRIPPING: Funds exported and re-imported to appear legitimate
4. WATCHLIST HITS: Customer names matching OFAC, UN, or RBI AML watchlists
5. VELOCITY ANOMALIES: Sudden spike in transaction frequency or amount

INSTRUCTIONS:
1. Assign a FRAUD_SCORE from 0 (clean) to 100 (confirmed fraud pattern).
2. Identify all detected fraud patterns with evidence.
3. List any watchlist hits with matched entity names.
4. List structuring alerts with transaction clusters.
5. Cite the EXACT regulatory clause for every finding.
6. Recommend STR filing if score ≥ 70.

OUTPUT FORMAT (use these exact labels):
FRAUD_SCORE: <integer 0-100>
PATTERNS_DETECTED:
- <pattern 1>: <brief description>
WATCHLIST_HITS:
- <entity name> | <list name> | <match confidence>
STRUCTURING_ALERTS:
- <customer_id> | <txn count> | <total amount> | <date range>
RECOMMENDATIONS:
- <action 1>
- <action 2>
CITATIONS:
- <doc_name> | Section <section_number>: <brief snippet>
SUMMARY:
<2-3 sentence narrative>
"""


class FraudDetectionAgent(BaseAgent):
    """
    Agent responsible for AML / CFT fraud detection using rule-based
    pre-scoring combined with LLM narrative analysis.

    Detection pipeline:
    1. Rule-based: watchlist joins, structuring detection, velocity checks
    2. LLM-assisted: pattern narrative, regulatory citations
    3. Alerting: Slack alert per transaction breaching FRAUD_ALERT_THRESHOLD
    """

    # ------------------------------------------------------------------ #
    #  Main entry point                                                    #
    # ------------------------------------------------------------------ #

    def run(self, query: str, user_role: str, rag_results: list) -> dict:
        """
        Execute the fraud detection workflow.

        Steps:
        1. Detect watchlist hits via KYC / AML_WATCHLIST join.
        2. Detect structuring patterns.
        3. Fetch flagged transactions from TRANSACTIONS.
        4. Build enriched prompt with all signals + RAG context.
        5. Call LLM for narrative analysis.
        6. Parse structured response.
        7. Send Slack alerts for individual transactions exceeding threshold.
        8. Return standardised output dict.

        Parameters
        ----------
        query : str
            The user's fraud-related question or instruction.
        user_role : str
            User's access role.
        rag_results : list[dict]
            Pre-fetched regulatory document chunks.

        Returns
        -------
        dict
            Standard agent output contract.
        """
        logger.info("[FraudDetectionAgent] Starting fraud detection for query: %s", query[:80])

        try:
            # 1. Detect watchlist hits
            watchlist_hits = self.detect_watchlist_hits(customer_ids=[])

            # 2. Detect structuring patterns
            structuring_alerts = self.detect_structuring(days=7)

            # 3. Fetch flagged transactions
            flagged_txns = self._fetch_flagged_transactions()

            # 4. Build enriched prompt
            signals_text = self._format_signals(
                watchlist_hits, structuring_alerts, flagged_txns
            )
            enriched_query = (
                f"{query}\n\n"
                f"=== DETECTED FRAUD SIGNALS ===\n"
                f"{signals_text}"
            )
            prompt = self._build_prompt(_SYSTEM_PROMPT, enriched_query, rag_results)

            # 5. Call LLM
            raw_response = self._call_llm(prompt)

            if raw_response.startswith("ERROR:"):
                return self._empty_response(raw_response)

            # 6. Parse response
            fraud_score = self._parse_risk_score(raw_response)
            patterns = self._parse_list_section(raw_response, "PATTERNS_DETECTED")
            wl_hits_parsed = self._parse_list_section(raw_response, "WATCHLIST_HITS")
            struct_alerts_parsed = self._parse_list_section(raw_response, "STRUCTURING_ALERTS")
            recommendations = self._parse_list_section(raw_response, "RECOMMENDATIONS")
            summary = self._parse_field(raw_response, "SUMMARY") or (
                f"Fraud analysis complete. Overall fraud score: {fraud_score}/100. "
                f"{len(watchlist_hits)} watchlist hits, "
                f"{len(structuring_alerts)} structuring alerts detected."
            )

            citations = self._extract_citations(rag_results)

            # Enrich flagged_txns with rule-based pre-scores
            enriched_flags = self._enrich_flagged_items(
                flagged_txns, watchlist_hits, structuring_alerts
            )

            result: dict = {
                "agent": self.agent_name,
                "summary": summary,
                "risk_score": fraud_score,
                "flagged_items": enriched_flags,
                "citations": citations,
                "recommendations": recommendations,
                "raw_llm_response": raw_response,
                "error": None,
                # Agent-specific extras
                "patterns_detected": patterns,
                "watchlist_hits": watchlist_hits,
                "structuring_alerts": structuring_alerts,
                "wl_hits_parsed": wl_hits_parsed,
                "struct_alerts_parsed": struct_alerts_parsed,
            }

            # 7. Send per-transaction Slack alerts
            self._send_alerts_for_flagged(enriched_flags, fraud_score)

            logger.info(
                "[FraudDetectionAgent] Completed. Fraud score=%d %s",
                fraud_score,
                format_risk_badge(fraud_score),
            )
            return result

        except Exception as exc:  # pylint: disable=broad-except
            logger.error("[FraudDetectionAgent] Unexpected error: %s", exc, exc_info=True)
            return self._empty_response(str(exc))

    # ------------------------------------------------------------------ #
    #  Watchlist detection                                                 #
    # ------------------------------------------------------------------ #

    def detect_watchlist_hits(self, customer_ids: list) -> list:
        """
        Join KYC_PROFILES with AML_WATCHLIST on approximate name similarity
        to surface potential sanctions / watchlist matches.

        Uses SOUNDEX-based similarity when supported; falls back to substring
        match.  Returns mock data when no Snowpark session is available.

        Parameters
        ----------
        customer_ids : list[str]
            Subset of customer IDs to check.  Pass an empty list to check all
            customers with recent activity.

        Returns
        -------
        list[dict]
            Each dict: {customer_id, kyc_name, watchlist_name, list_name,
            match_score, matched_at}.
        """
        if self.session is not None:
            try:
                id_filter = (
                    f"AND k.CUSTOMER_ID IN ({', '.join(repr(c) for c in customer_ids)})"
                    if customer_ids
                    else ""
                )
                sql = f"""
                SELECT
                    k.CUSTOMER_ID,
                    k.FULL_NAME                AS kyc_name,
                    w.ENTITY_NAME              AS watchlist_name,
                    w.LIST_NAME                AS list_name,
                    JAROWINKLER_SIMILARITY(
                        UPPER(k.FULL_NAME),
                        UPPER(w.ENTITY_NAME)
                    )                          AS match_score,
                    CURRENT_TIMESTAMP()        AS matched_at
                FROM KYC_PROFILES k
                JOIN AML_WATCHLIST w
                    ON JAROWINKLER_SIMILARITY(
                        UPPER(k.FULL_NAME),
                        UPPER(w.ENTITY_NAME)
                    ) >= 85
                WHERE k.KYC_STATUS = 'ACTIVE'
                  {id_filter}
                ORDER BY match_score DESC
                LIMIT 50
                """
                rows = self.session.sql(sql).collect()
                return [
                    {
                        "customer_id": r["CUSTOMER_ID"],
                        "kyc_name": r["KYC_NAME"],
                        "watchlist_name": r["WATCHLIST_NAME"],
                        "list_name": r["LIST_NAME"],
                        "match_score": float(r["MATCH_SCORE"]),
                        "matched_at": str(r["MATCHED_AT"]),
                    }
                    for r in rows
                ]
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "[FraudDetectionAgent] Watchlist SQL failed, using mock data: %s", exc
                )

        # ---- Mock data ----
        logger.info("[FraudDetectionAgent] Using mock watchlist hits (local mode).")
        return [
            {
                "customer_id": "CUST_MOCK_001",
                "kyc_name": "Rahul Sharma",
                "watchlist_name": "Rahul Sharma",
                "list_name": "RBI_AML_WATCHLIST",
                "match_score": 94.5,
                "matched_at": "2026-10-05T10:00:00Z",
            }
        ]

    # ------------------------------------------------------------------ #
    #  Structuring detection                                               #
    # ------------------------------------------------------------------ #

    def detect_structuring(self, customer_id: str = None, days: int = 7) -> list:
        """
        Identify customers performing multiple transactions just below the
        ₹10,00,000 RBI Cash Transaction Report (CTR) threshold — a classic
        structuring / smurfing pattern.

        Detection window: transactions between ₹8,00,000 and ₹10,00,000
        (configurable via _STRUCTURING_LOWER_INR / _STRUCTURING_UPPER_INR).

        Parameters
        ----------
        customer_id : str, optional
            Limit detection to a single customer.  None = all customers.
        days : int
            Rolling window in days (default 7).

        Returns
        -------
        list[dict]
            Each dict: {customer_id, txn_count, total_amount_inr,
            min_date, max_date, structuring_score}.
        """
        if self.session is not None:
            try:
                cust_filter = (
                    f"AND CUSTOMER_ID = '{customer_id}'" if customer_id else ""
                )
                sql = f"""
                SELECT
                    CUSTOMER_ID,
                    COUNT(*)           AS txn_count,
                    SUM(AMOUNT)        AS total_amount_inr,
                    MIN(CREATED_AT)    AS min_date,
                    MAX(CREATED_AT)    AS max_date
                FROM TRANSACTIONS
                WHERE AMOUNT BETWEEN {_STRUCTURING_LOWER_INR} AND {_STRUCTURING_UPPER_INR}
                  AND CREATED_AT >= DATEADD('day', -{days}, CURRENT_TIMESTAMP())
                  {cust_filter}
                GROUP BY CUSTOMER_ID
                HAVING COUNT(*) >= 2
                ORDER BY txn_count DESC
                LIMIT 100
                """
                rows = self.session.sql(sql).collect()
                return [
                    {
                        "customer_id": r["CUSTOMER_ID"],
                        "txn_count": int(r["TXN_COUNT"]),
                        "total_amount_inr": float(r["TOTAL_AMOUNT_INR"]),
                        "min_date": str(r["MIN_DATE"]),
                        "max_date": str(r["MAX_DATE"]),
                        "structuring_score": min(
                            100, int(r["TXN_COUNT"]) * 20
                        ),  # higher count → higher suspicion
                    }
                    for r in rows
                ]
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "[FraudDetectionAgent] Structuring SQL failed, using mock: %s", exc
                )

        # ---- Mock data ----
        logger.info("[FraudDetectionAgent] Using mock structuring data (local mode).")
        return [
            {
                "customer_id": "CUST_MOCK_042",
                "txn_count": 4,
                "total_amount_inr": 3_840_000.0,
                "min_date": "2026-09-29",
                "max_date": "2026-10-05",
                "structuring_score": 80,
            }
        ]

    # ------------------------------------------------------------------ #
    #  Rule-based pre-scoring                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def calculate_fraud_score(
        txn: dict,
        watchlist_hit: bool,
        is_structuring: bool,
    ) -> int:
        """
        Compute a rule-based fraud pre-score before LLM analysis.

        Scoring breakdown:
        - Base score: txn['risk_score'] (or 30 as default)
        - Watchlist hit:   +30 points
        - Structuring:     +25 points
        - International:   +15 points (TXN_TYPE == 'INTERNATIONAL')
        - Capped at 100

        Parameters
        ----------
        txn : dict
            Transaction dict with at least 'risk_score' and 'txn_type'.
        watchlist_hit : bool
            True if the customer appears on an AML watchlist.
        is_structuring : bool
            True if the customer has structuring pattern detected.

        Returns
        -------
        int
            Rule-based fraud score in range 0–100.
        """
        base = int(txn.get("risk_score", 30))
        score = base
        if watchlist_hit:
            score += 30
        if is_structuring:
            score += 25
        if str(txn.get("txn_type", "")).upper() == "INTERNATIONAL":
            score += 15
        return min(100, score)

    # ------------------------------------------------------------------ #
    #  Private helpers                                                     #
    # ------------------------------------------------------------------ #

    def _fetch_flagged_transactions(self) -> list:
        """
        Retrieve recently flagged transactions from TRANSACTIONS table.

        Returns mock data if no session is available.

        Returns
        -------
        list[dict]
            Each dict represents a flagged transaction row.
        """
        if self.session is not None:
            try:
                sql = f"""
                SELECT
                    TXN_ID,
                    CUSTOMER_ID,
                    AMOUNT,
                    CURRENCY,
                    TXN_TYPE,
                    RISK_SCORE,
                    FLAG_REASON,
                    CREATED_AT
                FROM TRANSACTIONS
                WHERE IS_FLAGGED = TRUE
                  AND CREATED_AT >= DATEADD('day', -7, CURRENT_TIMESTAMP())
                ORDER BY RISK_SCORE DESC
                LIMIT 50
                """
                rows = self.session.sql(sql).collect()
                return [
                    {
                        "txn_id": r["TXN_ID"],
                        "customer_id": r["CUSTOMER_ID"],
                        "amount": float(r["AMOUNT"]),
                        "currency": r["CURRENCY"],
                        "txn_type": r["TXN_TYPE"],
                        "risk_score": int(r["RISK_SCORE"] or 0),
                        "flag_reason": r["FLAG_REASON"],
                        "created_at": str(r["CREATED_AT"]),
                    }
                    for r in rows
                ]
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "[FraudDetectionAgent] Flagged txn SQL failed, using mock: %s", exc
                )

        # ---- Mock data ----
        return [
            {
                "txn_id": "TXN_MOCK_9001",
                "customer_id": "CUST_MOCK_042",
                "amount": 960_000.0,
                "currency": "INR",
                "txn_type": "DOMESTIC",
                "risk_score": 78,
                "flag_reason": "Near-threshold structuring",
                "created_at": "2026-10-04T14:22:00Z",
            },
            {
                "txn_id": "TXN_MOCK_9002",
                "customer_id": "CUST_MOCK_001",
                "amount": 5_200_000.0,
                "currency": "INR",
                "txn_type": "INTERNATIONAL",
                "risk_score": 85,
                "flag_reason": "Watchlist match + large international transfer",
                "created_at": "2026-10-05T08:11:00Z",
            },
        ]

    def _enrich_flagged_items(
        self,
        flagged_txns: list,
        watchlist_hits: list,
        structuring_alerts: list,
    ) -> list:
        """
        Enrich flagged transactions with rule-based fraud pre-scores.

        Parameters
        ----------
        flagged_txns : list[dict]
            Raw flagged transaction rows.
        watchlist_hits : list[dict]
            Watchlist hit records.
        structuring_alerts : list[dict]
            Structuring pattern records.

        Returns
        -------
        list[dict]
            Enriched flagged items with 'fraud_score' and 'signals' fields.
        """
        wl_customers = {h["customer_id"] for h in watchlist_hits}
        struct_customers = {s["customer_id"] for s in structuring_alerts}

        enriched = []
        for txn in flagged_txns:
            cid = txn.get("customer_id", "")
            wl_hit = cid in wl_customers
            is_struct = cid in struct_customers
            fraud_score = self.calculate_fraud_score(txn, wl_hit, is_struct)

            signals = []
            if wl_hit:
                signals.append("WATCHLIST_HIT")
            if is_struct:
                signals.append("STRUCTURING")
            if str(txn.get("txn_type", "")).upper() == "INTERNATIONAL":
                signals.append("INTERNATIONAL")

            enriched.append(
                {
                    **txn,
                    "fraud_score": fraud_score,
                    "signals": signals,
                    "amount_display": format_inr(txn.get("amount", 0)),
                }
            )
        return enriched

    def _send_alerts_for_flagged(self, enriched_flags: list, overall_score: int) -> None:
        """
        Send a Slack fraud alert for every transaction whose fraud_score
        meets or exceeds FRAUD_ALERT_THRESHOLD.

        Parameters
        ----------
        enriched_flags : list[dict]
            Enriched flagged transaction dicts with 'fraud_score'.
        overall_score : int
            Overall agent fraud score (included in alert metadata).
        """
        for item in enriched_flags:
            item_score = item.get("fraud_score", 0)
            if item_score >= config.FRAUD_ALERT_THRESHOLD:
                try:
                    alerter.send_fraud_alert(
                        txn_id=item.get("txn_id", "UNKNOWN"),
                        customer_id=item.get("customer_id", "UNKNOWN"),
                        amount=item.get("amount", 0),
                        fraud_score=item_score,
                        signals=item.get("signals", []),
                        flag_reason=item.get("flag_reason", ""),
                    )
                    logger.info(
                        "[FraudDetectionAgent] Slack alert sent for txn %s (score=%d)",
                        item.get("txn_id"),
                        item_score,
                    )
                except Exception as exc:  # pylint: disable=broad-except
                    logger.error(
                        "[FraudDetectionAgent] Slack alert failed for txn %s: %s",
                        item.get("txn_id"),
                        exc,
                    )

    @staticmethod
    def _format_signals(
        watchlist_hits: list,
        structuring_alerts: list,
        flagged_txns: list,
    ) -> str:
        """Format detected fraud signals into readable prompt text."""
        lines: list[str] = []

        lines.append(f"Watchlist Hits ({len(watchlist_hits)}):")
        for h in watchlist_hits:
            lines.append(
                f"  - Customer {h['customer_id']} "
                f"matched '{h['watchlist_name']}' on {h['list_name']} "
                f"(score: {h['match_score']:.1f})"
            )

        lines.append(f"\nStructuring Alerts ({len(structuring_alerts)}):")
        for s in structuring_alerts:
            lines.append(
                f"  - Customer {s['customer_id']}: {s['txn_count']} transactions "
                f"totalling {format_inr(s['total_amount_inr'])} "
                f"({s['min_date']} to {s['max_date']})"
            )

        lines.append(f"\nFlagged Transactions ({len(flagged_txns)}):")
        for t in flagged_txns:
            lines.append(
                f"  - TXN {t['txn_id']}: {format_inr(t['amount'])} | "
                f"Type: {t.get('txn_type')} | "
                f"Risk: {t.get('risk_score')} | "
                f"Reason: {t.get('flag_reason', 'N/A')}"
            )

        return "\n".join(lines)

    @staticmethod
    def _parse_list_section(text: str, label: str) -> list:
        """
        Extract a bullet-list section from LLM output.

        Parameters
        ----------
        text : str
            Raw LLM response.
        label : str
            Section heading label.

        Returns
        -------
        list[str]
            Items extracted from the section, stripped of bullet markers.
        """
        pattern = rf"{re.escape(label)}\s*:\s*\n((?:\s*[-•*]\s*.+\n?)+)"
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return []
        raw_block = match.group(1)
        return [
            re.sub(r"^\s*[-•*]\s*", "", line).strip()
            for line in raw_block.splitlines()
            if line.strip() and re.match(r"^\s*[-•*]", line)
        ]

    @staticmethod
    def _parse_field(text: str, label: str) -> str:
        """
        Extract a single-value or multi-line field from LLM output.

        Parameters
        ----------
        text : str
            Raw LLM response.
        label : str
            Field label.

        Returns
        -------
        str
            Extracted value, or empty string if not found.
        """
        single = re.search(
            rf"^{re.escape(label)}\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE
        )
        if single:
            return single.group(1).strip()

        multi = re.search(
            rf"{re.escape(label)}\s*:\s*\n([\s\S]+?)(?:\n[A-Z_]{{3,}}:|\Z)",
            text,
            re.IGNORECASE,
        )
        if multi:
            return multi.group(1).strip()

        return ""
