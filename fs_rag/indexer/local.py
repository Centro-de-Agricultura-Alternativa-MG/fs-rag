"""Sequential/Local processing strategy - original behavior maintained."""

import time
from pathlib import Path
from typing import Callable, Optional, List

from fs_rag.indexer.strategy import ProcessingStrategy, ProcessingResult
from fs_rag.processor import DocumentChunk


class LocalSequentialStrategy(ProcessingStrategy):
    """Process files sequentially, one at a time (original behavior).
    
    This is the default strategy and maintains backward compatibility.
    """

    def process_files(
        self,
        files: List[Path],
        file_hasher: Callable[[Path], str],
        process_file_func: Callable[[Path, Optional[Callable]], List[DocumentChunk]],
        progress_callback: Optional[Callable] = None,
        skip_file_ids: Optional[set] = None,
    ) -> List[ProcessingResult]:
        """Process files sequentially, one at a time."""
        skip_file_ids = skip_file_ids or set()
        results = []

        for idx, file_path in enumerate(files, start=1):
            file_start = time.time()
            file_id = file_hasher(file_path)

            # Check if should skip
            if file_id in skip_file_ids:
                self._log_file_progress(idx, len(files), file_path, "SKIP (already processed)")
                result = ProcessingResult(
                    file_path=file_path,
                    chunks=[],
                    file_id=file_id,
                    status="skipped",
                    skipped=True,
                    processing_time=0.0,
                )
                results.append(result)
                continue

            self._log_file_progress(idx, len(files), file_path, "Processing")

            try:
                # Create progress callback with file index info
                wrapped_callback = self._create_progress_callback(
                    progress_callback, idx, len(files)
                )

                # Try distributed processing first if enabled
                chunks = None
                if self._should_use_distributed():
                    self.logger.debug(f"[DISTRIBUTED] Attempting to process {file_path} with remote worker")
                    chunks = self._process_file_with_distributed(file_path, process_file_func, wrapped_callback)
                
                # Fall back to local processing if distributed failed or disabled
                if chunks is None:
                    chunks = process_file_func(file_path, wrapped_callback)

                if not chunks:
                    self._log_file_progress(idx, len(files), file_path, "No chunks created")
                    result = ProcessingResult(
                        file_path=file_path,
                        chunks=[],
                        file_id=file_id,
                        status="failed",
                        error_message="No chunks created",
                        processing_time=time.time() - file_start,
                    )
                    results.append(result)
                    continue

                processing_time = time.time() - file_start
                self._log_file_progress(
                    idx,
                    len(files),
                    file_path,
                    f"Completed ({len(chunks)} chunks, {processing_time:.2f}s)",
                )

                result = ProcessingResult(
                    file_path=file_path,
                    chunks=chunks,
                    file_id=file_id,
                    status="completed",
                    processing_time=processing_time,
                )
                results.append(result)

            except Exception as e:
                processing_time = time.time() - file_start
                self.logger.exception(f"[FILE {idx}/{len(files)}] Error processing {file_path}: {e}")
                result = ProcessingResult(
                    file_path=file_path,
                    chunks=[],
                    file_id=file_id,
                    status="failed",
                    error_message=str(e),
                    processing_time=processing_time,
                )
                results.append(result)

        return results
