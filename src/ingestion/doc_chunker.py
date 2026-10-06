"""
src/ingestion/doc_chunker.py
-----------------------------
Section-aware document chunker for the Auris regulatory ingestion pipeline.

Splits parsed document text into overlapping, semantically coherent chunks
optimised for RAG retrieval.  Key design choices:

- **Section-aware splitting**: Respects heading boundaries so chunks don't
  straddle two unrelated sections.
- **Overlap**: Adjacent chunks share a configurable overlap window so
  context is not lost at boundaries.
- **Metadata propagation**: Each chunk inherits the document name, section
  number, and section title from the source.
- **Size control**: Chunks are kept within a token-count window so they
  fit within LLM context limits.

Usage
-----
    from src.ingestion.doc_chunker import DocChunker

    chunker = DocChunker(max_chunk_tokens=400, overlap_tokens=50)
    chunks = chunker.chunk_document(pages, doc_name="RBI KYC 2016")
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# Approximate tokens per character (English regulatory text)
_CHARS_PER_TOKEN = 4.0


class DocChunker:
    """Split document text into overlapping, section-aware chunks.

    Parameters
    ----------
    max_chunk_tokens : int
        Maximum number of tokens per chunk (default 400).
    overlap_tokens : int
        Number of overlapping tokens between consecutive chunks (default 50).
    min_chunk_tokens : int
        Minimum tokens for a chunk to be emitted (default 30).
    """

    def __init__(
        self,
        max_chunk_tokens: int = 400,
        overlap_tokens: int = 50,
        min_chunk_tokens: int = 30,
    ) -> None:
        self.max_chunk_chars = int(max_chunk_tokens * _CHARS_PER_TOKEN)
        self.overlap_chars = int(overlap_tokens * _CHARS_PER_TOKEN)
        self.min_chunk_chars = int(min_chunk_tokens * _CHARS_PER_TOKEN)

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def chunk_document(
        self,
        pages: list[dict[str, Any]],
        doc_name: str = "Unknown Document",
        doc_category: str = "public_policy",
        permission_level: str = "junior_analyst",
        source_url: str = "",
        effective_date: str = "",
    ) -> list[dict[str, Any]]:
        """Chunk parsed pages into RAG-ready document chunks.

        Parameters
        ----------
        pages : list[dict]
            Output from :meth:`PDFParser.parse` — each dict has
            ``page_number``, ``text``, ``char_count``.
        doc_name : str
            Human-readable document title.
        doc_category : str
            Regulatory domain: ``aml_guidelines``, ``public_policy``, etc.
        permission_level : str
            Minimum role required to access these chunks.
        source_url : str
            Canonical URL of the source document.
        effective_date : str
            ISO date when the regulation took effect.

        Returns
        -------
        list[dict]
            Chunks ready for insertion into ``REGULATORY_DOCS``.  Each
            dict has keys matching the table schema.
        """
        # Concatenate all page text
        full_text = "\n\n".join(p["text"] for p in pages if p.get("text"))

        if not full_text.strip():
            logger.warning("[DocChunker] No text content to chunk.")
            return []

        # Split into sections by headings
        sections = self._split_into_sections(full_text)
        logger.info(
            "[DocChunker] Split '%s' into %d sections.",
            doc_name,
            len(sections),
        )

        # Chunk each section with overlap
        all_chunks: list[dict[str, Any]] = []
        for section in sections:
            section_chunks = self._chunk_section(
                section_text=section["text"],
                section_number=section["section_number"],
                section_title=section["section_title"],
                doc_name=doc_name,
                doc_category=doc_category,
                permission_level=permission_level,
                source_url=source_url,
                effective_date=effective_date,
            )
            all_chunks.extend(section_chunks)

        logger.info(
            "[DocChunker] Produced %d chunks for '%s' (avg %d chars each).",
            len(all_chunks),
            doc_name,
            sum(len(c["content"]) for c in all_chunks) // max(1, len(all_chunks)),
        )
        return all_chunks

    def chunk_text(
        self,
        text: str,
        doc_name: str = "Unknown Document",
        doc_category: str = "public_policy",
        permission_level: str = "junior_analyst",
        source_url: str = "",
        effective_date: str = "",
    ) -> list[dict[str, Any]]:
        """Convenience method to chunk raw text directly.

        Wraps *text* in a single-page structure and delegates to
        :meth:`chunk_document`.
        """
        pages = [{"page_number": 1, "text": text, "char_count": len(text)}]
        return self.chunk_document(
            pages=pages,
            doc_name=doc_name,
            doc_category=doc_category,
            permission_level=permission_level,
            source_url=source_url,
            effective_date=effective_date,
        )

    # ------------------------------------------------------------------ #
    #  Section splitting                                                   #
    # ------------------------------------------------------------------ #

    def _split_into_sections(self, text: str) -> list[dict[str, Any]]:
        """Split document text into logical sections by headings.

        Detects headings by patterns like:
        - Markdown: ``## Section Title``
        - Numbered: ``3.1 Section Title`` or ``Section 12(iii)``
        - ALL CAPS lines
        """
        # Heading patterns
        patterns = [
            # Markdown headings
            re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE),
            # Numbered sections like "3.1" or "3.1.2"
            re.compile(r"^(\d+(?:\.\d+)*)\s+([A-Z][\w\s\-–—:,]+)$", re.MULTILINE),
            # "Section X" or "CHAPTER X"
            re.compile(
                r"^((?:Section|Chapter|Part|Article|Rule|Clause)\s+\d+[A-Za-z()]*)\s*[-–—:.]?\s*(.*)$",
                re.MULTILINE | re.IGNORECASE,
            ),
        ]

        # Find all heading positions
        headings: list[tuple[int, str, str]] = []  # (pos, section_number, title)
        for pattern in patterns:
            for match in pattern.finditer(text):
                headings.append((
                    match.start(),
                    match.group(1).strip().lstrip("#").strip(),
                    match.group(2).strip() if match.group(2) else match.group(1).strip(),
                ))

        # De-duplicate and sort by position
        headings.sort(key=lambda x: x[0])

        if not headings:
            # No headings found — treat entire text as one section
            return [{
                "section_number": "1",
                "section_title": "Document Content",
                "text": text.strip(),
            }]

        sections: list[dict[str, Any]] = []

        # Text before first heading
        pre_text = text[: headings[0][0]].strip()
        if pre_text and len(pre_text) > self.min_chunk_chars:
            sections.append({
                "section_number": "0",
                "section_title": "Preamble",
                "text": pre_text,
            })

        # Each heading → next heading
        for i, (pos, sec_num, title) in enumerate(headings):
            end_pos = headings[i + 1][0] if i + 1 < len(headings) else len(text)
            section_text = text[pos:end_pos].strip()

            if section_text and len(section_text) > self.min_chunk_chars:
                sections.append({
                    "section_number": sec_num,
                    "section_title": title,
                    "text": section_text,
                })

        return sections

    # ------------------------------------------------------------------ #
    #  Within-section chunking with overlap                                #
    # ------------------------------------------------------------------ #

    def _chunk_section(
        self,
        section_text: str,
        section_number: str,
        section_title: str,
        doc_name: str,
        doc_category: str,
        permission_level: str,
        source_url: str,
        effective_date: str,
    ) -> list[dict[str, Any]]:
        """Chunk a single section into overlapping windows."""
        if len(section_text) <= self.max_chunk_chars:
            # Section fits in one chunk
            return [
                self._make_chunk(
                    content=section_text,
                    section_number=section_number,
                    section_title=section_title,
                    doc_name=doc_name,
                    doc_category=doc_category,
                    permission_level=permission_level,
                    source_url=source_url,
                    effective_date=effective_date,
                )
            ]

        # Split at sentence boundaries for cleaner chunks
        sentences = self._split_sentences(section_text)
        chunks: list[dict[str, Any]] = []
        current_text = ""
        overlap_text = ""

        for sentence in sentences:
            if len(current_text) + len(sentence) > self.max_chunk_chars and current_text:
                # Emit current chunk
                chunks.append(
                    self._make_chunk(
                        content=current_text.strip(),
                        section_number=section_number,
                        section_title=section_title,
                        doc_name=doc_name,
                        doc_category=doc_category,
                        permission_level=permission_level,
                        source_url=source_url,
                        effective_date=effective_date,
                    )
                )

                # Keep overlap from the end of current chunk
                overlap_text = current_text[-self.overlap_chars:] if self.overlap_chars else ""
                current_text = overlap_text + sentence
            else:
                current_text += sentence

        # Emit remaining text
        if current_text.strip() and len(current_text.strip()) >= self.min_chunk_chars:
            chunks.append(
                self._make_chunk(
                    content=current_text.strip(),
                    section_number=section_number,
                    section_title=section_title,
                    doc_name=doc_name,
                    doc_category=doc_category,
                    permission_level=permission_level,
                    source_url=source_url,
                    effective_date=effective_date,
                )
            )

        return chunks

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _make_chunk(
        content: str,
        section_number: str,
        section_title: str,
        doc_name: str,
        doc_category: str,
        permission_level: str,
        source_url: str,
        effective_date: str,
    ) -> dict[str, Any]:
        """Build a chunk dict matching the ``REGULATORY_DOCS`` schema."""
        return {
            "doc_id": str(uuid.uuid4()),
            "doc_name": doc_name,
            "doc_category": doc_category,
            "section_number": section_number,
            "section_title": section_title,
            "content": content,
            "source_url": source_url,
            "effective_date": effective_date,
            "permission_level": permission_level,
        }

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Split text into sentences preserving sentence-ending punctuation.

        Uses a regex that handles common regulatory text patterns like
        numbered lists, abbreviations (e.g., 'Rs.', 'viz.'), and
        section references (e.g., '12(iii)').
        """
        # Negative lookbehind for common abbreviations
        sentence_end = re.compile(
            r"(?<!\bRs)(?<!\bMr)(?<!\bMrs)(?<!\bDr)(?<!\bvs)"
            r"(?<!\bSr)(?<!\bJr)(?<!\bNo)(?<!\bVol)"
            r"(?<=[.!?])\s+(?=[A-Z(0-9])"
        )
        parts = sentence_end.split(text)
        # Ensure each part ends with a space for recombination
        return [p + " " for p in parts if p.strip()]
