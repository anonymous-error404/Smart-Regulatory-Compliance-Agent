"""
src/agents/risk_agent.py
------------------------
Basel III / IV Risk Assessment Agent for Auris.

Analyses transactions for liquidity risk (LCR, NSFR), credit risk, and
market risk against RBI-mandated thresholds.  Triggers Slack alerts when
overall risk score breaches the HIGH_RISK_THRESHOLD.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any

from src.agents.base_agent import BaseAgent
from src.alerts.slack_alerts import alerter
from src.utils.formatters import format_inr, format_risk_badge

import config

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
#  System prompt                                                       #
# ------------------------------------------------------------------ #

_SYSTEM_PROMPT = """You are an expert Basel III/IV risk assessment specialist for Indian banking, with deep knowledge of RBI (Reserve Bank of India) prudential regulations.

Your task is to analyse the provided transaction data and regulatory context, then produce a structured risk assessment.

REGULATORY FRAMEWORK:
- Basel III/IV: CRR, LCR ≥ 100%, NSFR ≥ 100%, Leverage Ratio ≥ 3%, Capital Adequacy Ratio (CAR) ≥ 11.5% for Indian banks
- RBI Master Directions on Liquidity Risk Management
- RBI guidelines on Credit Risk and Market Risk under ICAAP
- RBI Large Exposure Framework (LEF)

INSTRUCTIONS:
1. Analyse transactions for liquidity risk, credit risk, and market risk.
2. Compute an overall risk score from 0 (no risk) to 100 (critical risk).
3. Compare LCR and NSFR against RBI-mandated 100% minimum.
4. Cite the EXACT regulatory clause, section number, and document name for every finding.
5. Identify breaches and recommend remediation actions.
6. Do NOT speculate beyond the provided data.

