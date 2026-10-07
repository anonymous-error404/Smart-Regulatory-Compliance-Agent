"""
src/agents/base_agent.py
------------------------
Abstract base class for all Auris AI agents.

Every concrete agent (RiskAssessmentAgent, FraudDetectionAgent,
RegulatoryReportAgent) must inherit from BaseAgent and implement run().
"""

import re
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

# Internal imports
from src.mock_cortex import CortexClient
from src.utils.formatters import build_audit_record

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base class shared by all Auris agents.

    Provides:
    - CortexClient creation for LLM inference and RAG search
    - Prompt assembly helpers
    - Risk-score extraction from free-form LLM text
    - Citation extraction from RAG result dicts
    - Audit-trail persistence (Snowflake if session present, else local log)
    """

    # ------------------------------------------------------------------ #
    #  Construction                                                        #
    # ------------------------------------------------------------------ #

    def __init__(self, session=None) -> None:
        """
        Initialise the agent.

        Parameters
        ----------
        session : snowflake.snowpark.Session, optional
            An active Snowpark session.  When provided, audit records and
            live SQL queries are executed against Snowflake.  When None,
            the agent operates in local/mock mode.
        """
        self.session: Any = session  # Snowpark Session | None
        self.cortex: CortexClient = CortexClient(session=session)
        self.agent_name: str = self.__class__.__name__

    # ------------------------------------------------------------------ #
    #  Abstract interface                                                  #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def run(self, query: str, user_role: str, rag_results: list) -> dict:
        """
        Execute the agent's main logic and return a standardised result dict.

        Parameters
        ----------
        query : str
            The natural-language question or instruction from the user.
        user_role : str
            One of the role strings defined in config.USER_ROLES.
        rag_results : list[dict]
            Pre-fetched regulatory document chunks from the RAG pipeline.
            Each dict contains: doc_name, section_number, section_title,
            content, source_url, relevance_score.

        Returns
        -------
        dict
            Standard output contract::

                {
                    'agent':             str,
                    'summary':           str,
                    'risk_score':        int | None,
                    'flagged_items':     list,
                    'citations':         list,
                    'recommendations':   list,
                    'raw_llm_response':  str,
                    'error':             str | None,
                }
        """

    # ------------------------------------------------------------------ #
    #  LLM call                                                           #
    # ------------------------------------------------------------------ #

    def _call_llm(self, prompt: str) -> str:
        """
        Call CortexClient.complete() with exception handling.

        Parameters
        ----------
        prompt : str
            The fully assembled prompt string.

        Returns
        -------
        str
            The LLM's response, or a formatted error string beginning with
            'ERROR:' if the call fails.
        """
        try:
            response: str = self.cortex.complete(prompt)
            logger.debug("[%s] LLM call succeeded (%d chars)", self.agent_name, len(response))
            return response
        except Exception as exc:  # pylint: disable=broad-except
            error_msg = f"ERROR: LLM call failed in {self.agent_name}: {exc}"
            logger.error(error_msg, exc_info=True)
            return error_msg

    # ------------------------------------------------------------------ #
    #  Prompt assembly                                                     #
    # ------------------------------------------------------------------ #

    def _build_prompt(
        self,
        system_prompt: str,
        user_query: str,
        context_chunks: list,
    ) -> str:
        """
        Assemble a full prompt from a system instruction, RAG chunks, and
        the user's query.

        The resulting prompt follows a structured template so that every
        agent produces consistently formatted LLM inputs.

        Parameters
        ----------
        system_prompt : str
            Role / task instructions for the LLM.
        user_query : str
            The raw user question or command.
        context_chunks : list[dict]
            RAG result dicts (doc_name, section_number, section_title,
            content, source_url, relevance_score).

        Returns
        -------
        str
            The assembled prompt ready to be sent to the LLM.
        """
        # Build the regulatory context section from RAG chunks
        context_lines: list[str] = []
        for idx, chunk in enumerate(context_chunks, start=1):
            doc_name = chunk.get("doc_name", "Unknown Document")
            section_number = chunk.get("section_number", "N/A")
            section_title = chunk.get("section_title", "")
            content = chunk.get("content", "")
            relevance = chunk.get("relevance_score", 0.0)

            context_lines.append(
                f"[{idx}] Document: {doc_name} | "
                f"Section {section_number}: {section_title} "
                f"(relevance: {relevance:.2f})\n"
                f"{content}"
            )

        context_block = (
            "\n\n---\n".join(context_lines)
            if context_lines
            else "No regulatory context available."
        )

        prompt = (
            f"SYSTEM INSTRUCTIONS:\n{system_prompt}\n\n"
            f"=== REGULATORY CONTEXT (RAG RESULTS) ===\n"
            f"{context_block}\n\n"
            f"=== USER QUERY ===\n"
            f"{user_query}\n\n"
            f"=== YOUR RESPONSE ==="
        )
        return prompt

    # ------------------------------------------------------------------ #
    #  Risk-score extraction                                              #
    # ------------------------------------------------------------------ #

    def _parse_risk_score(self, llm_response: str) -> int:
        """
        Extract an integer risk score (0–100) from free-form LLM output.

        Attempts to locate a pattern such as ``RISK_SCORE: 72`` or
        ``FRAUD_SCORE: 85`` in the response text.  Falls back to 50 if
        no valid integer is found.

        Parameters
        ----------
        llm_response : str
            Raw text returned by the LLM.

        Returns
        -------
        int
            Extracted risk score in the range 0–100, or 50 on failure.
        """
        # Match patterns like RISK_SCORE: 72, FRAUD_SCORE:85, score: 43
        patterns = [
            r"(?:RISK_SCORE|FRAUD_SCORE|OVERALL_SCORE|SCORE)\s*[:\-=]\s*(\d{1,3})",
            r"\bscore[:\s]+(\d{1,3})\b",
            r"(\d{1,3})\s*/\s*100",  # e.g. "72/100"
        ]
        for pattern in patterns:
            match = re.search(pattern, llm_response, re.IGNORECASE)
            if match:
                value = int(match.group(1))
                if 0 <= value <= 100:
                    logger.debug("[%s] Parsed risk score: %d", self.agent_name, value)
                    return value

        logger.warning(
            "[%s] Could not parse risk score from LLM response; defaulting to 50.",
            self.agent_name,
        )
        return 50  # safe default

    # ------------------------------------------------------------------ #
    #  Citation extraction                                                 #
    # ------------------------------------------------------------------ #

    def _extract_citations(self, rag_results: list) -> list:
        """
        Convert raw RAG result dicts into the standard citation format.

        Parameters
        ----------
        rag_results : list[dict]
            Items from the RAG pipeline, each containing doc_name,
            section_number, section_title, content, source_url.

        Returns
        -------
        list[dict]
            List of citation dicts::

                {
                    'doc_name':  str,
                    'section':   str,
                    'snippet':   str,   # first 200 chars of content
                    'source_url': str,
                }
        """
        citations: list[dict] = []
        for chunk in rag_results:
            content: str = chunk.get("content", "")
            snippet = content[:200] + ("…" if len(content) > 200 else "")
            citations.append(
                {
                    "doc_name": chunk.get("doc_name", "Unknown"),
                    "section": (
                        f"§{chunk.get('section_number', 'N/A')} "
                        f"{chunk.get('section_title', '')}".strip()
                    ),
                    "snippet": snippet,
                    "source_url": chunk.get("source_url", ""),
                }
            )
        return citations

    # ------------------------------------------------------------------ #
    #  Audit trail                                                         #
    # ------------------------------------------------------------------ #

    def _save_to_audit_trail(
        self,
        user_id: str,
        query: str,
        response: dict,
    ) -> None:
        """
        Persist an audit record to Snowflake (AUDIT_TRAIL table) when a
        session is available; otherwise log locally.

        Parameters
        ----------
        user_id : str
            Identifier of the user who issued the query.
        query : str
            The original user query.
        response : dict
            The standardised agent output dict.
        """
        record = build_audit_record(
            user_id=user_id,
            agent=self.agent_name,
            query=query,
            response=response,
        )

        if self.session is not None:
            try:
                # Upsert into AUDIT_TRAIL via Snowpark execute
                risk_score = response.get("risk_score")
                risk_score_sql = str(risk_score) if risk_score is not None else "NULL"
                summary_escaped = (response.get("summary", "") or "").replace("'", "''")
                query_escaped = (query or "").replace("'", "''")
                record_json = json.dumps(record).replace("'", "''")

                citations_json = json.dumps(response.get("citations", [])).replace("'", "''")
                sql = (
                    "INSERT INTO AUDIT_TRAIL "
                    "(AUDIT_ID, USER_ID, QUERY_TEXT, AGENT_ROUTED_TO, RESPONSE_SUMMARY, "
                    "RISK_SCORE_RETURNED, REGULATORY_CITATIONS, QUERY_TIMESTAMP, SESSION_ID) "
                    f"SELECT '{record['audit_id']}', '{user_id}', '{query_escaped}', '{self.agent_name}', "
                    f"'{summary_escaped}', {risk_score_sql}, PARSE_JSON('{citations_json}'), CURRENT_TIMESTAMP(), '{record.get('session_id', '')}'"
                )
                self.session.sql(sql).collect()
                logger.info(
                    "[%s] Audit record %s saved to Snowflake.",
                    self.agent_name,
                    record["audit_id"],
                )
            except Exception as exc:  # pylint: disable=broad-except
                logger.error(
                    "[%s] Failed to save audit record to Snowflake: %s",
                    self.agent_name,
                    exc,
                    exc_info=True,
                )
        else:
            logger.info(
                "[%s] (local mode) Audit record: %s",
                self.agent_name,
                json.dumps(record, indent=2),
            )

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _empty_response(self, error_message: str) -> dict:
        """
        Return a well-formed but empty agent output dict with an error set.

        Parameters
        ----------
        error_message : str
            Human-readable description of what went wrong.

        Returns
        -------
        dict
            Standard output contract with all list fields empty and
            risk_score set to None.
        """
        return {
            "agent": self.agent_name,
            "summary": f"Agent failed: {error_message}",
            "risk_score": None,
            "flagged_items": [],
            "citations": [],
            "recommendations": [],
            "raw_llm_response": "",
            "error": error_message,
        }
