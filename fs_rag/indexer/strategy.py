"""Processing strategies for indexing files with different parallelism approaches."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Optional, List
from dataclasses import dataclass
from datetime import datetime
import sqlite3

from fs_rag.processor import DocumentChunk


@dataclass
class ProcessingResult:
    """Result of processing a single file."""
    file_path: Path
    chunks: List[DocumentChunk]
    file_id: str
    status: str  # "completed", "failed", "skipped"
    error_message: Optional[str] = None
    processing_time: float = 0.0
    skipped: bool = False


class ProcessingStrategy(ABC):
    """Abstract base class for file processing strategies.
    
    Strategies differ in parallelism approach:
    - Sequential: Process files one at a time (original behavior)
    - Parallel (threads/processes): Process multiple files concurrently
    
    Distributed processing (remote workers) is independent and works with any strategy.
    When DISTRIBUTED_PROCESSING_ENABLED=true, the strategy will use remote workers
    for the actual file processing, while maintaining the same dispatch method.
    """

    def __init__(self, config, embeddings, vector_db, logger):
        """Initialize strategy with shared services.
        
        Args:
            config: Application configuration
            embeddings: Embeddings provider
            vector_db: Vector database
            logger: Logger instance
        """
        self.config = config
        self.embeddings = embeddings
        self.vector_db = vector_db
        self.logger = logger
        self._remote_worker_client = None
        self._init_distributed_client()

    def _init_distributed_client(self):
        """Initialize distributed client if distributed processing is enabled."""
        if not self.config.distributed_processing_enabled:
            return
        
        try:
            from fs_rag.indexer.distributed import RemoteWorkerClient
            # For now, use the first worker URL if multiple are configured
            urls = [url.strip() for url in self.config.remote_worker_urls.split(",") if url.strip()]
            if urls:
                self._remote_worker_client = RemoteWorkerClient(
                    urls[0],
                    timeout=self.config.remote_worker_timeout,
                    retries=self.config.remote_worker_retries,
                    logger=self.logger,
                )
                self.logger.info(f"[DISTRIBUTED] Initialized remote worker client: {urls[0]}")
        except (ImportError, Exception) as e:
            self.logger.warning(f"[DISTRIBUTED] Failed to initialize remote worker client: {e}")
            self._remote_worker_client = None

    def _should_use_distributed(self) -> bool:
        """Check if distributed processing is enabled and client is available."""
        return self.config.distributed_processing_enabled and self._remote_worker_client is not None

    @abstractmethod
    def process_files(
        self,
        files: List[Path],
        file_hasher: Callable[[Path], str],
        process_file_func: Callable[[Path, Optional[Callable]], List[DocumentChunk]],
        progress_callback: Optional[Callable] = None,
        skip_file_ids: Optional[set] = None,
    ) -> List[ProcessingResult]:
        """Process a list of files according to strategy.
        
        Args:
            files: List of file paths to process
            file_hasher: Function to generate file hash/id
            process_file_func: Function to process individual file (returns chunks)
            progress_callback: Optional callback for progress updates
            skip_file_ids: Set of file IDs to skip (already processed)
        
        Returns:
            List of ProcessingResult objects
        """
        pass

    def _process_file_with_distributed(
        self, 
        file_path: Path,
        local_process_func: Callable[[Path, Optional[Callable]], List[DocumentChunk]],
        progress_callback: Optional[Callable] = None
    ) -> Optional[List[DocumentChunk]]:
        """Process a single file using distributed worker if available.
        
        Args:
            file_path: Path to file to process
            local_process_func: Local fallback processing function
            progress_callback: Optional progress callback
        
        Returns:
            List of chunks or None if distributed processing failed
        """
        if not self._should_use_distributed():
            return None
        
        try:
            chunks_data = self._remote_worker_client.process_file(
                str(file_path),
                chunk_size=self.config.chunk_size,
                chunk_overlap=self.config.chunk_overlap,
            )
            
            if chunks_data:
                self.logger.debug(f"[DISTRIBUTED] Successfully processed {file_path} with remote worker")
                # Convert chunk dicts back to DocumentChunk objects
                chunks = [
                    DocumentChunk(
                        content=chunk_data.get("content", ""),
                        metadata=chunk_data.get("metadata", {}),
                    )
                    for chunk_data in chunks_data
                ]
                return chunks
        except Exception as e:
            self.logger.debug(f"[DISTRIBUTED] Remote worker processing failed for {file_path}: {e}")
        
        return None

    def _create_progress_callback(
        self,
        progress_callback: Optional[Callable],
        current_index: int,
        total_files: int,
    ) -> Optional[Callable]:
        """Create a wrapped progress callback that includes file count info."""
        if progress_callback is None:
            return None

        def wrapped_callback(file_path: Path, chunk_count: int):
            # Progress callback receives: (file_path, chunk_count, file_index, total_files)
            progress_callback(file_path, chunk_count, current_index, total_files)

        return wrapped_callback

    def _log_file_progress(self, current: int, total: int, file_path: Path, status: str):
        """Log progress for a file with consistent formatting."""
        self.logger.info(f"[FILE {current}/{total}] {status}: {file_path}")

    def _log_batch_progress(self, completed: int, failed: int, total: int):
        """Log batch progress summary."""
        percentage = int((completed / total) * 100) if total > 0 else 0
        self.logger.debug(
            f"[BATCH PROGRESS] Completed: {completed}/{total} ({percentage}%) | Failed: {failed}"
        )
