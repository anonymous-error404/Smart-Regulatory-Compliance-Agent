"""
src/ingestion/pdf_parser.py
----------------------------
PDF text extraction for the Auris regulatory document ingestion pipeline.

Supports multiple extraction backends (PyPDF2, pdfplumber, fallback to
text file reading) and returns structured page-level text with metadata.

Usage
-----
    from src.ingestion.pdf_parser import PDFParser

    parser = PDFParser()
    pages = parser.parse("path/to/regulatory_doc.pdf")
    # [{"page_number": 1, "text": "...", "char_count": 1234}, ...]
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PDFParser:
    """Extract text content from PDF and text files.

    Tries multiple PDF libraries in order of preference:
    1. ``pdfplumber`` — best for table-heavy regulatory docs
    2. ``PyPDF2``     — widely available, good for text-heavy PDFs
    3. Fallback       — plain text file reader

    Parameters
    ----------
    fallback_encoding : str
        Encoding to use when reading plain text files (default ``'utf-8'``).
    """

    def __init__(self, fallback_encoding: str = "utf-8") -> None:
        self._encoding = fallback_encoding
        self._backend = self._detect_backend()
        logger.info("[PDFParser] Using backend: %s", self._backend)

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def parse(self, file_path: str) -> list[dict[str, Any]]:
        """Extract text from a PDF or text file.

        Parameters
        ----------
        file_path : str
            Absolute or relative path to the document.

        Returns
        -------
        list[dict]
            One dict per page/section with keys:
            ``page_number`` (int), ``text`` (str), ``char_count`` (int).

        Raises
        ------
        FileNotFoundError
            If *file_path* does not exist.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {file_path}")

        ext = path.suffix.lower()
        logger.info("[PDFParser] Parsing '%s' (ext=%s)", path.name, ext)

        if ext == ".pdf":
            return self._parse_pdf(path)
        elif ext in {".txt", ".md", ".csv"}:
            return self._parse_text(path)
        else:
            logger.warning(
                "[PDFParser] Unsupported extension '%s', attempting text parse.",
                ext,
            )
            return self._parse_text(path)

    def parse_directory(self, dir_path: str, extensions: list[str] | None = None) -> dict[str, list[dict]]:
        """Parse all supported files in a directory.

        Parameters
        ----------
        dir_path : str
            Path to the directory containing documents.
        extensions : list[str], optional
            File extensions to include (default: ``.pdf``, ``.txt``, ``.md``).

        Returns
        -------
        dict[str, list[dict]]
            Mapping of ``filename → pages``.
        """
        if extensions is None:
            extensions = [".pdf", ".txt", ".md"]

        dirp = Path(dir_path)
        if not dirp.is_dir():
            raise NotADirectoryError(f"Not a directory: {dir_path}")

        results: dict[str, list[dict]] = {}
        for fpath in sorted(dirp.iterdir()):
            if fpath.suffix.lower() in extensions and fpath.is_file():
                try:
                    pages = self.parse(str(fpath))
                    results[fpath.name] = pages
                    logger.info(
                        "[PDFParser] Parsed '%s': %d pages, %d chars total.",
                        fpath.name,
                        len(pages),
                        sum(p["char_count"] for p in pages),
                    )
                except Exception as exc:
                    logger.error("[PDFParser] Failed to parse '%s': %s", fpath.name, exc)

        return results

    # ------------------------------------------------------------------ #
    #  PDF backends                                                        #
    # ------------------------------------------------------------------ #

    def _parse_pdf(self, path: Path) -> list[dict[str, Any]]:
        """Route to the best available PDF backend."""
        if self._backend == "pdfplumber":
            return self._parse_with_pdfplumber(path)
        elif self._backend == "pypdf2":
            return self._parse_with_pypdf2(path)
        else:
            logger.warning(
                "[PDFParser] No PDF library available. "
                "Install pdfplumber or PyPDF2: pip install pdfplumber"
            )
            return []

    @staticmethod
    def _parse_with_pdfplumber(path: Path) -> list[dict[str, Any]]:
        """Extract text using pdfplumber (best for regulatory tables)."""
        import pdfplumber  # type: ignore[import]

        pages: list[dict[str, Any]] = []
        with pdfplumber.open(str(path)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                # Also try extracting tables
                tables = page.extract_tables() or []
                table_text_parts: list[str] = []
                for table in tables:
                    for row in table:
                        cleaned = [str(cell).strip() if cell else "" for cell in row]
                        table_text_parts.append(" | ".join(cleaned))

                if table_text_parts:
                    text += "\n\n[TABLE]\n" + "\n".join(table_text_parts)

                text = text.strip()
                if text:
                    pages.append({
                        "page_number": i,
                        "text": text,
                        "char_count": len(text),
                    })

        return pages

    @staticmethod
    def _parse_with_pypdf2(path: Path) -> list[dict[str, Any]]:
        """Extract text using pypdf or PyPDF2."""
        try:
            from pypdf import PdfReader  # type: ignore[import]
        except ImportError:
            from PyPDF2 import PdfReader  # type: ignore[import]

        pages: list[dict[str, Any]] = []
        reader = PdfReader(str(path))
        for i, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            text = text.strip()
            if text:
                pages.append({
                    "page_number": i,
                    "text": text,
                    "char_count": len(text),
                })

        return pages

    # ------------------------------------------------------------------ #
    #  Text file parsing                                                   #
    # ------------------------------------------------------------------ #

    def _parse_text(self, path: Path) -> list[dict[str, Any]]:
        """Read a plain text or markdown file as a single 'page'."""
        text = path.read_text(encoding=self._encoding, errors="replace")
        text = text.strip()
        if not text:
            return []

        # Split into logical sections (by blank-line-separated paragraphs
        # or Markdown headings)
        sections = self._split_text_sections(text)
        pages: list[dict[str, Any]] = []
        for i, section in enumerate(sections, start=1):
            section = section.strip()
            if section:
                pages.append({
                    "page_number": i,
                    "text": section,
                    "char_count": len(section),
                })

        return pages

    @staticmethod
    def _split_text_sections(text: str) -> list[str]:
        """Split text into sections by headings or double newlines."""
        import re

        # Split on Markdown headings (# ... or ## ...)
        heading_pattern = re.compile(r"(?=^#{1,3}\s+)", re.MULTILINE)
        sections = heading_pattern.split(text)

        # If no headings, split by double newlines
        if len(sections) <= 1:
            sections = re.split(r"\n\s*\n", text)

        return [s for s in sections if s.strip()]

    # ------------------------------------------------------------------ #
    #  Backend detection                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _detect_backend() -> str:
        """Detect the best available PDF library."""
        try:
            import pdfplumber  # noqa: F401
            return "pdfplumber"
        except ImportError:
            pass
        try:
            from pypdf import PdfReader  # noqa: F401
            return "pypdf2"
        except ImportError:
            pass
        try:
            from PyPDF2 import PdfReader  # noqa: F401
            return "pypdf2"
        except ImportError:
            pass
        return "none"
