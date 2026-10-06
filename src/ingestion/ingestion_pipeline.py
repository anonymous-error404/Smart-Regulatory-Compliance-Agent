"""
src/ingestion/ingestion_pipeline.py
------------------------------------
End-to-end regulatory document ingestion pipeline for Auris.

Orchestrates the full flow:
    PDF/text file → parse → chunk → tag metadata → store

Supports two storage backends:
- **Snowflake** (live) — INSERT INTO ``REGULATORY_DOCS`` via Snowpark
- **Local JSON** (demo) — save chunks to a JSON file for local RAG

Usage
-----
    from src.ingestion.ingestion_pipeline import IngestionPipeline

    pipeline = IngestionPipeline()
    result = pipeline.ingest_file(
        file_path="docs/rbi_kyc_2016.pdf",
        doc_name="RBI Master Direction – KYC 2016",
        doc_category="aml_guidelines",
        permission_level="junior_analyst",
    )
    print(f"Ingested {result['chunk_count']} chunks")

    # Or ingest an entire directory:
    results = pipeline.ingest_directory("docs/regulatory/")
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Ensure project root is importable
# ---------------------------------------------------------------------------
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config  # noqa: E402
from src.ingestion.pdf_parser import PDFParser
from src.ingestion.doc_chunker import DocChunker

logger = logging.getLogger(__name__)

# Default output for local mode
_LOCAL_STORE_DIR = os.path.join(_ROOT, "data", "ingested_chunks")


# ------------------------------------------------------------------ #
#  Category auto-detection rules                                       #
# ------------------------------------------------------------------ #

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "aml_guidelines": [
        "anti-money laundering", "aml", "cft", "pmla", "money laundering",
        "suspicious transaction", "str", "ctr", "fiu", "know your customer",
        "kyc", "customer due diligence", "cdd", "enhanced due diligence",
        "politically exposed", "pep", "beneficial owner", "watchlist",
        "sanctions", "ofac",
    ],
    "public_policy": [
        "basel", "capital adequacy", "lcr", "nsfr", "leverage ratio",
        "risk weighted", "tier 1", "tier 2", "pillar", "liquidity coverage",
        "net stable funding", "rbi circular", "master direction",
        "master circular", "prudential norms", "sebi", "securities",
    ],
    "internal_policy": [
        "internal policy", "board approved", "risk appetite",
        "risk assessment methodology", "internal audit", "compliance manual",
        "operating procedure", "sop",
    ],
    "risk_reports": [
        "risk report", "credit exposure", "npa", "provisioning",
        "stress test", "concentration risk", "market risk", "operational risk",
        "risk committee", "quarterly report",
    ],
    "board_reports": [
        "board report", "board meeting", "committee report",
        "oversight report", "annual report", "shareholder",
    ],
    "kyc_pii": [
        "aadhaar", "pan number", "biometric", "personal data",
        "pii", "data protection", "privacy", "uidai",
    ],
}


class IngestionPipeline:
    """End-to-end document ingestion pipeline.

    Parameters
    ----------
    session : snowflake.snowpark.Session, optional
        Active Snowpark session.  When provided, chunks are inserted into
        ``REGULATORY_DOCS``.  When None, chunks are saved to local JSON.
    max_chunk_tokens : int
        Maximum tokens per chunk (default 400).
    overlap_tokens : int
        Overlap between consecutive chunks (default 50).
    """

    def __init__(
        self,
        session: Any = None,
        max_chunk_tokens: int = 400,
        overlap_tokens: int = 50,
    ) -> None:
        self.session = session
        self._env: str = getattr(config, "ENV", "local")
        self._parser = PDFParser()
        self._chunker = DocChunker(
            max_chunk_tokens=max_chunk_tokens,
            overlap_tokens=overlap_tokens,
        )

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def ingest_file(
        self,
        file_path: str,
        doc_name: str | None = None,
        doc_category: str | None = None,
        permission_level: str = "junior_analyst",
        source_url: str = "",
        effective_date: str = "",
    ) -> dict[str, Any]:
        """Ingest a single file into the regulatory corpus.

        Parameters
        ----------
        file_path : str
            Path to the PDF or text file.
        doc_name : str, optional
            Document title.  Auto-derived from filename if not provided.
        doc_category : str, optional
            Regulatory category.  Auto-detected from content if not provided.
        permission_level : str
            Minimum access role (default ``'junior_analyst'``).
        source_url : str
            Source URL for the document.
        effective_date : str
            ISO date when the regulation took effect.

        Returns
        -------
        dict
            Summary with ``file``, ``doc_name``, ``doc_category``,
            ``chunk_count``, ``total_chars``, ``stored_to``.
        """
        path = Path(file_path)
        if not doc_name:
            doc_name = path.stem.replace("_", " ").replace("-", " ").title()

        logger.info("[IngestionPipeline] Ingesting '%s' as '%s'", path.name, doc_name)

        # Step 1: Parse
        pages = self._parser.parse(str(path))
        if not pages:
            logger.warning("[IngestionPipeline] No content extracted from '%s'", path.name)
            return {
                "file": str(path),
                "doc_name": doc_name,
                "doc_category": doc_category or "unknown",
                "chunk_count": 0,
                "total_chars": 0,
                "stored_to": "none",
                "status": "empty",
            }

        # Step 2: Auto-detect category if not provided
        full_text = " ".join(p["text"] for p in pages)
        if not doc_category:
            doc_category = self._detect_category(full_text)
            logger.info("[IngestionPipeline] Auto-detected category: '%s'", doc_category)

        # Step 3: Chunk
        chunks = self._chunker.chunk_document(
            pages=pages,
            doc_name=doc_name,
            doc_category=doc_category,
            permission_level=permission_level,
            source_url=source_url,
            effective_date=effective_date or datetime.now().strftime("%Y-%m-%d"),
        )

        # Step 4: Store
        if self._env == "snowflake" and self.session is not None:
            self._store_snowflake(chunks)
            stored_to = "snowflake:REGULATORY_DOCS"
        else:
            self._store_local(chunks, doc_name)
            stored_to = f"local:{_LOCAL_STORE_DIR}"

        total_chars = sum(len(c["content"]) for c in chunks)
        result = {
            "file": str(path),
            "doc_name": doc_name,
            "doc_category": doc_category,
            "chunk_count": len(chunks),
            "total_chars": total_chars,
            "stored_to": stored_to,
            "status": "success",
        }

        logger.info(
            "[IngestionPipeline] Ingested '%s': %d chunks, %d chars → %s",
            doc_name,
            len(chunks),
            total_chars,
            stored_to,
        )
        return result

    def ingest_directory(
        self,
        dir_path: str,
        doc_category: str | None = None,
        permission_level: str = "junior_analyst",
    ) -> list[dict[str, Any]]:
        """Ingest all supported files in a directory.

        Parameters
        ----------
        dir_path : str
            Path to the directory containing documents.
        doc_category : str, optional
            Override category for all files.  Auto-detected per-file if None.
        permission_level : str
            Default permission level for all files.

        Returns
        -------
        list[dict]
            List of ingestion result summaries.
        """
        dirp = Path(dir_path)
        if not dirp.is_dir():
            raise NotADirectoryError(f"Not a directory: {dir_path}")

        results: list[dict[str, Any]] = []
        extensions = {".pdf", ".txt", ".md"}

        for fpath in sorted(dirp.iterdir()):
            if fpath.suffix.lower() in extensions and fpath.is_file():
                try:
                    result = self.ingest_file(
                        file_path=str(fpath),
                        doc_category=doc_category,
                        permission_level=permission_level,
                    )
                    results.append(result)
                except Exception as exc:
                    logger.error(
                        "[IngestionPipeline] Failed to ingest '%s': %s",
                        fpath.name,
                        exc,
                    )
                    results.append({
                        "file": str(fpath),
                        "status": "error",
                        "error": str(exc),
                    })

        logger.info(
            "[IngestionPipeline] Directory ingestion complete: %d files processed.",
            len(results),
        )
        return results

    # ------------------------------------------------------------------ #
    #  Storage backends                                                    #
    # ------------------------------------------------------------------ #

    def _store_snowflake(self, chunks: list[dict]) -> None:
        """INSERT chunks into the REGULATORY_DOCS table via Snowpark."""
        if not self.session:
            logger.error("[IngestionPipeline] No Snowpark session — cannot store.")
            return

        for chunk in chunks:
            try:
                sql = """
                INSERT INTO REGULATORY_DOCS
                    (DOC_ID, DOC_NAME, DOC_CATEGORY, SECTION_NUMBER,
                     SECTION_TITLE, CONTENT, SOURCE_URL, EFFECTIVE_DATE,
                     PERMISSION_LEVEL)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                self.session.sql(sql, params=[
                    chunk["doc_id"],
                    chunk["doc_name"],
                    chunk["doc_category"],
                    chunk.get("section_number", ""),
                    chunk.get("section_title", ""),
                    chunk["content"],
                    chunk.get("source_url", ""),
                    chunk.get("effective_date", ""),
                    chunk.get("permission_level", "junior_analyst"),
                ]).collect()
            except Exception as exc:
                logger.error(
                    "[IngestionPipeline] Failed to insert chunk '%s': %s",
                    chunk["doc_id"],
                    exc,
                )

        logger.info(
            "[IngestionPipeline] Inserted %d chunks into REGULATORY_DOCS.",
            len(chunks),
        )

    @staticmethod
    def _store_local(chunks: list[dict], doc_name: str) -> None:
        """Save chunks as JSON to the local data directory."""
        os.makedirs(_LOCAL_STORE_DIR, exist_ok=True)

        # Safe filename
        safe_name = "".join(
            c if c.isalnum() or c in " _-" else "_"
            for c in doc_name
        ).strip().replace(" ", "_")[:80]

        out_path = os.path.join(
            _LOCAL_STORE_DIR,
            f"{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        )

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(chunks, f, indent=2, ensure_ascii=False)

        logger.info("[IngestionPipeline] Saved %d chunks to %s", len(chunks), out_path)

    # ------------------------------------------------------------------ #
    #  Category auto-detection                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _detect_category(text: str) -> str:
        """Auto-detect the document category from content keywords."""
        text_lower = text.lower()

        scores: dict[str, int] = {}
        for category, keywords in _CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[category] = score

        if scores:
            best = max(scores, key=scores.get)  # type: ignore[arg-type]
            return best

        return "public_policy"  # default fallback
