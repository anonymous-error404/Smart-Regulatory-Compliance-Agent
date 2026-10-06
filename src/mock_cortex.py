"""
mock_cortex.py
==============
Local-development mock for Snowflake Cortex AI functions.

When ``config.ENV == 'local'`` the application uses this module instead of
calling real Snowflake Cortex endpoints, so developers can iterate quickly
without burning credits.

Public API
----------
- ``Complete(model, prompt)``       — mock COMPLETE() function
- ``mock_rag_search(query, ...)``   — mock Cortex Search results
- ``CortexClient``                  — auto-selects real vs mock based on ENV

Colour codes (ANSI dim) are used for log lines so they do not distract in a
coloured terminal but remain visible in plain logs.
"""

from __future__ import annotations

import json
import random
import sys
import os
import logging
from typing import Any

# ---------------------------------------------------------------------------
# Ensure project root is importable
# ---------------------------------------------------------------------------
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config  # noqa: E402

logger = logging.getLogger(__name__)

# ANSI dim/reset for log decoration
_DIM = "\033[2m"
_RESET = "\033[0m"


def _log_mock(tag: str, msg: str) -> None:
    """Print a dim-styled mock log line to stdout."""
    print(f"{_DIM}[{tag}] {msg}{_RESET}")


# ---------------------------------------------------------------------------
# Realistic mock response corpus
# ---------------------------------------------------------------------------

_MOCK_RISK_RESPONSES: list[dict] = [
    {
        "risk_score": 78,
        "risk_level": "HIGH",
        "primary_drivers": [
            "Transaction amount exceeds ₹10,00,000 threshold",
            "Counterparty located in FATF grey-listed jurisdiction",
            "Velocity anomaly: 4 transactions in 2 hours",
        ],
        "regulatory_flags": ["RBI Master Direction – KYC 2016, Section 12(iii)", "PMLA 2002, Section 3"],
        "recommendation": "Escalate to compliance officer for enhanced due diligence (EDD).",
    },
    {
        "risk_score": 42,
        "risk_level": "MEDIUM",
        "primary_drivers": [
            "Cash deposit above ₹50,000 without PAN",
            "Customer risk profile: MEDIUM",
        ],
        "regulatory_flags": ["RBI Circular RBI/2015-16/42, Paragraph 4.2"],
        "recommendation": "Request PAN / Form 60 before completing the transaction.",
    },
    {
        "risk_score": 15,
        "risk_level": "LOW",
        "primary_drivers": ["Normal transaction pattern", "Verified KYC on record"],
        "regulatory_flags": [],
        "recommendation": "No action required. Log for audit trail.",
    },
]

_MOCK_FRAUD_RESPONSES: list[dict] = [
    {
        "fraud_probability": 0.87,
        "fraud_score": 87,
        "detected_patterns": [
            "Structuring: 5 transactions of ₹9,80,000 in 6 hours (just below ₹10L threshold)",
            "Unusual beneficiary: first-time payee with offshore account",
        ],
        "similar_cases": ["CASE-2024-0042", "CASE-2024-0119"],
        "action": "BLOCK_AND_ALERT",
    },
    {
        "fraud_probability": 0.54,
        "fraud_score": 54,
        "detected_patterns": ["Mule account indicators", "Geographic mismatch"],
        "similar_cases": [],
        "action": "MANUAL_REVIEW",
    },
]

