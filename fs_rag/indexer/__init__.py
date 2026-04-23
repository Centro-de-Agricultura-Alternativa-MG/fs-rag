"""Filesystem indexer for building document databases."""

from pathlib import Path
from typing import Optional, Callable
import sqlite3
from datetime import datetime

from fs_rag.core import get_config, get_logger
from fs_rag.core.embeddings import get_embeddings_provider
from fs_rag.core.vector_db import get_vector_db
from fs_rag.processor import ProcessorFactory, DocumentChunk

logger = get_logger(__name__)


class FilesystemIndexer:
    """Indexes files in a filesystem for search and retrieval."""

    def __init__(self):
        self.config = get_config()
        self.embeddings = get_embeddings_provider()
        self.vector_db = get_vector_db()
        self.db_path = self.config.index_dir / "index.db"
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database for metadata."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL UNIQUE,
                size INTEGER,
                modified_time REAL,
                indexed_time REAL,
                content_hash TEXT,
                is_indexed BOOLEAN DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                file_id TEXT NOT NULL,
                chunk_index INTEGER,
                content TEXT,
                FOREIGN KEY (file_id) REFERENCES files(id)
            )
        """)
        conn.commit()
        conn.close()

    def _get_file_hash(self, file_path: Path) -> str:
        """Get a hash of file path and modified time."""
        import hashlib
        stat = file_path.stat()
        data = f"{file_path}:{stat.st_mtime}:{stat.st_size}".encode()
        return hashlib.md5(data).hexdigest()

    def _is_processable(self, file_path: Path) -> bool:
        """Check if a file can be processed."""
        if file_path.is_dir():
            return False
        if file_path.name.startswith("."):
            return False
        if file_path.suffix.lower() in {".pyc", ".o", ".so", ".exe", ".bin"}:
            return False
        return ProcessorFactory.can_process(file_path)

    def _scan_directory(self, root_dir: Path) -> list[Path]:
        """Recursively scan for processable files."""
        files = []
        try:
            for item in root_dir.rglob("*"):
                if self._is_processable(item):
                    files.append(item)
        except PermissionError as e:
            logger.warning(f"Permission denied scanning {root_dir}: {e}")
        return files

    def _process_file(self, file_path: Path, progress_callback: Optional[Callable] = None) -> list[DocumentChunk]:
        """Process a file and return chunks."""
        processor = ProcessorFactory.get_processor(file_path)
        if not processor:
            logger.debug(f"No processor found for {file_path}")
            return []

        try:
            text = processor.extract_text(file_path)
            if not text or len(text.strip()) < 10:
                logger.debug(f"Extracted text too short from {file_path}")
                return []

            chunks_text = processor.chunk_text(
                text,
                chunk_size=self.config.chunk_size,
                chunk_overlap=self.config.chunk_overlap
            )

            chunks = []
            for i, chunk_text in enumerate(chunks_text):
                chunk = DocumentChunk(
                    content=chunk_text,
                    source_file=file_path,
                    chunk_index=i,
                    metadata={
                        "file_path": str(file_path),
                        "file_name": file_path.name,
                        "chunk_index": i,
                        "file_size": file_path.stat().st_size,
                    }
                )
                chunks.append(chunk)

            if progress_callback:
                progress_callback(file_path, len(chunks))

            return chunks
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            return []

    def index_directory(
        self,
        root_dir: Path,
        force_reindex: bool = False,
        progress_callback: Optional[Callable] = None
    ) -> dict:
        """Index all files in a directory."""
        root_dir = Path(root_dir)
        if not root_dir.exists():
            raise ValueError(f"Directory does not exist: {root_dir}")

        logger.info(f"Starting indexing of {root_dir}")

        # Scan for files
        files = self._scan_directory(root_dir)
        logger.info(f"Found {len(files)} processable files")

        # Get connection
        conn = sqlite3.connect(self.db_path)

        stats = {
            "files_processed": 0,
            "chunks_created": 0,
            "documents_embedded": 0,
            "errors": 0,
        }

        try:
            for file_path in files:
                file_id = self._get_file_hash(file_path)

                # Check if already indexed
                cursor = conn.execute("SELECT is_indexed FROM files WHERE id = ?", (file_id,))
                existing = cursor.fetchone()

                if existing and existing[0] and not force_reindex:
                    logger.debug(f"Skipping already indexed file: {file_path}")
                    continue

                # Process file
                chunks = self._process_file(file_path, progress_callback)
                if not chunks:
                    stats["errors"] += 1
                    continue

                # Store in vector DB
                chunk_ids = [f"{file_id}:{i}" for i in range(len(chunks))]
                embeddings = self.embeddings.embed_batch([c.content for c in chunks])

                self.vector_db.add(
                    ids=chunk_ids,
                    embeddings=embeddings,
                    metadatas=[c.metadata for c in chunks],
                    documents=[c.content for c in chunks]
                )

                # Update metadata DB
                cursor = conn.execute("SELECT id FROM files WHERE id = ?", (file_id,))
                if cursor.fetchone():
                    conn.execute(
                        "UPDATE files SET is_indexed = 1, indexed_time = ? WHERE id = ?",
                        (datetime.now().timestamp(), file_id)
                    )
                else:
                    conn.execute(
                        "INSERT INTO files (id, path, size, modified_time, indexed_time, content_hash, is_indexed) VALUES (?, ?, ?, ?, ?, ?, 1)",
                        (file_id, str(file_path), file_path.stat().st_size, file_path.stat().st_mtime, datetime.now().timestamp(), file_id)
                    )

                stats["files_processed"] += 1
                stats["chunks_created"] += len(chunks)
                stats["documents_embedded"] += len(chunks)

            conn.commit()
        finally:
            conn.close()

        logger.info(f"Indexing complete: {stats}")
        return stats

    def get_index_stats(self) -> dict:
        """Get statistics about the index."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        stats = {
            "total_files": cursor.execute("SELECT COUNT(*) FROM files").fetchone()[0],
            "indexed_files": cursor.execute("SELECT COUNT(*) FROM files WHERE is_indexed = 1").fetchone()[0],
            "total_chunks": cursor.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
            "vector_db_size": self.vector_db.count(),
        }

        conn.close()
        return stats

    def clear_index(self) -> None:
        """Clear all indexed data."""
        logger.warning("Clearing index...")

        # Clear vector DB by removing all documents
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM files")
        file_ids = [row[0] for row in cursor.fetchall()]

        if file_ids:
            all_chunk_ids = []
            for file_id in file_ids:
                cursor.execute("SELECT id FROM chunks WHERE file_id = ?", (file_id,))
                chunk_ids = [row[0] for row in cursor.fetchall()]
                all_chunk_ids.extend(chunk_ids)

            if all_chunk_ids:
                self.vector_db.delete(all_chunk_ids)

        # Clear metadata DB
        conn.execute("DELETE FROM chunks")
        conn.execute("DELETE FROM files")
        conn.commit()
        conn.close()

        logger.info("Index cleared")
