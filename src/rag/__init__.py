"""
src/rag — Permission-Aware RAG Pipeline for Auris.

Provides document retrieval with:
- Permission pre-filtering (filter BEFORE ranking)
- Semantic search via Cortex Search or local BM25
- Cross-encoder reranking for precision
- Citation-ready output formatting
"""

from src.rag.permission_filter import PermissionFilter
from src.rag.reranker import Reranker
from src.rag.rag_pipeline import RAGPipeline

__all__ = ["PermissionFilter", "Reranker", "RAGPipeline"]