_MOCK_REGULATORY_RESPONSES: list[dict] = [
    {
        "query_understood": "KYC requirements for large cash transactions",
        "citations": [
            {
                "regulation": "RBI Master Direction – Know Your Customer (KYC) Direction, 2016",
                "section": "Section 12(iii)",
                "text": (
                    "Regulated entities shall carry out enhanced due diligence for "
                    "cash transactions of ₹10 lakh and above or its equivalent in "
                    "foreign currency."
                ),
                "url": "https://rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=11566",
            },
            {
                "regulation": "Prevention of Money Laundering Act, 2002",
                "section": "Section 3",
                "text": (
                    "Whosoever directly or indirectly attempts to indulge or "
                    "knowingly assists or is a party to concealment of proceeds "
                    "of crime is guilty of the offence of money laundering."
                ),
                "url": "https://enforcementdirectorate.gov.in/pmla",
            },
        ],
        "plain_summary": (
            "For cash transactions ≥ ₹10 lakh, the bank must complete Enhanced Due "
            "Diligence (EDD), file a Suspicious Transaction Report (STR) with FIU-IND "
            "within 7 working days, and retain records for 10 years under PMLA."
        ),
    },
    {
        "query_understood": "Basel III capital adequacy for Indian banks",
        "citations": [
            {
                "regulation": "RBI Master Circular – Basel III Capital Regulations, 2015",
                "section": "Section 3.1",
                "text": (
                    "Banks are required to maintain a minimum Total Capital Ratio "
                    "(TCR) of 11.5% of Risk Weighted Assets (RWAs) on an ongoing "
                    "basis, including Capital Conservation Buffer (CCB) of 2.5%."
                ),
                "url": "https://rbi.org.in/Scripts/BS_ViewMasCirculardetails.aspx?id=9859",
            }
        ],
        "plain_summary": (
            "Indian banks must maintain CET1 ≥ 5.5%, Tier-1 ≥ 7%, and Total Capital "
            "≥ 11.5% of RWA under the RBI's Basel III framework (includes CCB)."
        ),
    },
]

_MOCK_GENERIC_RESPONSE = {
    "answer": (
        "Based on the available regulatory corpus, the query relates to standard "
        "compliance obligations under Indian financial regulations. Please refine "
        "your query for a more targeted analysis."
    ),
    "confidence": "MEDIUM",
    "suggested_follow_up": [
        "Specify the regulation name (e.g., RBI, SEBI, IRDAI)",
        "Include transaction type or customer segment",
    ],
}


# ---------------------------------------------------------------------------
# Module-level mock functions (mirror Snowflake Cortex built-ins)
# ---------------------------------------------------------------------------


def Complete(model: str, prompt: str) -> str:  # noqa: N802  (mirrors Cortex naming)
    """Mock Snowflake Cortex ``COMPLETE()`` function.

    Selects a realistic canned response based on keywords in *prompt* and
    returns it as a JSON string, mirroring what the real Cortex endpoint
    returns.

    Parameters
    ----------
    model:
        Cortex model name (e.g. ``'snowflake-arctic-instruct'``).  Ignored in
        the mock but logged for traceability.
    prompt:
        The prompt text sent to the model.

    Returns
    -------
    str
        A JSON-formatted string with a realistic mock response.
    """
    _log_mock("MOCK CORTEX", f"Complete called with model={model!r}, prompt_len={len(prompt)}")

    prompt_lower = prompt.lower()

    if "risk" in prompt_lower:
        payload = random.choice(_MOCK_RISK_RESPONSES)
    elif "fraud" in prompt_lower:
        payload = random.choice(_MOCK_FRAUD_RESPONSES)
    elif any(kw in prompt_lower for kw in ("regulatory", "rbi", "basel", "kyc", "pmla", "aml")):
        payload = random.choice(_MOCK_REGULATORY_RESPONSES)
    else:
        payload = _MOCK_GENERIC_RESPONSE

    return json.dumps(payload, ensure_ascii=False, indent=2)


