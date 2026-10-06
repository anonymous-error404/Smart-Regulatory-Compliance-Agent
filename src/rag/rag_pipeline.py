"""
src/rag/rag_pipeline.py
------------------------
Main RAG (Retrieval-Augmented Generation) pipeline for Auris.

Orchestrates the full permission-aware retrieval flow:

1. **Permission pre-filter** — resolve user role → allowed categories/levels
2. **Retrieval** — Cortex Search (live) or BM25 local search (mock)
3. **Reranking** — multi-signal cross-encoder reranking
4. **Formatting** — normalize output to standard citation-ready dicts

This module is the single entry point that agents and the orchestrator
call for document retrieval.  It replaces the ad-hoc ``mock_rag_search``
call with a proper pipeline.
"""

from __future__ import annotations

import json
import logging
import math
import re
from typing import Any

from src.rag.permission_filter import PermissionFilter
from src.rag.reranker import Reranker

import config

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
#  Expanded local corpus for BM25 search                               #
# ------------------------------------------------------------------ #

_LOCAL_CORPUS: list[dict] = [
    {
        "doc_id": "DOC_001",
        "doc_name": "RBI Master Direction – Know Your Customer (KYC) Direction, 2016",
        "doc_category": "aml_guidelines",
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
        "effective_date": "2016-02-25",
        "permission_level": "junior_analyst",
    },
    {
        "doc_id": "DOC_002",
        "doc_name": "Prevention of Money Laundering (Maintenance of Records) Rules, 2005",
        "doc_category": "aml_guidelines",
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
        "effective_date": "2005-07-01",
        "permission_level": "junior_analyst",
    },
    {
        "doc_id": "DOC_003",
        "doc_name": "RBI Master Circular – Basel III Capital Regulations, July 2015",
        "doc_category": "public_policy",
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
        "effective_date": "2015-07-01",
        "permission_level": "junior_analyst",
    },
    {
        "doc_id": "DOC_004",
        "doc_name": "RBI Master Direction on Liquidity Risk Management, 2012",
        "doc_category": "public_policy",
        "section_number": "4.2",
        "section_title": "Liquidity Coverage Ratio (LCR) Requirements",
        "content": (
            "Banks shall maintain sufficient stock of High Quality Liquid Assets "
            "(HQLA) to cover total net cash outflows over a 30-day stress period. "
            "The minimum LCR requirement is 100%. Level 1 HQLA includes cash, "
            "central bank reserves, and sovereign securities. Level 2A assets "
            "(corporate bonds rated AA- or higher) receive a 15% haircut and can "
            "constitute up to 40% of HQLA. The LCR must be reported monthly to RBI."
        ),
        "source_url": "https://rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=10835",
        "effective_date": "2014-01-01",
        "permission_level": "junior_analyst",
    },
    {
        "doc_id": "DOC_005",
        "doc_name": "RBI Master Direction on Liquidity Risk Management, 2012",
        "doc_category": "public_policy",
        "section_number": "5.1",
        "section_title": "Net Stable Funding Ratio (NSFR) Requirements",
        "content": (
            "Banks shall maintain a minimum Net Stable Funding Ratio (NSFR) of "
            "100% on an ongoing basis. The NSFR measures the proportion of "
            "available stable funding (ASF) to required stable funding (RSF). "
            "Core deposits from retail and small business customers receive "
            "ASF factors of 90-95%. Loans to retail customers with residual "
            "maturity over one year receive RSF factor of 85%. Banks breaching "
            "NSFR must submit a remediation plan within 30 days."
        ),
        "source_url": "https://rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=10835",
        "effective_date": "2018-04-01",
        "permission_level": "junior_analyst",
    },
    {
        "doc_id": "DOC_006",
        "doc_name": "RBI Circular – Frauds Classification and Reporting, 2016",
        "doc_category": "aml_guidelines",
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
        "effective_date": "2016-07-01",
        "permission_level": "junior_analyst",
    },
    {
        "doc_id": "DOC_007",
        "doc_name": "SEBI (Prohibition of Insider Trading) Regulations, 2015",
        "doc_category": "public_policy",
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
        "effective_date": "2015-01-15",
        "permission_level": "junior_analyst",
    },
    {
        "doc_id": "DOC_008",
        "doc_name": "RBI AML/CFT Guidelines for Banks – Internal Risk Assessment",
        "doc_category": "internal_policy",
        "section_number": "6.2",
        "section_title": "Customer Risk Profiling Methodology",
        "content": (
            "Banks shall develop and maintain a comprehensive customer risk "
            "assessment methodology that considers: (a) nature and type of "
            "customer, (b) business relationship and product usage, (c) "
            "geographic risk factors, (d) transaction patterns and volumes, "
            "(e) source of funds and wealth. High-risk customers shall be "
            "subject to enhanced due diligence and monitoring frequency not "
            "less than quarterly. PEP accounts require board-level approval."
        ),
        "source_url": "",
        "effective_date": "2024-01-15",
        "permission_level": "senior_analyst",
    },
    {
        "doc_id": "DOC_009",
        "doc_name": "Internal Policy – Board Risk Committee Report Q3 FY27",
        "doc_category": "risk_reports",
        "section_number": "3.4",
        "section_title": "Credit Risk Exposure Concentrations",
        "content": (
            "The top 20 large exposures account for 34.2% of total credit "
            "exposure, within the RBI Large Exposure Framework (LEF) limit of "
            "25% per counterparty. Infrastructure sector exposure has increased "
            "by 8.3% QoQ to ₹12,450 crore. Three accounts in the watchlist "
            "category have been upgraded following resolution. NPA ratio stands "
            "at 2.1% (gross) and 0.8% (net), within board-approved tolerance "
            "of 3.0% and 1.5% respectively."
        ),
        "source_url": "",
        "effective_date": "2026-09-30",
        "permission_level": "senior_analyst",
    },
    {
        "doc_id": "DOC_010",
        "doc_name": "Internal Policy – KYC PII Data Handling Procedures",
        "doc_category": "kyc_pii",
        "section_number": "2.1",
        "section_title": "PII Data Classification and Access Control",
        "content": (
            "Customer Personally Identifiable Information (PII) including "
            "Aadhaar, PAN, biometric data, and financial records are classified "
            "as CONFIDENTIAL. Access requires compliance_head clearance. All "
            "PII access must be logged in the audit trail with justification. "
            "Data masking must be applied when displaying PII in dashboards or "
            "reports for non-compliance_head roles. Aadhaar numbers must be "
            "stored in SHA-256 hashed form per UIDAI guidelines."
        ),
        "source_url": "",
        "effective_date": "2026-03-01",
        "permission_level": "compliance_head",
    },
    {
        "doc_id": "DOC_011",
        "doc_name": "RBI Master Direction – KYC Direction, 2016 (Updated Feb 2024)",
        "doc_category": "aml_guidelines",
        "section_number": "38(1)",
        "section_title": "Suspicious Transaction Reporting Obligations",
        "content": (
            "A Suspicious Transaction Report (STR) shall be furnished within "
            "7 working days of the transaction being identified as suspicious. "
            "Transactions are suspicious if they: (a) give rise to reasonable "
            "ground of suspicion that they may involve proceeds of an offence, "
            "(b) appear unusual or unjustified, (c) are not commensurate with "
            "the customer's known profile, (d) involve structuring to avoid "
            "reporting thresholds. Tipping off the customer about an STR filing "
            "is a criminal offence under Section 66 of the PMLA."
        ),
        "source_url": "https://rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=11566",
        "effective_date": "2024-02-15",
        "permission_level": "junior_analyst",
    },
    {
        "doc_id": "DOC_012",
        "doc_name": "Basel III Framework – Leverage Ratio (BIS, Jan 2014)",
        "doc_category": "public_policy",
        "section_number": "7.1",
        "section_title": "Minimum Leverage Ratio",
        "content": (
            "Banks must maintain a minimum Leverage Ratio of 3% at all times. "
            "The Leverage Ratio is defined as Tier 1 Capital divided by the "
            "bank's total exposure measure. The exposure measure includes "
            "on-balance sheet exposures, derivative exposures, securities "
            "financing transaction exposures, and off-balance sheet items. "
            "For Indian banks, RBI has set the leverage ratio at 4% for "
            "Domestic Systemically Important Banks (D-SIBs)."
        ),
        "source_url": "https://www.bis.org/publ/bcbs270.pdf",
        "effective_date": "2014-01-12",
        "permission_level": "junior_analyst",
    },
    {
        "doc_id": "DOC_013",
        "doc_name": "Internal Policy – Board-Level AML Oversight Report",
        "doc_category": "board_reports",
        "section_number": "1.1",
        "section_title": "AML Program Effectiveness Assessment",
        "content": (
            "The Board-level AML oversight report provides a comprehensive "
            "assessment of the bank's anti-money laundering program effectiveness. "
            "Key metrics include: STR-to-SAR conversion rate (currently 34%), "
            "false positive rate in transaction monitoring (currently 78%), "
            "average investigation closure time (5.2 days), and regulatory "
            "examination findings remediation status (92% complete). The "
            "Principal Officer has recommended increasing the ML model "
            "threshold from 65 to 70 to reduce false positive burden."
        ),
        "source_url": "",
        "effective_date": "2026-09-30",
        "permission_level": "compliance_head",
    },
]


