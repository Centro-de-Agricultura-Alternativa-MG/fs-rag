"""Hybrid search engine combining keyword and semantic search."""

import sqlite3
from pathlib import Path
from typing import Optional

from fs_rag.core import get_config, get_logger
from fs_rag.core.embeddings import get_embeddings_provider
from fs_rag.core.vector_db import get_vector_db

logger = get_logger(__name__)


class SearchResult:
    """Represents a search result."""

    def __init__(self, file_path: str, content: str, metadata: dict, score: float):
        self.file_path = file_path
        self.content = content
        self.metadata = metadata
        self.score = score

    def __repr__(self):
        return f"SearchResult(file={self.file_path}, score={self.score:.3f})"


class HybridSearchEngine:
    """Hybrid search combining keyword and semantic search."""

    def __init__(self, index_db_path: Optional[Path] = None):
        self.config = get_config()
        self.embeddings = get_embeddings_provider()
        self.vector_db = get_vector_db()

        self.db_path = index_db_path or (self.config.index_dir / "index.db")

    def keyword_search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Search using keyword matching in SQLite."""
        if not self.db_path.exists():
            logger.warning(f"Index database not found: {self.db_path}")
            return []

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        try:
            # FTS (Full-Text Search) would be better, but for simplicity using LIKE
            cursor = conn.execute("""
                SELECT DISTINCT c.id, c.content, f.path
                FROM chunks c
                JOIN files f ON c.file_id = f.id
                WHERE c.content LIKE ?
                LIMIT ?
            """, (f"%{query}%", top_k))

            results = []
            for row in cursor.fetchall():
                results.append(SearchResult(
                    file_path=row["path"],
                    content=row["content"],
                    metadata={"chunk_id": row["id"]},
                    score=1.0  # Keyword match gets score of 1.0
                ))

            return results
        finally:
            conn.close()

    def semantic_search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Search using semantic similarity in vector DB."""
        try:
            query_embedding = self.embeddings.embed(query)
        except Exception as e:
            logger.error(f"Error embedding query: {e}")
            return []

        try:
            vector_results = self.vector_db.search(query_embedding, top_k=top_k)
        except Exception as e:
            logger.error(f"Error searching vector DB: {e}")
            return []

        results = []
        for result in vector_results:
            # Convert distance to similarity score (0-1, higher is better)
            # ChromaDB returns distances in [0, 2] for cosine, Qdrant returns similarity in [0, 1]
            similarity = 1.0 - (result["distance"] / 2.0) if result["distance"] > 1 else result["distance"]

            results.append(SearchResult(
                file_path=result["metadata"].get("file_path", "unknown"),
                content=result["document"],
                metadata=result["metadata"],
                score=max(0, min(1, similarity))  # Normalize to [0, 1]
            ))

        return results

    def search_feedback_responses(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Search for knowledge feedback responses (approved answers indexed as knowledge)."""
        try:
            query_embedding = self.embeddings.embed(query)
        except Exception as e:
            logger.error(f"Error embedding query for feedback search: {e}")
            return []

        try:
            # Search in vector DB, filtering for feedback responses
            vector_results = self.vector_db.search_source_type(query_embedding,  top_k=top_k  , source_type="knowledge_feedback")
        except Exception as e:
            logger.error(f"Error searching vector DB for feedback: {e}")
            return []

        print(vector_results)
        results = []
        for result in vector_results:
            # Filter to only knowledge feedback responses
            metadata = result.get("metadata", {})
            if metadata.get("source_type") != "knowledge_feedback":
                continue

            # Convert distance to similarity score
            similarity = 1.0 - (result["distance"] / 2.0) if result["distance"] > 1 else result["distance"]

            results.append(SearchResult(
                file_path="[Knowledge Feedback]",
                content=result["document"],
                metadata=metadata,
                score=max(0, min(1, similarity))  # Normalize to [0, 1]
            ))
        print(results)
        return results

    def hybrid_search(self, query: str, top_k: int = 5, semantic_weight: float = 0.7) -> list[SearchResult]:
        """Combined keyword, semantic, and feedback search with weighted scoring."""
        keyword_results = self.keyword_search(query, top_k=top_k * 2)
        semantic_results = self.semantic_search(query, top_k=top_k * 2)
        
        # Include feedback responses with higher weight
        feedback_results = []
        if self.config.knowledge_feedback_enabled:
            feedback_results = self.search_feedback_responses(
                query, 
                top_k=min(self.config.knowledge_feedback_max_retrieval_results, top_k)
            )

        # Combine results by file path and content
        combined = {}
        feedback_multiplier = self.config.knowledge_feedback_score_multiplier
        print(feedback_results)
        # Add feedback results with boost (highest priority)
        for result in feedback_results:
            key = (result.file_path, result.content[:100])
            if key not in combined:
                combined[key] = result
                # Apply feedback boost and semantic weight
                combined[key].score = result.score * semantic_weight * feedback_multiplier
            else:
                combined[key].score = max(
                    combined[key].score,
                    result.score * semantic_weight * feedback_multiplier
                )
        print('llllllllllllllllllllll')
        print(combined)
        # Add semantic results
        for result in semantic_results:
            key = (result.file_path, result.content[:100])  # Use path + preview as key
            if key not in combined:
                combined[key] = result
                combined[key].score = result.score * semantic_weight
            else:
                # Boost score if also in keyword results
                combined[key].score = (combined[key].score + result.score * semantic_weight) / 2

        # Add keyword results
        for result in keyword_results:
            key = (result.file_path, result.content[:100])
            if key not in combined:
                combined[key] = result
                combined[key].score = result.score * (1 - semantic_weight)
            else:
                # Boost score
                combined[key].score = (combined[key].score + result.score * (1 - semantic_weight)) / 2

        # Sort by score and return top_k
        sorted_results = sorted(combined.values(), key=lambda r: r.score, reverse=True)
        return sorted_results[:top_k]

    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        method: str = "hybrid",
        semantic_weight: float = 0.7
    ) -> list[SearchResult]:
        """
        Search the index.

        Args:
            query: Search query
            top_k: Number of results to return (defaults to config.search_top_k)
            method: Search method - "keyword", "semantic", or "hybrid"
            semantic_weight: Weight for semantic search in hybrid mode (0-1)

        Returns:
            List of search results
        """
        if top_k is None:
            top_k = self.config.search_top_k

        if method == "keyword":
            return self.keyword_search(query, top_k=top_k)
        elif method == "semantic":
            return self.semantic_search(query, top_k=top_k)
        elif method == "hybrid":
            return self.hybrid_search(query, top_k=top_k, semantic_weight=semantic_weight)
        else:
            raise ValueError(f"Unknown search method: {method}")
