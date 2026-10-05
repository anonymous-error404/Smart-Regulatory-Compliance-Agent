"""
src/agents/regulatory_agent.py
-------------------------------
Regulatory Report & Compliance Q&A Agent for Auris.

Grounds all answers strictly in provided RAG document chunks and always
cites the exact section number and document name.  Also generates
AML summary reports and Basel Pillar 3 disclosure summaries.
"""

import logging
import re
from typing import Any

from src.agents.base_agent import BaseAgent
from src.utils.formatters import format_inr, format_regulatory_citation

import config

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
#  System prompt                                                       #
# ------------------------------------------------------------------ #

_SYSTEM_PROMPT = """You are an expert regulatory compliance officer specialising in Indian banking regulations. Your knowledge spans RBI, SEBI, Basel III/IV, FATF, and Indian financial law.

STRICT RULES:
1. Answer ONLY based on the provided regulatory document chunks.
2. ALWAYS cite the exact section number and document name for EVERY claim.
3. If no relevant chunk is provided, explicitly state: "No relevant regulatory document found for this query."
4. Never speculate or answer from general knowledge alone.
5. Structure your answer clearly with headers.

REGULATORY FRAMEWORK COVERAGE:
- RBI Master Circulars and Master Directions
- Basel III/IV Capital, Liquidity, and Leverage requirements
- PMLA 2002 and RBI AML/CFT guidelines
- SEBI regulations (where applicable)
- FATF 40 Recommendations
- RBI Prompt Corrective Action (PCA) Framework

OUTPUT FORMAT (use these exact labels):
ANSWER:
<detailed, structured answer with inline citations [doc_name § section]>

CITATIONS:
- <doc_name> | Section <section_number>: <snippet>

REGULATORY_REFERENCES:
- <full formal reference string>

CONFIDENCE: <HIGH|MEDIUM|LOW>

NEXT_ACTIONS:
- <recommended action 1>
- <recommended action 2>

SUMMARY:
<1-2 sentence plain-English summary>
"""

# ------------------------------------------------------------------ #
#  AML report prompt                                                   #
# ------------------------------------------------------------------ #

_AML_REPORT_PROMPT = """You are an AML compliance officer preparing a formal AML Summary Report for Indian banking regulators.

Generate a comprehensive AML Summary Report for the specified period using the provided transaction statistics and regulatory context.

The report must include:
1. Executive Summary
2. Transaction Volume Analysis
3. Suspicious Activity Overview (SAR/STR summary)
4. High-Risk Customer Segments
5. Regulatory Compliance Status (PMLA, RBI AML guidelines)
6. Recommended Remediation Actions
7. Certification statement

Always cite applicable regulatory sections.

OUTPUT FORMAT:
AML_REPORT_TITLE: AML Summary Report — <period_start> to <period_end>
EXECUTIVE_SUMMARY:
<text>
TRANSACTION_ANALYSIS:
<text>
SUSPICIOUS_ACTIVITY:
<text>
COMPLIANCE_STATUS: <COMPLIANT|PARTIALLY_COMPLIANT|NON_COMPLIANT>
RECOMMENDATIONS:
- <action>
CITATIONS:
- <doc> | Section <sec>: <snippet>
SUMMARY:
<1-2 sentences>
"""

# ------------------------------------------------------------------ #
#  Basel Pillar 3 prompt                                               #
# ------------------------------------------------------------------ #

_BASEL_DISCLOSURE_PROMPT = """You are a Basel III Pillar 3 disclosure specialist for Indian banking.

Generate a Pillar 3 Market Discipline disclosure summary based on the provided regulatory context.

The disclosure must cover:
1. Capital Adequacy (CET1, Tier 1, Total Capital Ratio vs RBI minimums)
2. Liquidity Risk (LCR, NSFR status)
3. Credit Risk Exposure Summary
4. Market Risk Overview
5. Leverage Ratio
6. Qualitative disclosures on risk governance

Always cite the exact Basel III/IV document section and RBI circular.

OUTPUT FORMAT:
PILLAR3_TITLE: Basel III Pillar 3 Market Discipline Disclosure
CAPITAL_ADEQUACY:
<text>
LIQUIDITY_RISK:
<text>
CREDIT_RISK:
<text>
MARKET_RISK:
<text>
LEVERAGE:
<text>
RISK_GOVERNANCE:
<text>
COMPLIANCE_STATUS: <COMPLIANT|PARTIALLY_COMPLIANT|NON_COMPLIANT>
CITATIONS:
- <doc> | Section <sec>: <snippet>
SUMMARY:
<1-2 sentences>
"""