OUTPUT FORMAT (use these exact labels):
RISK_SCORE: <integer 0-100>
LCR_STATUS: <COMPLIANT|BREACH|UNKNOWN> | LCR: <value>%
NSFR_STATUS: <COMPLIANT|BREACH|UNKNOWN> | NSFR: <value>%
RISK_FACTORS:
- <factor 1>
- <factor 2>
RECOMMENDATIONS:
- <action 1>
- <action 2>
CITATIONS:
- <doc_name> | Section <section_number>: <brief snippet>
SUMMARY:
<2-3 sentence narrative>
"""


class RiskAssessmentAgent(BaseAgent):
    """
    Agent responsible for Basel III/IV liquidity, credit, and market risk
    assessment of banking transactions.

    Uses Snowflake TRANSACTIONS table (live) or mock data (local dev) to
    gather transaction statistics before invoking the LLM.
    """

    # ------------------------------------------------------------------ #
    #  Main entry point                                                    #
    # ------------------------------------------------------------------ #

    def run(self, query: str, user_role: str, rag_results: list) -> dict:
        """
        Execute the risk assessment workflow.

        Steps:
        1. Fetch transaction statistics from Snowflake (or mock).
        2. Build an enriched prompt combining stats, RAG context, and query.
        3. Call the LLM.
        4. Parse the structured response.
        5. Trigger a Slack alert if risk_score >= HIGH_RISK_THRESHOLD.
        6. Return the standardised output dict.

        Parameters
        ----------
        query : str
            The user's risk-related question or instruction.
        user_role : str
            User's access role (determines data visibility).
        rag_results : list[dict]
            Pre-fetched regulatory document chunks.

        Returns
        -------
        dict
            Standard agent output contract.
        """
        logger.info("[RiskAssessmentAgent] Starting risk assessment for query: %s", query[:80])

        try:
            # 1. Fetch transaction statistics
            txn_stats = self.get_transaction_stats(days=7)
            txn_summary_text = self._format_txn_stats(txn_stats)

            # 2. Build prompt
            enriched_query = (
                f"{query}\n\n"
                f"=== TRANSACTION STATISTICS (LAST 7 DAYS) ===\n"
                f"{txn_summary_text}"
            )
            prompt = self._build_prompt(_SYSTEM_PROMPT, enriched_query, rag_results)

            # 3. Call LLM
            raw_response = self._call_llm(prompt)

            # Check for LLM error
            if raw_response.startswith("ERROR:"):
                return self._empty_response(raw_response)

            # 4. Parse structured response
            risk_score = self._parse_risk_score(raw_response)
            risk_factors = self._parse_list_section(raw_response, "RISK_FACTORS")
            recommendations = self._parse_list_section(raw_response, "RECOMMENDATIONS")
            lcr_status = self._parse_field(raw_response, "LCR_STATUS")
            nsfr_status = self._parse_field(raw_response, "NSFR_STATUS")
            summary = self._parse_field(raw_response, "SUMMARY") or (
                f"Risk assessment complete. Overall risk score: {risk_score}/100. "
                f"LCR: {lcr_status}. NSFR: {nsfr_status}."
            )

            citations = self._extract_citations(rag_results)

            # Build flagged items from high-value / high-risk transactions
            flagged_items = self._flag_high_risk_txns(txn_stats)

            result: dict = {
                "agent": self.agent_name,
                "summary": summary,
                "risk_score": risk_score,
                "flagged_items": flagged_items,
                "citations": citations,
                "recommendations": recommendations,
                "raw_llm_response": raw_response,
                "error": None,
                # Agent-specific extras
                "lcr_status": lcr_status,
                "nsfr_status": nsfr_status,
                "risk_factors": risk_factors,
                "txn_stats": txn_stats,
            }

            # 5. Trigger Slack alert if risk is high
            if risk_score >= config.HIGH_RISK_THRESHOLD:
                logger.warning(
                    "[RiskAssessmentAgent] High risk detected (score=%d). Sending Slack alert.",
                    risk_score,
                )
                try:
                    alerter.send_daily_summary(
                        summary_data={
                            "agent": self.agent_name,
                            "risk_score": risk_score,
                            "summary": summary,
                            "flagged_items": flagged_items,
                            "lcr_status": lcr_status,
                            "nsfr_status": nsfr_status,
                        }
                    )
                except Exception as alert_exc:  # pylint: disable=broad-except
                    logger.error("Slack alert failed: %s", alert_exc)

            logger.info(
                "[RiskAssessmentAgent] Completed. Risk score=%d %s",
                risk_score,
                format_risk_badge(risk_score),
            )
            return result

        except Exception as exc:  # pylint: disable=broad-except
            logger.error("[RiskAssessmentAgent] Unexpected error: %s", exc, exc_info=True)
            return self._empty_response(str(exc))

    # ------------------------------------------------------------------ #
    #  Transaction statistics                                              #
    # ------------------------------------------------------------------ #

    def get_transaction_stats(self, days: int = 7) -> dict:
        """
        Query the TRANSACTIONS table for aggregate statistics over the
        last *days* calendar days.

        Falls back to mock statistics when no Snowpark session is available.

        Parameters
        ----------
        days : int
            Lookback window in days (default 7).

        Returns
        -------
        dict
            Keys: total_count, total_amount_inr, flagged_count,
            avg_risk_score, high_risk_count, international_count,
            period_days.
        """
        if self.session is not None:
            try:
                sql = f"""
                SELECT
                    COUNT(*)                                   AS total_count,
                    SUM(AMOUNT)                                AS total_amount_inr,
                    SUM(CASE WHEN IS_FLAGGED = TRUE THEN 1 ELSE 0 END)
                                                               AS flagged_count,
                    AVG(RISK_SCORE)                            AS avg_risk_score,
                    SUM(CASE WHEN RISK_SCORE >= {config.HIGH_RISK_THRESHOLD} THEN 1 ELSE 0 END)
                                                               AS high_risk_count,
                    SUM(CASE WHEN TXN_TYPE = 'INTERNATIONAL' THEN 1 ELSE 0 END)
                                                               AS international_count
                FROM TRANSACTIONS
                WHERE CREATED_AT >= DATEADD('day', -{days}, CURRENT_TIMESTAMP())
                """
                rows = self.session.sql(sql).collect()
                if rows:
                    row = rows[0]
                    return {
                        "total_count": int(row["TOTAL_COUNT"] or 0),
                        "total_amount_inr": float(row["TOTAL_AMOUNT_INR"] or 0),
                        "flagged_count": int(row["FLAGGED_COUNT"] or 0),
                        "avg_risk_score": float(row["AVG_RISK_SCORE"] or 0),
                        "high_risk_count": int(row["HIGH_RISK_COUNT"] or 0),
                        "international_count": int(row["INTERNATIONAL_COUNT"] or 0),
                        "period_days": days,
                    }
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "[RiskAssessmentAgent] SQL query failed, using mock data: %s", exc
                )

        # ---- Mock data (local dev / no session) ----
        logger.info("[RiskAssessmentAgent] Using mock transaction stats (local mode).")
        return {
            "total_count": 1_243,
            "total_amount_inr": 4_875_620_000.0,  # ~₹487.5 Cr
            "flagged_count": 18,
            "avg_risk_score": 42.7,
            "high_risk_count": 5,
            "international_count": 87,
            "period_days": days,
        }

    # ------------------------------------------------------------------ #
    #  Liquidity risk scoring                                              #
    # ------------------------------------------------------------------ #

    def score_liquidity_risk(self, lcr: float, nsfr: float) -> dict:
        """
        Compute a liquidity risk score and status based on Basel III LCR
        and NSFR ratios.

        Basel III / RBI minimum for both LCR and NSFR is **100%**.

        Parameters
        ----------
        lcr : float
            Liquidity Coverage Ratio as a percentage (e.g. 110.5).
        nsfr : float
            Net Stable Funding Ratio as a percentage (e.g. 105.0).

        Returns
        -------
        dict
            Keys: score (int 0-100), status (str), lcr_breach (bool),
            nsfr_breach (bool), lcr_value (float), nsfr_value (float).
        """
        LCR_MINIMUM = 100.0   # RBI / Basel III minimum
        NSFR_MINIMUM = 100.0  # RBI / Basel III minimum

        lcr_breach = lcr < LCR_MINIMUM
        nsfr_breach = nsfr < NSFR_MINIMUM

        # Compute partial scores — the further below the minimum, the worse
        lcr_deficit = max(0.0, LCR_MINIMUM - lcr)
        nsfr_deficit = max(0.0, NSFR_MINIMUM - nsfr)

        # Each percentage point of deficit contributes ~2 risk points
        lcr_score_contrib = min(50, int(lcr_deficit * 2))
        nsfr_score_contrib = min(50, int(nsfr_deficit * 2))
        score = min(100, lcr_score_contrib + nsfr_score_contrib)

        if not lcr_breach and not nsfr_breach:
            status = "COMPLIANT"
        elif lcr_breach and nsfr_breach:
            status = "DUAL_BREACH"
        elif lcr_breach:
            status = "LCR_BREACH"
        else:
            status = "NSFR_BREACH"

        return {
            "score": score,
            "status": status,
            "lcr_breach": lcr_breach,
            "nsfr_breach": nsfr_breach,
            "lcr_value": lcr,
            "nsfr_value": nsfr,
        }

    # ------------------------------------------------------------------ #
    #  Private helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _format_txn_stats(stats: dict) -> str:
        """Format transaction stats dict into a readable string for the prompt."""
        return (
            f"- Period: Last {stats.get('period_days', 7)} days\n"
            f"- Total Transactions: {stats.get('total_count', 0):,}\n"
            f"- Total Volume: {format_inr(stats.get('total_amount_inr', 0))}\n"
            f"- Flagged Transactions: {stats.get('flagged_count', 0)}\n"
            f"- High-Risk Transactions (score≥{config.HIGH_RISK_THRESHOLD}): "
            f"{stats.get('high_risk_count', 0)}\n"
            f"- Average Risk Score: {stats.get('avg_risk_score', 0):.1f}/100\n"
            f"- International Transactions: {stats.get('international_count', 0)}\n"
        )

    @staticmethod
    def _flag_high_risk_txns(stats: dict) -> list:
        """
        Build a minimal list of flagged-item dicts from aggregate stats.

        In live mode the orchestrator or UI layer would expand this with
        individual transaction rows; here we surface the aggregate counts.
        """
        flagged: list[dict] = []
        if stats.get("flagged_count", 0) > 0:
            flagged.append(
                {
                    "type": "aggregate_flag",
                    "description": (
                        f"{stats['flagged_count']} transactions flagged in last "
                        f"{stats.get('period_days', 7)} days"
                    ),
                    "amount_inr": None,
                    "risk_score": stats.get("avg_risk_score"),
                }
            )
        if stats.get("high_risk_count", 0) > 0:
            flagged.append(
                {
                    "type": "high_risk_aggregate",
                    "description": (
                        f"{stats['high_risk_count']} transactions with "
                        f"risk score ≥ {config.HIGH_RISK_THRESHOLD}"
                    ),
                    "amount_inr": None,
                    "risk_score": 100,  # worst-case sentinel for aggregate
                }
            )
        return flagged

    @staticmethod
    def _parse_list_section(text: str, label: str) -> list:
        """
        Extract a bullet-list section from LLM output.

        Parameters
        ----------
        text : str
            Raw LLM response.
        label : str
            Section heading label (e.g. 'RISK_FACTORS').

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
        items = [
            re.sub(r"^\s*[-•*]\s*", "", line).strip()
            for line in raw_block.splitlines()
            if line.strip() and re.match(r"^\s*[-•*]", line)
        ]
        return items

    @staticmethod
    def _parse_field(text: str, label: str) -> str:
        """
        Extract a single-value field from LLM output (e.g. ``LCR_STATUS: COMPLIANT``).

        For multi-line fields (e.g. SUMMARY), captures until the next all-caps label
        or end of string.

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
        # Try single-line match first
        single = re.search(
            rf"^{re.escape(label)}\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE
        )
        if single:
            return single.group(1).strip()

        # Multi-line block (e.g. SUMMARY)
        multi = re.search(
            rf"{re.escape(label)}\s*:\s*\n([\s\S]+?)(?:\n[A-Z_]{{3,}}:|\Z)",
            text,
            re.IGNORECASE,
        )
        if multi:
            return multi.group(1).strip()

        return ""
