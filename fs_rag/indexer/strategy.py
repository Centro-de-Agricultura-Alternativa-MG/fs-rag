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
    - Distributed: Delegate to remote workers
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