class RegulatoryReportAgent(BaseAgent):
    """
    Agent responsible for:
    - Regulatory Q&A grounded in RAG document chunks
    - AML Summary Report generation
    - Basel III Pillar 3 Disclosure generation

    All responses are citation-backed; the agent explicitly acknowledges
    when no relevant regulatory context is available.
    """

    # ------------------------------------------------------------------ #
    #  Main entry point                                                    #
    # ------------------------------------------------------------------ #

    def run(self, query: str, user_role: str, rag_results: list) -> dict:
        """
        Execute the regulatory Q&A workflow.

        If no RAG results are provided, returns an error response explaining
        that no relevant documents were found for the user's access level.

        Parameters
        ----------
        query : str
            The user's regulatory question.
        user_role : str
            User's access role (determines which documents are visible).
        rag_results : list[dict]
            Pre-fetched regulatory document chunks.

        Returns
        -------
        dict
            Standard agent output contract.  risk_score is None for pure
            Q&A responses (it is not applicable).
        """
        logger.info(
            "[RegulatoryReportAgent] Starting regulatory Q&A for query: %s", query[:80]
        )

        # Guard: no RAG context available
        if not rag_results:
            error_msg = (
                "No regulatory documents found for your query with your access level. "
                "Please refine your search terms or contact your compliance administrator."
            )
            logger.warning("[RegulatoryReportAgent] No RAG results for role='%s'.", user_role)
            return self._empty_response(error_msg)

        try:
            # Build prompt
            prompt = self._build_prompt(_SYSTEM_PROMPT, query, rag_results)

            # Call LLM
            raw_response = self._call_llm(prompt)

            if raw_response.startswith("ERROR:"):
                return self._empty_response(raw_response)

            # Parse response
            answer = self._parse_field(raw_response, "ANSWER")
            confidence = self._parse_field(raw_response, "CONFIDENCE") or "MEDIUM"
            next_actions = self._parse_list_section(raw_response, "NEXT_ACTIONS")
            reg_refs = self._parse_list_section(raw_response, "REGULATORY_REFERENCES")
            summary = self._parse_field(raw_response, "SUMMARY") or (
                f"Regulatory query answered with {confidence} confidence "
                f"based on {len(rag_results)} document chunk(s)."
            )

            citations = self._extract_citations(rag_results)

            result: dict = {
                "agent": self.agent_name,
                "summary": summary,
                "risk_score": None,  # N/A for pure regulatory Q&A
                "flagged_items": [],
                "citations": citations,
                "recommendations": next_actions,
                "raw_llm_response": raw_response,
                "error": None,
                # Agent-specific extras
                "answer": answer,
                "confidence": confidence,
                "regulatory_references": reg_refs,
            }

            logger.info(
                "[RegulatoryReportAgent] Completed. Confidence=%s, citations=%d",
                confidence,
                len(citations),
            )
            return result

        except Exception as exc:  # pylint: disable=broad-except
            logger.error(
                "[RegulatoryReportAgent] Unexpected error: %s", exc, exc_info=True
            )
            return self._empty_response(str(exc))

    # ------------------------------------------------------------------ #
    #  AML Summary Report                                                  #
    # ------------------------------------------------------------------ #

    def generate_aml_summary_report(
        self,
        period_start: str,
        period_end: str,
        user_role: str,
        rag_results: list,
    ) -> dict:
        """
        Generate a comprehensive AML Summary Report for the given period.

        Queries the TRANSACTIONS table for the period statistics, then uses
        the LLM to draft a formal report grounded in the RAG regulatory context.

        Parameters
        ----------
        period_start : str
            Start date in ISO format (e.g. '2026-09-01').
        period_end : str
            End date in ISO format (e.g. '2026-09-30').
        user_role : str
            User's access role.
        rag_results : list[dict]
            Pre-fetched AML-related regulatory document chunks.

        Returns
        -------
        dict
            Extended output dict including:
            report_title, executive_summary, transaction_analysis,
            suspicious_activity, compliance_status, plus standard fields.
        """
        logger.info(
            "[RegulatoryReportAgent] Generating AML report %s → %s",
            period_start,
            period_end,
        )

        # Fetch period transaction stats
        period_stats = self._fetch_period_stats(period_start, period_end)
        stats_text = self._format_period_stats(period_stats, period_start, period_end)

        enriched_query = (
            f"Generate an AML Summary Report for the period {period_start} to {period_end}.\n\n"
            f"=== TRANSACTION STATISTICS ===\n{stats_text}"
        )

        prompt = self._build_prompt(_AML_REPORT_PROMPT, enriched_query, rag_results)
        raw_response = self._call_llm(prompt)

        if raw_response.startswith("ERROR:"):
            return self._empty_response(raw_response)

        report_title = self._parse_field(raw_response, "AML_REPORT_TITLE")
        exec_summary = self._parse_block(raw_response, "EXECUTIVE_SUMMARY")
        txn_analysis = self._parse_block(raw_response, "TRANSACTION_ANALYSIS")
        suspicious = self._parse_block(raw_response, "SUSPICIOUS_ACTIVITY")
        compliance_status = self._parse_field(raw_response, "COMPLIANCE_STATUS") or "UNKNOWN"
        recommendations = self._parse_list_section(raw_response, "RECOMMENDATIONS")
        summary = self._parse_field(raw_response, "SUMMARY") or (
            f"AML Summary Report generated for {period_start} to {period_end}."
        )
        citations = self._extract_citations(rag_results)

        return {
            "agent": self.agent_name,
            "summary": summary,
            "risk_score": None,
            "flagged_items": [],
            "citations": citations,
            "recommendations": recommendations,
            "raw_llm_response": raw_response,
            "error": None,
            # Report-specific extras
            "report_title": report_title,
            "executive_summary": exec_summary,
            "transaction_analysis": txn_analysis,
            "suspicious_activity": suspicious,
            "compliance_status": compliance_status,
            "period_start": period_start,
            "period_end": period_end,
            "period_stats": period_stats,
        }

    # ------------------------------------------------------------------ #
    #  Basel Pillar 3 Disclosure                                           #
    # ------------------------------------------------------------------ #

    def generate_basel_disclosure(
        self,
        user_role: str,
        rag_results: list,
    ) -> dict:
        """
        Generate a Basel III Pillar 3 Market Discipline disclosure summary.

        The disclosure covers capital adequacy, liquidity risk, credit risk,
        market risk, leverage ratio, and risk governance — all grounded in
        the provided RAG chunks.

        Parameters
        ----------
        user_role : str
            User's access role (senior roles see additional Tier 1 data).
        rag_results : list[dict]
            Pre-fetched Basel-related regulatory document chunks.

        Returns
        -------
        dict
            Extended output dict with Pillar 3 sections plus standard fields.
        """
        logger.info("[RegulatoryReportAgent] Generating Basel Pillar 3 disclosure.")

        if not rag_results:
            return self._empty_response(
                "No Basel regulatory documents found for Pillar 3 disclosure generation."
            )

        query = (
            "Generate a Basel III Pillar 3 Market Discipline disclosure summary "
            "for an Indian commercial bank."
        )
        prompt = self._build_prompt(_BASEL_DISCLOSURE_PROMPT, query, rag_results)
        raw_response = self._call_llm(prompt)

        if raw_response.startswith("ERROR:"):
            return self._empty_response(raw_response)

        title = self._parse_field(raw_response, "PILLAR3_TITLE")
        capital = self._parse_block(raw_response, "CAPITAL_ADEQUACY")
        liquidity = self._parse_block(raw_response, "LIQUIDITY_RISK")
        credit = self._parse_block(raw_response, "CREDIT_RISK")
        market = self._parse_block(raw_response, "MARKET_RISK")
        leverage = self._parse_block(raw_response, "LEVERAGE")
        governance = self._parse_block(raw_response, "RISK_GOVERNANCE")
        compliance_status = self._parse_field(raw_response, "COMPLIANCE_STATUS") or "UNKNOWN"
        summary = self._parse_field(raw_response, "SUMMARY") or (
            "Basel III Pillar 3 disclosure generated."
        )
        citations = self._extract_citations(rag_results)

        return {
            "agent": self.agent_name,
            "summary": summary,
            "risk_score": None,
            "flagged_items": [],
            "citations": citations,
            "recommendations": [],
            "raw_llm_response": raw_response,
            "error": None,
            # Disclosure-specific extras
            "disclosure_title": title,
            "capital_adequacy": capital,
            "liquidity_risk": liquidity,
            "credit_risk": credit,
            "market_risk": market,
            "leverage": leverage,
            "risk_governance": governance,
            "compliance_status": compliance_status,
        }

    # ------------------------------------------------------------------ #
    #  Private helpers                                                     #
    # ------------------------------------------------------------------ #

    def _fetch_period_stats(self, period_start: str, period_end: str) -> dict:
        """
        Query TRANSACTIONS table for aggregate statistics in the given period.

        Falls back to mock data when no Snowpark session is available.

        Parameters
        ----------
        period_start : str
            ISO date string for the start of the period.
        period_end : str
            ISO date string for the end of the period.

        Returns
        -------
        dict
            Aggregate stats: total_count, total_amount_inr, flagged_count,
            str_count, high_risk_count, international_count.
        """
        if self.session is not None:
            try:
                sql = f"""
                SELECT
                    COUNT(*)                                      AS total_count,
                    SUM(AMOUNT)                                   AS total_amount_inr,
                    SUM(CASE WHEN IS_FLAGGED = TRUE THEN 1 ELSE 0 END)
                                                                  AS flagged_count,
                    SUM(CASE WHEN STR_FILED = TRUE THEN 1 ELSE 0 END)
                                                                  AS str_count,
                    SUM(CASE WHEN RISK_SCORE >= {config.HIGH_RISK_THRESHOLD} THEN 1 ELSE 0 END)
                                                                  AS high_risk_count,
                    SUM(CASE WHEN TXN_TYPE = 'INTERNATIONAL' THEN 1 ELSE 0 END)
                                                                  AS international_count
                FROM TRANSACTIONS
                WHERE CREATED_AT BETWEEN '{period_start}' AND '{period_end}'
                """
                rows = self.session.sql(sql).collect()
                if rows:
                    r = rows[0]
                    return {
                        "total_count": int(r["TOTAL_COUNT"] or 0),
                        "total_amount_inr": float(r["TOTAL_AMOUNT_INR"] or 0),
                        "flagged_count": int(r["FLAGGED_COUNT"] or 0),
                        "str_count": int(r["STR_COUNT"] or 0),
                        "high_risk_count": int(r["HIGH_RISK_COUNT"] or 0),
                        "international_count": int(r["INTERNATIONAL_COUNT"] or 0),
                    }
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "[RegulatoryReportAgent] Period stats SQL failed, using mock: %s", exc
                )

        # ---- Mock data ----
        logger.info("[RegulatoryReportAgent] Using mock period stats (local mode).")
        return {
            "total_count": 8_542,
            "total_amount_inr": 31_200_000_000.0,
            "flagged_count": 124,
            "str_count": 11,
            "high_risk_count": 38,
            "international_count": 612,
        }

    @staticmethod
    def _format_period_stats(stats: dict, start: str, end: str) -> str:
        """Format period stats for inclusion in the prompt."""
        return (
            f"- Period: {start} to {end}\n"
            f"- Total Transactions: {stats.get('total_count', 0):,}\n"
            f"- Total Volume: {format_inr(stats.get('total_amount_inr', 0))}\n"
            f"- Flagged Transactions: {stats.get('flagged_count', 0)}\n"
            f"- STRs Filed: {stats.get('str_count', 0)}\n"
            f"- High-Risk Transactions: {stats.get('high_risk_count', 0)}\n"
            f"- International Transactions: {stats.get('international_count', 0)}\n"
        )

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
        Extract a single-line or multi-line field from LLM output.

        Parameters
        ----------
        text : str
            Raw LLM response.
        label : str
            Field label.

        Returns
        -------
        str
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

    @staticmethod
    def _parse_block(text: str, label: str) -> str:
        """
        Extract a multi-line block section from LLM output.

        Captures all content between the label and the next all-caps label
        or the end of the string.

        Parameters
        ----------
        text : str
            Raw LLM response.
        label : str
            Section heading label.

        Returns
        -------
        str
            Block content, stripped of leading/trailing whitespace.
        """
        pattern = rf"{re.escape(label)}\s*:\s*\n([\s\S]+?)(?:\n[A-Z_]{{3,}}:|\Z)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""
