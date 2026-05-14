"""Vector database abstraction for ChromaDB and Qdrant."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
import numpy as np
import json


from fs_rag.core import get_config, get_logger

logger = get_logger(__name__)


class VectorDB(ABC):
    """Base class for vector databases."""

    @abstractmethod
    def add(self, ids: list[str], embeddings: list[np.ndarray], metadatas: list[dict], documents: list[str]) -> None:
        """Add embeddings to the database."""
        pass

    @abstractmethod
    def search(self, embedding: np.ndarray, top_k: int = 5) -> list[dict]:
        """Search for similar embeddings."""
        pass

    @abstractmethod
    def delete(self, ids: list[str]) -> None:
        """Delete embeddings by ID."""
        pass

    @abstractmethod
    def get(self, ids: list[str]) -> list[dict]:
        """Get embeddings by ID."""
        pass

    @abstractmethod
    def count(self) -> int:
        """Get total number of embeddings."""
        pass

    @abstractmethod
    def get_chunks_by_filepath(self, filepath: str) -> list[dict]:
        """Get all chunks for a given filepath."""
        pass


class ChromaDBVectorDB(VectorDB):
    """ChromaDB implementation."""

    def __init__(self, path: Optional[str] = None, collection_name: str = "documents"):
        self.path = path or str(get_config().vector_db_path)
        self.collection_name = collection_name

        try:
            import chromadb
            self.client = chromadb.PersistentClient(path=self.path)
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
        except ImportError:
            logger.error("chromadb not installed. Install with: pip install chromadb")
            self.client = None
            self.collection = None

    def add(self, ids: list[str], embeddings: list[np.ndarray], metadatas: list[dict], documents: list[str]) -> None:
        if not self.collection:
            raise RuntimeError("ChromaDB collection not initialized")

        # Convert numpy arrays to lists for ChromaDB
        embeddings_list = [emb.tolist() if isinstance(emb, np.ndarray) else emb for emb in embeddings]

        self.collection.add(
            ids=ids,
            embeddings=embeddings_list,
            metadatas=metadatas,
            documents=documents
        )
        logger.debug(f"Added {len(ids)} documents to ChromaDB")

    def search(self, embedding: np.ndarray, top_k: int = 5) -> list[dict]:
        if not self.collection:
            raise RuntimeError("ChromaDB collection not initialized")

        embedding_list = embedding.tolist() if isinstance(embedding, np.ndarray) else embedding

        results = self.collection.query(
            query_embeddings=[embedding_list],
            n_results=top_k
        )

        # Format results
        formatted_results = []
        if results and results["ids"]:
            for i, doc_id in enumerate(results["ids"][0]):
                formatted_results.append({
                    "id": doc_id,
                    "document": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0.0,
                })

        return formatted_results

    def delete(self, ids: list[str]) -> None:
        if not self.collection:
            raise RuntimeError("ChromaDB collection not initialized")
        self.collection.delete(ids=ids)
        logger.debug(f"Deleted {len(ids)} documents from ChromaDB")

    def get(self, ids: list[str]) -> list[dict]:
        if not self.collection:
            raise RuntimeError("ChromaDB collection not initialized")
        results = self.collection.get(ids=ids)
        formatted_results = []
        for i, doc_id in enumerate(results["ids"]):
            formatted_results.append({
                "id": doc_id,
                "document": results["documents"][i] if results["documents"] else "",
                "metadata": results["metadatas"][i] if results["metadatas"] else {},
            })
        return formatted_results

    def count(self) -> int:
        if not self.collection:
            return 0
        return self.collection.count()

    def get_chunks_by_filepath(self, filepath: str) -> list[dict]:
        if not self.collection:
            raise RuntimeError("ChromaDB collection not initialized")
        
        results = self.collection.get(
            where={"filepath": filepath}
        )
        
        formatted_results = []
        for i, doc_id in enumerate(results["ids"]):
            formatted_results.append({
                "id": doc_id,
                "document": results["documents"][i] if results["documents"] else "",
                "metadata": results["metadatas"][i] if results["metadatas"] else {},
            })
        return formatted_results


class QdrantVectorDB(VectorDB):
    """Qdrant implementation."""

    def __init__(self, url: Optional[str] = None, api_key: Optional[str] = None, collection_name: str = "documents"):
        self.url = url or get_config().qdrant_url
        self.api_key = api_key or get_config().qdrant_api_key
        self.collection_name = collection_name

        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models

            self.client = QdrantClient(url=self.url, api_key=self.api_key)
            self.models = models
        except ImportError:
            logger.error("qdrant-client not installed. Install with: pip install qdrant-client")
            self.client = None
            self.models = None

    def _ensure_collection(self, vector_size: int) -> None:
        if not self.client or not self.models:
            raise RuntimeError("Qdrant client not initialized")

        # Check if collection exists
        try:
            self.client.get_collection(self.collection_name)
        except Exception:
            # Create collection if it doesn't exist
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=self.models.VectorParams(size=vector_size, distance=self.models.Distance.COSINE),
            )

    def add(self, ids: list[str], embeddings: list[np.ndarray], metadatas: list[dict], documents: list[str]) -> None:

        qdrant_payload_max_size = 33554423  # ~32MB

        if not self.client or not self.models:
            raise RuntimeError("Qdrant client not initialized")

        if not embeddings:
            return

        # Ensure collection exists with proper vector size
        vector_size = embeddings[0].shape[0] if isinstance(embeddings[0], np.ndarray) else len(embeddings[0])
        self._ensure_collection(vector_size)

        # Convert to Qdrant format
        points = []
        for i, doc_id in enumerate(ids):
            vector = embeddings[i].tolist() if isinstance(embeddings[i], np.ndarray) else embeddings[i]
            payload = {
                "document": documents[i],
                **metadatas[i]
            }

            point = self.models.PointStruct(
                id=hash(doc_id) % (2**31),
                vector=vector,
                payload=payload
            )

            points.append(point)


        point_chunks = []
        current_chunk = []
        current_size = 0

        for p in points:
            # Convert to dict → JSON → bytes
            p_dict = {
                "id": p.id,
                "vector": p.vector,
                "payload": p.payload
            }

            p_size = len(json.dumps(p_dict).encode("utf-8"))

            # If adding this point exceeds max size → start new chunk
            if current_size + p_size > qdrant_payload_max_size:
                point_chunks.append(current_chunk)
                current_chunk = []
                current_size = 0

            current_chunk.append(p)
            current_size += p_size

        # Add last chunk
        if current_chunk:
            point_chunks.append(current_chunk)

        # Upload chunks
        for chunk in point_chunks:
            self.client.upsert(collection_name=self.collection_name, points=chunk)
            logger.debug(f"Added {len(chunk)} documents to Qdrant")

    def search(self, embedding: np.ndarray, top_k: int = 5) -> list[dict]:
        if not self.client or not self.models:
            raise RuntimeError("Qdrant client not initialized")

        vector = embedding.tolist() if isinstance(embedding, np.ndarray) else embedding

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            limit=top_k
        )

        formatted_results = []
        for result in results.points:
            formatted_results.append({
                "id": str(result.id),
                "document": result.payload.get("document", ""),
                "metadata": {k: v for k, v in result.payload.items() if k != "document"},
                "distance": result.score,
            })

        return formatted_results

    def delete(self, ids: list[str]) -> None:
        if not self.client:
            raise RuntimeError("Qdrant client not initialized")
        numeric_ids = [hash(doc_id) % (2**31) for doc_id in ids]
        self.client.delete(collection_name=self.collection_name, points_selector=self.models.PointIdsList(ids=numeric_ids))
        logger.debug(f"Deleted {len(ids)} documents from Qdrant")

    def get(self, ids: list[str]) -> list[dict]:
        if not self.client:
            raise RuntimeError("Qdrant client not initialized")

        numeric_ids = [hash(doc_id) % (2**31) for doc_id in ids]
        results = self.client.retrieve(collection_name=self.collection_name, ids=numeric_ids)

        formatted_results = []
        for result in results:
            formatted_results.append({
                "id": str(result.id),
                "document": result.payload.get("document", ""),
                "metadata": {k: v for k, v in result.payload.items() if k != "document"},
            })
        return formatted_results

    def count(self) -> int:
        if not self.client:
            return 0
        try:
            collection_info = self.client.get_collection(self.collection_name)
            return collection_info.points_count
        except Exception:
            return 0

    def get_chunks_by_filepath(self, filepath: str) -> list[dict]:
        if not self.client or not self.models:
            raise RuntimeError("Qdrant client not initialized")
            
        results = self.client.scroll(
            collection_name=self.collection_name,
            limit=10000,
            scroll_filter=self.models.Filter(
                must=[
                    self.models.FieldCondition(
                        key="file_path",  # ✅ FIX HERE
                        match=self.models.MatchValue(value=filepath)
                    )
                ]
            )
        )
        
        formatted_results = []
        if results[0]:
            for result in results[0]:
                formatted_results.append({
                    "id": str(result.id),
                    "document": result.payload.get("document", ""),
                    "metadata": {k: v for k, v in result.payload.items() if k != "document"},
                })

        return formatted_results


def get_vector_db() -> VectorDB:
    """Get the configured vector database."""
    config = get_config()
    if config.vector_db_type.value == "chromadb":
        return ChromaDBVectorDB()
    elif config.vector_db_type.value == "qdrant":
        return QdrantVectorDB()
    else:
        raise ValueError(f"Unknown vector DB type: {config.vector_db_type}")
