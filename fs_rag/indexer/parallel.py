"""Parallel processing strategies using thread pools and process pools."""

import time
from pathlib import Path
from typing import Callable, Optional, List
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from threading import Lock
from dataclasses import replace

from fs_rag.indexer.strategy import ProcessingStrategy, ProcessingResult
from fs_rag.processor import DocumentChunk


class ThreadPoolStrategy(ProcessingStrategy):
    """Process files in parallel using a thread pool.
    
    Best for I/O-bound operations like file reading and network calls.
    Uses Python's ThreadPoolExecutor for concurrent processing.
    """

    def __init__(self, config, embeddings, vector_db, logger, max_workers: Optional[int] = None):
        """Initialize thread pool strategy.
        
        Args:
            max_workers: Maximum number of concurrent threads (default: from config)
        """
        super().__init__(config, embeddings, vector_db, logger)
        self.max_workers = max_workers or config.parallel_workers
        self.results_lock = Lock()

    def process_files(
        self,
        files: List[Path],
        file_hasher: Callable[[Path], str],
        process_file_func: Callable[[Path, Optional[Callable]], List[DocumentChunk]],
        progress_callback: Optional[Callable] = None,
        skip_file_ids: Optional[set] = None,
    ) -> List[ProcessingResult]:
        """Process files in parallel using thread pool."""
        skip_file_ids = skip_file_ids or set()
        results = []
        processed_count = 0
        failed_count = 0

        self.logger.info(
            f"[PARALLEL] Starting thread pool with {self.max_workers} workers for {len(files)} files"
        )

        # Filter files to process and create work items
        work_items = []
        skipped_results = []

        for idx, file_path in enumerate(files, start=1):
            file_id = file_hasher(file_path)

            if file_id in skip_file_ids:
                skipped_results.append(
                    ProcessingResult(
                        file_path=file_path,
                        chunks=[],
                        file_id=file_id,
                        status="skipped",
                        skipped=True,
                        processing_time=0.0,
                    )
                )
                continue

            work_items.append((idx, file_path, file_id))

        # Add skipped results first
        results.extend(skipped_results)

        # Process files in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_item = {
                executor.submit(
                    self._process_single_file,
                    idx,
                    file_path,
                    file_id,
                    process_file_func,
                    len(files),
                    progress_callback,
                ): (idx, file_path, file_id)
                for idx, file_path, file_id in work_items
            }

            # Process completed tasks as they finish
            for future in as_completed(future_to_item):
                idx, file_path, file_id = future_to_item[future]

                try:
                    result = future.result()
                    with self.results_lock:
                        results.append(result)
                        if result.status == "completed":
                            processed_count += 1
                        elif result.status == "failed":
                            failed_count += 1

                    if processed_count % self.config.progress_log_interval == 0:
                        self._log_batch_progress(processed_count, failed_count, len(work_items))

                except Exception as e:
                    self.logger.exception(f"[PARALLEL] Error in worker for {file_path}: {e}")
                    with self.results_lock:
                        result = ProcessingResult(
                            file_path=file_path,
                            chunks=[],
                            file_id=file_id,
                            status="failed",
                            error_message=f"Worker error: {str(e)}",
                            processing_time=0.0,
                        )
                        results.append(result)
                        failed_count += 1

        self.logger.info(
            f"[PARALLEL DONE] Processed {processed_count} files with {failed_count} errors"
        )

        return results

    def _process_single_file(
        self,
        idx: int,
        file_path: Path,
        file_id: str,
        process_file_func: Callable[[Path, Optional[Callable]], List[DocumentChunk]],
        total_files: int,
        progress_callback: Optional[Callable] = None,
    ) -> ProcessingResult:
        """Process a single file (runs in thread pool)."""
        file_start = time.time()

        self._log_file_progress(idx, total_files, file_path, "Processing")

        try:
            # Create progress callback with file index info
            wrapped_callback = self._create_progress_callback(
                progress_callback, idx, total_files
            )

            # Process file
            chunks = process_file_func(file_path, wrapped_callback)

            if not chunks:
                self._log_file_progress(idx, total_files, file_path, "No chunks created")
                return ProcessingResult(
                    file_path=file_path,
                    chunks=[],
                    file_id=file_id,
                    status="failed",
                    error_message="No chunks created",
                    processing_time=time.time() - file_start,
                )

            processing_time = time.time() - file_start
            self._log_file_progress(
                idx,
                total_files,
                file_path,
                f"Completed ({len(chunks)} chunks, {processing_time:.2f}s)",
            )

            return ProcessingResult(
                file_path=file_path,
                chunks=chunks,
                file_id=file_id,
                status="completed",
                processing_time=processing_time,
            )

        except Exception as e:
            processing_time = time.time() - file_start
            self.logger.exception(f"[FILE {idx}/{total_files}] Error processing {file_path}: {e}")
            return ProcessingResult(
                file_path=file_path,
                chunks=[],
                file_id=file_id,
                status="failed",
                error_message=str(e),
                processing_time=processing_time,
            )


class ProcessPoolStrategy(ProcessingStrategy):
    """Process files in parallel using a process pool.
    
    Better for CPU-bound operations, but has overhead for serialization.
    Note: This strategy is more suitable for operations that don't require
    shared services (embeddings, vector_db). Use ThreadPoolStrategy for
    typical indexing workloads.
    """

    def __init__(self, config, embeddings, vector_db, logger, max_workers: Optional[int] = None):
        """Initialize process pool strategy."""
        super().__init__(config, embeddings, vector_db, logger)
        self.max_workers = max_workers or config.parallel_workers

    def process_files(
        self,
        files: List[Path],
        file_hasher: Callable[[Path], str],
        process_file_func: Callable[[Path, Optional[Callable]], List[DocumentChunk]],
        progress_callback: Optional[Callable] = None,
        skip_file_ids: Optional[set] = None,
    ) -> List[ProcessingResult]:
        """Process files in parallel using process pool.
        
        Note: This is less practical for indexing due to GIL and serialization overhead.
        """
        self.logger.warning(
            "[PROCESS POOL] ProcessPoolStrategy is experimental and may have limited benefits "
            "due to GIL and serialization overhead. Consider ThreadPoolStrategy instead."
        )

        skip_file_ids = skip_file_ids or set()
        results = []

        # For process pools, we need to delegate carefully due to pickling requirements
        # In practice, ThreadPoolStrategy is more suitable for most indexing tasks
        # This implementation uses the same approach as ThreadPoolStrategy for now
        return ThreadPoolStrategy(self.config, self.embeddings, self.vector_db, self.logger,
                                 self.max_workers).process_files(
            files, file_hasher, process_file_func, progress_callback, skip_file_ids
        )
