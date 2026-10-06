"""
src/ingestion — Regulatory Document Ingestion Pipeline for Auris.

Provides tools to:
- Parse PDFs and extract text content
- Chunk documents intelligently with section-awareness
- Assign permission levels and categories
- Upload chunks to Snowflake (or save locally for demo)
"""

from src.ingestion.doc_chunker import DocChunker
from src.ingestion.pdf_parser import PDFParser
from src.ingestion.ingestion_pipeline import IngestionPipeline

__all__ = ["DocChunker", "PDFParser", "IngestionPipeline"]
