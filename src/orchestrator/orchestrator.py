"""
src/orchestrator/orchestrator.py
---------------------------------
Auris Central Orchestrator.

Routes user queries to the appropriate agent(s), merges their outputs into
a unified response, writes to the audit trail, and returns a single dict
ready for the Streamlit UI or API layer.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from src.agents.risk_agent import RiskAssessmentAgent
from src.agents.fraud_agent import FraudDetectionAgent
from src.agents.regulatory_agent import RegulatoryReportAgent
from src.mock_cortex import CortexClient
from src.utils.formatters import build_audit_record

import config

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
#  Routing keyword maps                                                #
# ------------------------------------------------------------------ #

_RISK_KEYWORDS = frozenset(
    ["risk", "lcr", "nsfr", "liquidity", "credit", "basel", "capital",
     "leverage", "car", "npa", "exposure", "nsfr", "icaap", "stress"]
)

_FRAUD_KEYWORDS = frozenset(
    ["fraud", "aml", "structuring", "watchlist", "suspicious", "flag",
     "sanction", "smurfing", "layering", "round-trip", "cft", "str",
     "sar", "pmla", "kyc", "money laundering"]
)

_REGULATORY_KEYWORDS = frozenset(
    ["regulation", "rbi", "circular", "report", "filing", "deadline",
     "policy", "guideline", "sebi", "fatf", "compliance", "disclosure",
     "pillar", "master direction", "act", "section", "clause", "schedule"]
)

_AGENT_RISK = "RiskAssessmentAgent"
_AGENT_FRAUD = "FraudDetectionAgent"
_AGENT_REGULATORY = "RegulatoryReportAgent"


class AurisOrchestrator:
    """
    Central orchestrator for the Auris multi-agent system.

    Responsibilities:
    - Keyword-based query routing to one or more agents
    - Parallel (sequential) agent invocation
    - Result merging: deduplication of citations, union of flagged items
    - Audit trail persistence
    - Unified response packaging for the UI / API layer
    """

    # ------------------------------------------------------------------ #
    #  Construction                                                        #
    # ------------------------------------------------------------------ #

    def __init__(self, session=None) -> None:
        """
        Initialise the orchestrator and all three agents.

        Parameters
        ----------
        session : snowflake.snowpark.Session, optional
            Active Snowpark session passed down to every agent and used for
            audit-trail writes.  When None, all agents operate in local mode.
        """
        self.session: Any = session

        # Instantiate agents
        self.risk_agent = RiskAssessmentAgent(session=session)
        self.fraud_agent = FraudDetectionAgent(session=session)
        self.regulatory_agent = RegulatoryReportAgent(session=session)

        # CortexClient for fallback RAG search in local mode
        self._cortex = CortexClient(session=session)

        logger.info("[Orchestrator] Initialised. Session=%s", "live" if session else "local")

    # ------------------------------------------------------------------ #
    #  Query routing                                                       #
    # ------------------------------------------------------------------ #

    def route(self, query: str) -> list:
        """
        Determine which agents should handle the query based on keyword
        matching against the lowercased query string.

        Routing rules:
        - Any risk keyword       → RiskAssessmentAgent
        - Any fraud keyword      → FraudDetectionAgent
        - Any regulatory keyword → RegulatoryReportAgent
        - No keyword match       → all three agents

        Parameters
        ----------
        query : str
            The user's natural-language question or instruction.

        Returns
        -------
        list[str]
            Ordered list of agent name strings.  May contain one, two, or
            all three agent names.
        """
        q_lower = query.lower()
        tokens = set(q_lower.split())

        # Check multi-word keywords via substring match on full query
        selected: list[str] = []

        if tokens & _RISK_KEYWORDS or any(kw in q_lower for kw in _RISK_KEYWORDS):
            selected.append(_AGENT_RISK)

        if tokens & _FRAUD_KEYWORDS or any(kw in q_lower for kw in _FRAUD_KEYWORDS):
            selected.append(_AGENT_FRAUD)

        if tokens & _REGULATORY_KEYWORDS or any(kw in q_lower for kw in _REGULATORY_KEYWORDS):
            selected.append(_AGENT_REGULATORY)

        # Default: invoke all agents when no keywords match
        if not selected:
            selected = [_AGENT_RISK, _AGENT_FRAUD, _AGENT_REGULATORY]
            logger.info(
                "[Orchestrator] No keyword match for query '%s…' — invoking all agents.",
                query[:60],
            )
        else:
            logger.info(
                "[Orchestrator] Routing query '%s…' → %s",
                query[:60],
                selected,
            )

        return selected

    # ------------------------------------------------------------------ #
    #  Main entry point                                                    #
    # ------------------------------------------------------------------ #

    def run(
        self,
        query: str,
        user_identity: dict,
        rag_results: list = None,
    ) -> dict:
        """
        Execute the full Auris pipeline for a user query.

        Steps:
        1. Resolve RAG results (use provided or fetch via CortexClient).
        2. Route query to the appropriate agent(s).
        3. Invoke each selected agent.
        4. Merge all agent outputs.
        5. Persist merged result to the audit trail.
        6. Return the unified response dict.

        Parameters
        ----------
        query : str
            The user's natural-language question or command.
        user_identity : dict
            Must contain keys: user_id, username, role.
        rag_results : list[dict], optional
            Pre-fetched RAG chunks from the RAG pipeline.  When None, the
            orchestrator calls CortexClient.search() as a local fallback.

        Returns
        -------
        dict
            Unified response::

                {
                    'query':             str,
                    'user':              dict,
                    'agents_invoked':    list[str],
                    'overall_risk_score': int | None,
                    'summary':           str,
                    'flagged_items':     list,
                    'citations':         list,
                    'recommendations':   list,
                    'per_agent_results': dict,   # keyed by agent name
                    'timestamp':         str,    # ISO 8601 UTC
                    'error':             str | None,
                }
        """
        user_id: str = user_identity.get("user_id", "anonymous")
        user_role: str = user_identity.get("role", "analyst")
        username: str = user_identity.get("username", user_id)

        logger.info(
            "[Orchestrator] Processing query for user='%s' role='%s': %s",
            username,
            user_role,
            query[:80],
        )

        # 1. Resolve RAG results
        if rag_results is None:
            logger.info("[Orchestrator] No RAG results provided — using CortexClient.search().")
            try:
                rag_results = self._cortex.search(
                    query=query,
                    user_role=user_role,
                    categories=[],
                )
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "[Orchestrator] CortexClient.search() failed: %s. Proceeding without RAG.",
                    exc,
                )
                rag_results = []

        # 2. Route
        agents_to_invoke = self.route(query)

        # 3. Invoke each agent
        per_agent_results: dict = {}
        agent_outputs: list[dict] = []

        agent_map = {
            _AGENT_RISK: self.risk_agent,
            _AGENT_FRAUD: self.fraud_agent,
            _AGENT_REGULATORY: self.regulatory_agent,
        }

        for agent_name in agents_to_invoke:
            agent = agent_map[agent_name]
            logger.info("[Orchestrator] Invoking %s …", agent_name)
            try:
                result = agent.run(
                    query=query,
                    user_role=user_role,
                    rag_results=rag_results,
                )
            except Exception as exc:  # pylint: disable=broad-except
                logger.error(
                    "[Orchestrator] Agent %s raised an unhandled exception: %s",
                    agent_name,
                    exc,
                    exc_info=True,
                )
                result = {
                    "agent": agent_name,
                    "summary": f"Agent failed with unhandled error: {exc}",
                    "risk_score": None,
                    "flagged_items": [],
                    "citations": [],
                    "recommendations": [],
                    "raw_llm_response": "",
                    "error": str(exc),
                }

            per_agent_results[agent_name] = result
            agent_outputs.append(result)

        # 4. Merge results
        merged = self._merge_results(agent_outputs)

        # 5. Build unified response
        timestamp = datetime.now(tz=timezone.utc).isoformat()
        unified: dict = {
            "query": query,
            "user": {
                "user_id": user_id,
                "username": username,
                "role": user_role,
            },
            "agents_invoked": agents_to_invoke,
            "overall_risk_score": merged["overall_risk_score"],
            "summary": merged["summary"],
            "flagged_items": merged["flagged_items"],
            "citations": merged["citations"],
            "recommendations": merged["recommendations"],
            "per_agent_results": per_agent_results,
            "timestamp": timestamp,
            "error": merged.get("error"),
        }

        # 6. Save to audit trail
        self._save_orchestrator_audit(user_id, query, unified)

        logger.info(
            "[Orchestrator] Completed. Agents=%s, overall_risk=%s",
            agents_to_invoke,
            merged["overall_risk_score"],
        )
        return unified

    # ------------------------------------------------------------------ #
    #  Result merging                                                      #
    # ------------------------------------------------------------------ #

    def _merge_results(self, results: list) -> dict:
        """
        Merge the outputs of multiple agents into a single unified dict.

        Merging strategy:
        - overall_risk_score: max of all non-None risk_score values
        - flagged_items: union across all agents
        - citations: deduplicated by (doc_name, section) tuple
        - recommendations: concatenated list (deduplicated)
        - summary: concatenated agent summaries
        - error: first non-None error encountered

        Parameters
        ----------
        results : list[dict]
            List of standard agent output dicts.

        Returns
        -------
        dict
            Merged dict with keys: overall_risk_score, summary,
            flagged_items, citations, recommendations, error.
        """
        if not results:
            return {
                "overall_risk_score": None,
                "summary": "No agents were invoked.",
                "flagged_items": [],
                "citations": [],
                "recommendations": [],
                "error": "No agent results to merge.",
            }

        # Collect scores (exclude None)
        scores = [r["risk_score"] for r in results if r.get("risk_score") is not None]
        overall_risk_score = max(scores) if scores else None

        # Union of flagged items
        all_flagged: list[dict] = []
        for r in results:
            all_flagged.extend(r.get("flagged_items", []))

        # Deduplicated citations by (doc_name, section)
        seen_citations: set = set()
        deduplicated_citations: list[dict] = []
        for r in results:
            for cit in r.get("citations", []):
                key = (cit.get("doc_name", ""), cit.get("section", ""))
                if key not in seen_citations:
                    seen_citations.add(key)
                    deduplicated_citations.append(cit)

        # Deduplicated recommendations
        seen_recs: set = set()
        all_recommendations: list[str] = []
        for r in results:
            for rec in r.get("recommendations", []):
                rec_stripped = rec.strip()
                if rec_stripped and rec_stripped not in seen_recs:
                    seen_recs.add(rec_stripped)
                    all_recommendations.append(rec_stripped)

        # Combine summaries
        summaries = [
            f"[{r.get('agent', 'Agent')}] {r.get('summary', '')}"
            for r in results
            if r.get("summary")
        ]
        combined_summary = " | ".join(summaries)

        # First error encountered
        first_error = next(
            (r.get("error") for r in results if r.get("error")), None
        )

        return {
            "overall_risk_score": overall_risk_score,
            "summary": combined_summary,
            "flagged_items": all_flagged,
            "citations": deduplicated_citations,
            "recommendations": all_recommendations,
            "error": first_error,
        }

    # ------------------------------------------------------------------ #
    #  Audit trail                                                         #
    # ------------------------------------------------------------------ #

    def _save_orchestrator_audit(
        self,
        user_id: str,
        query: str,
        unified_response: dict,
    ) -> None:
        """
        Persist the orchestrator's unified response to the AUDIT_TRAIL table.

        Delegates to the risk_agent's _save_to_audit_trail helper (which
        already handles both live Snowflake and local-log modes) after
        adapting the unified dict to the standard agent output contract.

        Parameters
        ----------
        user_id : str
            Identifier of the requesting user.
        query : str
            The original user query.
        unified_response : dict
            The fully merged orchestrator response.
        """
        # Adapt unified response to the standard contract shape
        adapted = {
            "agent": "AurisOrchestrator",
            "summary": unified_response.get("summary", ""),
            "risk_score": unified_response.get("overall_risk_score"),
            "flagged_items": unified_response.get("flagged_items", []),
            "citations": unified_response.get("citations", []),
            "recommendations": unified_response.get("recommendations", []),
            "raw_llm_response": "",  # orchestrator itself doesn't call LLM
            "error": unified_response.get("error"),
        }
        try:
            self.risk_agent._save_to_audit_trail(user_id, query, adapted)  # noqa: SLF001
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(
                "[Orchestrator] Failed to save orchestrator audit record: %s", exc
            )


# Backwards compatibility alias
RegIQOrchestrator = AurisOrchestrator