def mock_rag_search(
    query: str,
    user_role: str,
    doc_categories: list[str],
) -> list[dict]:
    """Mock Cortex Search / RAG retrieval.

    Returns three realistic document chunks that look as if they were
    retrieved from the ``AURIS_REGULATORY_SEARCH`` Cortex Search Service.

    Parameters
    ----------
    query:
        The user's natural-language search query.
    user_role:
        The requesting user's role (logged only; no actual filtering in mock).
    doc_categories:
        Document categories the user is allowed to access (logged only).

    Returns
    -------
    list[dict]
        A list of up to 3 mock document-chunk dicts, each with keys:
        ``doc_name``, ``section_number``, ``section_title``, ``content``,
        ``source_url``, ``relevance_score``.
    """
    _log_mock(
        "MOCK RAG",
        f"Search called for role={user_role!r}, categories={doc_categories}, query={query!r}",
    )

    _corpus: list[dict] = [
        {
            "doc_name": "RBI Master Direction – Know Your Customer (KYC) Direction, 2016",
            "section_number": "12(iii)",
            "section_title": "Enhanced Due Diligence for High-Value Transactions",
            "content": (
                "Regulated Entities (REs) shall carry out customer due diligence (CDD) "
                "measures at enhanced levels where the transaction or a series of "
                "transactions involves cash of ₹10 lakh and above, or its equivalent "
                "in foreign currency. Enhanced due diligence includes obtaining the "
                "source of funds, purpose of transaction, and beneficial ownership "
                "declarations. Documentary evidence must be retained for a minimum of "
                "five years from the date of cessation of the business relationship."
            ),
            "source_url": "https://rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=11566",
            "relevance_score": round(random.uniform(0.88, 0.97), 4),
        },
        {
            "doc_name": "Prevention of Money Laundering (Maintenance of Records) Rules, 2005",
            "section_number": "3(1)(A)",
            "section_title": "Cash Transaction Reports – Obligation to Report",
            "content": (
                "Every reporting entity shall furnish to the Director, Financial "
                "Intelligence Unit – India (FIU-IND), a report of all cash transactions "
                "of the value of more than ten lakh rupees or its equivalent in foreign "
                "currency. Such report shall be submitted within seven working days from "
                "the date of the transaction. Failure to report constitutes an offence "
                "attracting penalties under Section 13 of the PMLA, 2002."
            ),
            "source_url": "https://fiuindia.gov.in/files/PMLRules2005.pdf",
            "relevance_score": round(random.uniform(0.80, 0.90), 4),
        },
        {
            "doc_name": "RBI Master Circular – Basel III Capital Regulations, July 2015",
            "section_number": "3.1",
            "section_title": "Minimum Capital Requirements",
            "content": (
                "With effect from 31 March 2019, banks are required to maintain a "
                "minimum Total Capital Ratio (TCR) of 11.5% of Risk Weighted Assets "
                "(RWAs). This includes a Common Equity Tier 1 (CET1) ratio of at "
                "least 5.5%, a minimum Tier 1 capital ratio of 7% and a Capital "
                "Conservation Buffer (CCB) of 2.5%. Banks that do not maintain the "
                "CCB will face restrictions on dividend distribution and discretionary "
                "bonus payments."
            ),
            "source_url": "https://rbi.org.in/Scripts/BS_ViewMasCirculardetails.aspx?id=9859",
            "relevance_score": round(random.uniform(0.72, 0.85), 4),
        },
        {
            "doc_name": "SEBI (Prohibition of Insider Trading) Regulations, 2015",
            "section_number": "4(1)",
            "section_title": "Trading when in possession of UPSI",
            "content": (
                "No insider shall trade in securities that are listed or proposed to "
                "be listed on a stock exchange when in possession of unpublished "
                "price sensitive information (UPSI). UPSI includes financial results, "
                "dividends, change in key management, mergers, material events and "
                "decisions of the board with respect to buying back of securities."
            ),
            "source_url": "https://www.sebi.gov.in/legal/regulations/jan-2015/sebi-prohibition-of-insider-trading-regulations-2015_27299.html",
            "relevance_score": round(random.uniform(0.65, 0.79), 4),
        },
        {
            "doc_name": "RBI Circular – Frauds Classification and Reporting, 2016",
            "section_number": "2.3",
            "section_title": "Reporting of Frauds to RBI",
            "content": (
                "Banks shall report all cases of fraud of ₹1 lakh and above to "
                "the Regional Office of Reserve Bank of India under whose jurisdiction "
                "the Head Office of the bank falls. Reports should be submitted within "
                "three weeks from the date of detection of the fraud. For frauds "
                "involving ₹100 crore and above, Flash Report must be submitted to "
                "DBS, CO, Mumbai immediately."
            ),
            "source_url": "https://rbi.org.in/Scripts/NotificationUser.aspx?Id=10476",
            "relevance_score": round(random.uniform(0.60, 0.75), 4),
        },
    ]

    # Return top-3 by relevance, shuffled to simulate search variability
    chunks = random.sample(_corpus, k=min(3, len(_corpus)))
    chunks.sort(key=lambda x: x["relevance_score"], reverse=True)
    return chunks