class RAGPipeline:
    """Permission-aware Retrieval-Augmented Generation pipeline.

    Encapsulates the full retrieval flow:  permission filter → search →
    rerank → format.  Designed to be used as a drop-in replacement for
    the old ``mock_rag_search()`` function.

    Parameters
    ----------
    session : snowflake.snowpark.Session, optional
        Active Snowpark session.  When provided, uses Cortex Search for
        retrieval.  When None, falls back to local BM25 search.
    top_k : int
        Number of chunks to return after reranking (default 5).
    """

    def __init__(self, session: Any = None, top_k: int = 5) -> None:
        self.session = session
        self.top_k = top_k
        self._env: str = getattr(config, "ENV", "local")
        self._search_service: str = getattr(
            config, "CORTEX_SEARCH_SERVICE", "AURIS_REGULATORY_SEARCH"
        )
        self._permission_filter = PermissionFilter(session=session)
        self._reranker = Reranker(top_k=top_k)

    # ------------------------------------------------------------------ #
    #  Main entry point                                                    #
    # ------------------------------------------------------------------ #

    def search(
        self,
        query: str,
        user_role: str,
        categories: list[str] | None = None,
        top_k: int | None = None,
    ) -> list[dict]:
        """Execute a permission-aware RAG search.

        Parameters
        ----------
        query : str
            Natural-language search query.
        user_role : str
            The requesting user's role (determines document access).
        categories : list[str], optional
            Override allowed categories.  When None, derived from role.
        top_k : int, optional
            Override the default top-K.

        Returns
        -------
        list[dict]
            Permission-filtered, reranked document chunks.  Each dict
            contains: ``doc_name``, ``section_number``, ``section_title``,
            ``content``, ``source_url``, ``relevance_score``,
            ``rerank_score``, ``permission_level``, ``doc_category``.
        """
        effective_top_k = top_k or self.top_k

        logger.info(
            "[RAGPipeline] Search for role='%s', query='%s…'",
            user_role,
            query[:60],
        )

        # Step 1: Determine allowed categories
        if categories:
            allowed_categories = categories
        else:
            allowed_categories = self._permission_filter.get_allowed_categories(user_role)

        logger.debug(
            "[RAGPipeline] Allowed categories for '%s': %s",
            user_role,
            allowed_categories,
        )

        # Step 2: Retrieve candidates (with permission pre-filter)
        if self._env == "snowflake" and self.session is not None:
            candidates = self._search_cortex(query, user_role)
        else:
            candidates = self._search_local(query, user_role)

        if not candidates:
            logger.warning("[RAGPipeline] No candidates returned from search.")
            return []

        # Step 3: Apply permission filter (defense-in-depth)
        # Even if Cortex Search already filtered, we double-check locally
        permitted = self._permission_filter.filter_documents(candidates, user_role)

        if not permitted:
            logger.warning(
                "[RAGPipeline] All %d candidates filtered out by permissions.",
                len(candidates),
            )
            return []

        # Step 4: Rerank
        reranked = self._reranker.rerank(
            query=query,
            chunks=permitted,
            cortex_client=None,
        )

        # Step 5: Take top-K and ensure top_k
        results = reranked[:effective_top_k]

        logger.info(
            "[RAGPipeline] Returning %d results (from %d candidates, %d permitted).",
            len(results),
            len(candidates),
            len(permitted),
        )
        return results

    # ------------------------------------------------------------------ #
    #  Cortex Search (live mode)                                           #
    # ------------------------------------------------------------------ #

    def _search_cortex(self, query: str, user_role: str) -> list[dict]:
        """Search via Snowflake Cortex Search with permission filter."""
        try:
            # Build permission-scoped filter
            cortex_filter = self._permission_filter.build_cortex_filter(user_role)

            filter_json = json.dumps(cortex_filter).replace("'", "''")
            query_escaped = query.replace("'", "''")

            sql = f"""
            SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
                '{self._search_service}',
                '{query_escaped}',
                OBJECT_CONSTRUCT(
                    'columns', ARRAY_CONSTRUCT(
                        'CONTENT', 'DOC_NAME', 'DOC_CATEGORY',
                        'SECTION_NUMBER', 'SECTION_TITLE', 'SOURCE_URL',
                        'PERMISSION_LEVEL', 'EFFECTIVE_DATE'
                    ),
                    'filter', PARSE_JSON('{filter_json}'),
                    'limit', 20
                )
            ) AS search_results
            """
            rows = self.session.sql(sql).collect()
            if rows:
                raw = json.loads(rows[0]["SEARCH_RESULTS"])
                results = raw.get("results", [])
                # Normalize keys to lowercase
                return [
                    {
                        "doc_name": r.get("DOC_NAME", r.get("doc_name", "")),
                        "doc_category": r.get("DOC_CATEGORY", r.get("doc_category", "")),
                        "section_number": r.get("SECTION_NUMBER", r.get("section_number", "")),
                        "section_title": r.get("SECTION_TITLE", r.get("section_title", "")),
                        "content": r.get("CONTENT", r.get("content", "")),
                        "source_url": r.get("SOURCE_URL", r.get("source_url", "")),
                        "permission_level": r.get("PERMISSION_LEVEL", r.get("permission_level", "junior_analyst")),
                        "effective_date": r.get("EFFECTIVE_DATE", r.get("effective_date", "")),
                        "relevance_score": float(r.get("score", r.get("relevance_score", 0.5))),
                    }
                    for r in results
                ]
        except Exception as exc:
            logger.error(
                "[RAGPipeline] Cortex Search failed, falling back to local: %s", exc
            )

        return self._search_local(query, user_role)

    # ------------------------------------------------------------------ #
    #  Local BM25 search (mock mode)                                       #
    # ------------------------------------------------------------------ #

    def _search_local(self, query: str, user_role: str) -> list[dict]:
        """BM25-style local search over the embedded corpus.

        Performs term frequency scoring with inverse document frequency
        weighting.  Permission filtering happens in the caller.
        """
        logger.info("[RAGPipeline] Using local BM25 search (local mode).")

        query_terms = self._tokenize(query.lower())
        if not query_terms:
            # Return all docs sorted by recency
            return list(_LOCAL_CORPUS)

        # Compute IDF for each query term
        n_docs = len(_LOCAL_CORPUS)
        idf: dict[str, float] = {}
        for term in query_terms:
            doc_freq = sum(
                1 for doc in _LOCAL_CORPUS
                if term in (doc.get("content", "") + " " + doc.get("doc_name", "")).lower()
            )
            idf[term] = math.log((n_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0)

        # Score each document
        scored: list[tuple[float, dict]] = []
        k1 = 1.5
        b = 0.75
        avg_dl = sum(
            len(doc.get("content", "").split()) for doc in _LOCAL_CORPUS
        ) / max(1, n_docs)

        for doc in _LOCAL_CORPUS:
            text = (doc.get("content", "") + " " + doc.get("doc_name", "") +
                    " " + doc.get("section_title", "")).lower()
            dl = len(text.split())
            score = 0.0

            for term in query_terms:
                tf = text.count(term)
                if tf > 0:
                    numerator = tf * (k1 + 1)
                    denominator = tf + k1 * (1 - b + b * dl / avg_dl)
                    score += idf.get(term, 0) * numerator / denominator

            if score > 0:
                doc_with_score = dict(doc)
                doc_with_score["relevance_score"] = round(
                    min(1.0, score / (len(query_terms) * 2)),
                    4,
                )
                scored.append((score, doc_with_score))

        # Sort by BM25 score and return top 20 candidates for reranking
        scored.sort(key=lambda x: x[0], reverse=True)
        candidates = [doc for _, doc in scored[:20]]

        logger.debug(
            "[RAGPipeline] BM25 local search returned %d candidates.",
            len(candidates),
        )
        return candidates

    # ------------------------------------------------------------------ #
    #  Tokenizer                                                           #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Tokenize text for BM25 search, stripping stopwords."""
        _STOPWORDS = frozenset({
            "a", "an", "the", "is", "are", "was", "were", "in", "on", "at",
            "to", "for", "of", "and", "or", "but", "not", "with", "by",
            "from", "as", "it", "its", "this", "that", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "shall", "can", "what", "how",
            "which", "who", "whom", "where", "when", "why", "all", "each",
            "our", "my", "your", "their", "me", "i", "we", "you", "he", "she",
        })
        tokens = re.findall(r"[a-z0-9₹]+", text.lower())
        return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]
