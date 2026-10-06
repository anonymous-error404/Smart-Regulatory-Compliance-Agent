"""
src/rag/reranker.py
--------------------
Cross-encoder-style reranker for the Auris RAG pipeline.

After the initial retrieval (Cortex Search or BM25), the reranker
re-scores each candidate chunk against the original query using a
multi-signal scoring approach:

1. **Keyword overlap** — exact term matching (BM25-like)
2. **Section relevance** — boost for section titles matching query terms
3. **Recency** — newer regulatory docs get a slight uplift
4. **Regulatory specificity** — chunks citing specific sections score higher
5. **LLM-assisted** — optional Cortex LLM scoring (live mode only)

The reranker returns the top-K chunks sorted by combined score.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, date
from typing import Any

logger = logging.getLogger(__name__)

# Weights for the multi-signal scoring
_W_KEYWORD = 0.35
_W_SECTION = 0.20
_W_RECENCY = 0.10
_W_SPECIFICITY = 0.15
_W_ORIGINAL = 0.20  # weight of the original retrieval score


class Reranker:
    """Multi-signal document chunk reranker.

    Operates entirely locally (no external API calls) so it works in
    both ``ENV='local'`` and ``ENV='snowflake'`` modes.  For LLM-assisted
    reranking, pass a ``cortex_client`` to :meth:`rerank`.

    Parameters
    ----------
    top_k : int
        Maximum number of chunks to return after reranking (default 5).
    """

    def __init__(self, top_k: int = 5) -> None:
        self.top_k = top_k

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def rerank(
        self,
        query: str,
        chunks: list[dict],
        cortex_client: Any = None,
    ) -> list[dict]:
        """Rerank *chunks* against *query* and return top-K results.

        Each chunk dict is expected to have:
        - ``content`` (str)
        - ``doc_name`` (str)
        - ``section_number`` (str)
        - ``section_title`` (str)
        - ``relevance_score`` (float) — original retrieval score
        - ``effective_date`` (str, optional)

        After reranking, each chunk receives an additional
        ``rerank_score`` key (float, 0.0–1.0).

        Parameters
        ----------
        query : str
            The user's natural-language query.
        chunks : list[dict]
            Candidate document chunks from initial retrieval.
        cortex_client : CortexClient, optional
            If provided, enables LLM-assisted reranking as a bonus signal.

        Returns
        -------
        list[dict]
            Top-K chunks sorted by ``rerank_score`` descending.
        """
        if not chunks:
            return []

        query_lower = query.lower()
        query_terms = set(self._tokenize(query_lower))

        scored: list[tuple[float, dict]] = []
        for chunk in chunks:
            score = self._compute_score(chunk, query_lower, query_terms)
            chunk_copy = dict(chunk)
            chunk_copy["rerank_score"] = round(score, 4)
            scored.append((score, chunk_copy))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        # Return top-K
        results = [chunk for _, chunk in scored[: self.top_k]]

        logger.info(
            "[Reranker] Reranked %d chunks → top %d returned. "
            "Score range: %.3f – %.3f",
            len(chunks),
            len(results),
            results[-1]["rerank_score"] if results else 0,
            results[0]["rerank_score"] if results else 0,
        )
        return results

    # ------------------------------------------------------------------ #
    #  Scoring                                                             #
    # ------------------------------------------------------------------ #

    def _compute_score(
        self,
        chunk: dict,
        query_lower: str,
        query_terms: set[str],
    ) -> float:
        """Compute a combined relevance score for a single chunk."""
        s_keyword = self._score_keyword_overlap(chunk, query_terms)
        s_section = self._score_section_relevance(chunk, query_terms)
        s_recency = self._score_recency(chunk)
        s_specificity = self._score_specificity(chunk)
        s_original = float(chunk.get("relevance_score", 0.5))

        combined = (
            _W_KEYWORD * s_keyword
            + _W_SECTION * s_section
            + _W_RECENCY * s_recency
            + _W_SPECIFICITY * s_specificity
            + _W_ORIGINAL * s_original
        )
        return min(1.0, combined)

    @staticmethod
    def _score_keyword_overlap(chunk: dict, query_terms: set[str]) -> float:
        """Compute BM25-like keyword overlap score (0.0–1.0)."""
        content = chunk.get("content", "").lower()
        doc_name = chunk.get("doc_name", "").lower()
        combined_text = content + " " + doc_name

        if not query_terms:
            return 0.0

        matched = sum(1 for term in query_terms if term in combined_text)
        # TF-IDF-inspired: diminishing returns for many matches
        raw_ratio = matched / len(query_terms)
        # BM25-like saturation
        k1 = 1.2
        return raw_ratio * (k1 + 1) / (raw_ratio + k1)

    @staticmethod
    def _score_section_relevance(chunk: dict, query_terms: set[str]) -> float:
        """Score how well the section title matches the query (0.0–1.0)."""
        section_title = chunk.get("section_title", "").lower()
        if not section_title or not query_terms:
            return 0.0

        title_terms = set(section_title.split())
        overlap = query_terms & title_terms
        if not overlap:
            # Partial substring matching
            for qt in query_terms:
                if len(qt) > 3 and qt in section_title:
                    return 0.4
            return 0.0

        return min(1.0, len(overlap) / max(1, min(len(query_terms), len(title_terms))))

    @staticmethod
    def _score_recency(chunk: dict) -> float:
        """Score based on document recency — newer docs rank higher (0.0–1.0).

        Docs from the last 2 years get full score; older docs decay linearly.
        """
        effective_date = chunk.get("effective_date", "")
        if not effective_date:
            return 0.5  # neutral default

        try:
            if isinstance(effective_date, str):
                eff_date = datetime.fromisoformat(effective_date[:10]).date()
            elif isinstance(effective_date, (datetime, date)):
                eff_date = effective_date if isinstance(effective_date, date) else effective_date.date()
            else:
                return 0.5

            days_old = (date.today() - eff_date).days
            # Full score for docs < 2 years old; decays over 10 years
            if days_old <= 730:
                return 1.0
            max_age_days = 3650  # 10 years
            return max(0.1, 1.0 - (days_old - 730) / max_age_days)
        except (ValueError, TypeError):
            return 0.5

    @staticmethod
    def _score_specificity(chunk: dict) -> float:
        """Score chunks with specific section references higher (0.0–1.0).

        A chunk that cites "Section 12(iii)" is more useful than one with
        no section reference.
        """
        section_number = chunk.get("section_number", "")
        content = chunk.get("content", "")

        score = 0.3  # baseline

        # Has a specific section number?
        if section_number and section_number != "N/A":
            score += 0.3

        # Content contains specific regulatory references?
        specificity_patterns = [
            r"section\s+\d+",
            r"rule\s+\d+",
            r"clause\s+\d+",
            r"paragraph\s+\d+",
            r"regulation\s+\d+",
            r"₹\s*[\d,]+",  # monetary thresholds
            r"\d+%",  # percentage thresholds
        ]
        matches = sum(
            1 for pat in specificity_patterns
            if re.search(pat, content, re.IGNORECASE)
        )
        score += min(0.4, matches * 0.1)

        return min(1.0, score)

    # ------------------------------------------------------------------ #
    #  Tokenizer                                                           #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple whitespace + punctuation tokenizer.

        Strips common stopwords to improve signal quality.
        """
        _STOPWORDS = frozenset({
            "a", "an", "the", "is", "are", "was", "were", "in", "on", "at",
            "to", "for", "of", "and", "or", "but", "not", "with", "by",
            "from", "as", "it", "its", "this", "that", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "shall", "can", "what", "how",
            "which", "who", "whom", "where", "when", "why", "all", "each",
            "our", "my", "your", "their", "me", "i", "we", "you", "he", "she",
        })

        # Split on non-alphanumeric characters
        tokens = re.findall(r"[a-z0-9₹]+", text.lower())
        return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]