# ---------------------------------------------------------------------------
# CortexClient — auto-selects real vs mock
# ---------------------------------------------------------------------------


class CortexClient:
    """Unified interface to Snowflake Cortex AI functions.

    Automatically routes calls to the real Snowflake Cortex functions when
    ``config.ENV == 'snowflake'``, or to the local mock implementations when
    ``config.ENV == 'local'``.

    Now integrates with :class:`~src.rag.rag_pipeline.RAGPipeline` for
    permission-aware, reranked document retrieval.

    Examples
    --------
    >>> client = CortexClient()
    >>> response = client.complete("What are the KYC requirements?")
    >>> chunks   = client.rag_search("AML thresholds", "junior_analyst", ["KYC"])
    """

    def __init__(self, session: Any = None) -> None:
        self.session = session
        self._env: str = getattr(config, "ENV", "local")
        self._model: str = getattr(config, "CORTEX_MODEL", "snowflake-arctic-instruct")
        self._search_service: str = getattr(config, "CORTEX_SEARCH_SERVICE", "AURIS_REGULATORY_SEARCH")

        # Initialise the permission-aware RAG pipeline
        try:
            from src.rag.rag_pipeline import RAGPipeline  # noqa: PLC0415
            self._rag_pipeline = RAGPipeline(session=session, top_k=5)
            logger.info("[CortexClient] RAG pipeline initialised.")
        except Exception as exc:  # noqa: BLE001
            self._rag_pipeline = None
            logger.warning("[CortexClient] RAG pipeline unavailable: %s", exc)

        if self._env == "snowflake":
            # Attempt to import real Cortex; fall back to mock on failure
            try:
                from snowflake.cortex import Complete as _RealComplete  # type: ignore[import]
                self._complete_fn = _RealComplete
                logger.info("[CortexClient] Using REAL Snowflake Cortex (model=%s).", self._model)
            except ImportError:
                logger.warning(
                    "[CortexClient] snowflake.cortex not available; falling back to mock."
                )
                self._complete_fn = Complete  # type: ignore[assignment]
        else:
            self._complete_fn = Complete  # type: ignore[assignment]
            logger.info("[CortexClient] ENV=local — using MOCK Cortex.")

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def complete(self, prompt: str, model: str | None = None) -> str:
        """Call Cortex COMPLETE (real or mock).

        Parameters
        ----------
        prompt:
            The full prompt string.
        model:
            Override the default Cortex model.  Uses ``config.CORTEX_MODEL``
            when not specified.

        Returns
        -------
        str
            Raw text / JSON response from the model.
        """
        _model = model or self._model
        return self._complete_fn(_model, prompt)

    def rag_search(
        self,
        query: str,
        user_role: str = "junior_analyst",
        doc_categories: list[str] | None = None,
        categories: list[str] | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Perform a permission-aware RAG search over the regulatory corpus.

        Delegates to :class:`~src.rag.rag_pipeline.RAGPipeline` which handles
        permission pre-filtering, BM25/Cortex retrieval, and reranking.
        Falls back to the legacy ``mock_rag_search()`` if the pipeline is
        unavailable.
        """
        resolved_categories = categories or doc_categories or []

        # Primary path: use the new permission-aware RAG pipeline
        if self._rag_pipeline is not None:
            try:
                return self._rag_pipeline.search(
                    query=query,
                    user_role=user_role,
                    categories=resolved_categories or None,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[CortexClient] RAG pipeline search failed: %s. Falling back.", exc
                )

        # Fallback: legacy mock search
        return mock_rag_search(query, user_role, resolved_categories)

    # Convenience alias
    search = rag_search



# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

cortex_client = CortexClient()
