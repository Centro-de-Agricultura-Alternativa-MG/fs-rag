"""Distributed processing strategy using remote workers."""

import json
import time
from pathlib import Path
from typing import Callable, Optional, List
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from fs_rag.indexer.strategy import ProcessingStrategy, ProcessingResult
from fs_rag.processor import DocumentChunk, ProcessorFactory


class RemoteWorkerClient:
    """Client for communicating with remote workers.
    
    Remote workers are expected to have an endpoint like:
    POST /process
    Body: {"filepath": "/path/to/file", "chunk_size": 512, "chunk_overlap": 50}
    Response: {"chunks": [{"content": "...", "metadata": {...}}, ...], "error": null}
    """

    def __init__(self, worker_url: str, timeout: int = 30, retries: int = 2, logger=None):
        """Initialize remote worker client.
        
        Args:
            worker_url: Base URL of remote worker
            timeout: Request timeout in seconds
            retries: Number of retries on failure
            logger: Logger instance
        """
        self.worker_url = worker_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.logger = logger
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create a requests session with connection pooling and retry strategy."""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=self.retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"]
        )
        
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=4,
            pool_maxsize=4
        )
        
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session

    def process_file(
        self, filepath: str, chunk_size: int, chunk_overlap: int
    ) -> Optional[List[dict]]:
        """Send file to remote worker for processing.
        
        Args:
            filepath: Path to file to process
            chunk_size: Chunk size for text splitting
            chunk_overlap: Overlap between chunks
        
        Returns:
            List of chunk dictionaries or None on failure
        """
        endpoint = f"{self.worker_url}/process"
        payload = {
            "filepath": filepath,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        }

        attempt = 0
        while attempt <= self.retries:
            try:
                response = self.session.post(
                    endpoint, json=payload, timeout=self.timeout
                )
                response.raise_for_status()

                data = response.json()
                if data.get("error"):
                    if self.logger:
                        self.logger.error(
                            f"Worker error for {filepath}: {data.get('error')}"
                        )
                    return None

                return data.get("chunks", [])

            except requests.Timeout:
                if self.logger:
                    self.logger.warning(
                        f"Worker timeout for {filepath} (attempt {attempt + 1}/{self.retries + 1})"
                    )
                attempt += 1
                if attempt > self.retries:
                    return None
                time.sleep(min(2 ** attempt, 10))

            except requests.RequestException as e:
                if self.logger:
                    self.logger.warning(
                        f"Worker request failed for {filepath} (attempt {attempt + 1}/{self.retries + 1}): {e}"
                    )
                attempt += 1
                if attempt > self.retries:
                    return None
                time.sleep(min(2 ** attempt, 10))

            except json.JSONDecodeError as e:
                if self.logger:
                    self.logger.error(f"Invalid response from worker for {filepath}: {e}")
                return None

        return None


class RemoteWorkerStrategy(ProcessingStrategy):
    """Process files using distributed remote workers.
    
    Delegates file processing to remote workers via HTTP/RPC.
    Workers must be configured in REMOTE_WORKER_URLS environment variable.
    """

    def __init__(self, config, embeddings, vector_db, logger):
        """Initialize distributed strategy with remote workers."""
        super().__init__(config, embeddings, vector_db, logger)
        self.worker_urls = self._parse_worker_urls()
        self.clients = [
            RemoteWorkerClient(
                url,
                timeout=config.remote_worker_timeout,
                retries=config.remote_worker_retries,
                logger=logger,
            )
            for url in self.worker_urls
        ]

        if not self.clients:
            raise ValueError("No remote worker URLs configured (REMOTE_WORKER_URLS)")

        self.logger.info(
            f"[DISTRIBUTED] Initialized with {len(self.clients)} remote workers: {self.worker_urls}"
        )

    def _parse_worker_urls(self) -> List[str]:
        """Parse comma-separated worker URLs from config."""
        urls_str = self.config.remote_worker_urls.strip()
        if not urls_str:
            return []

        urls = [url.strip() for url in urls_str.split(",") if url.strip()]
        return urls

    def process_files(
        self,
        files: List[Path],
        file_hasher: Callable[[Path], str],
        process_file_func: Callable[[Path, Optional[Callable]], List[DocumentChunk]],
        progress_callback: Optional[Callable] = None,
        skip_file_ids: Optional[set] = None,
    ) -> List[ProcessingResult]:
        """Process files using remote workers."""
        skip_file_ids = skip_file_ids or set()
        results = []
        processed_count = 0
        failed_count = 0

        self.logger.info(
            f"[DISTRIBUTED] Starting distributed processing for {len(files)} files"
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

        # Calculate max concurrent workers respecting PARALLEL_WORKERS config
        num_workers = len(self.clients)
        base_workers = min(self.config.parallel_workers, 16)
        max_concurrent = max(base_workers, num_workers * 2)

        self.logger.info(
            f"[DISTRIBUTED] Using {max_concurrent} concurrent workers ({num_workers} remote + {base_workers} config)"
        )

        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            future_to_item = {}

            for idx, file_path, file_id in work_items:
                client = self.clients[worker_index % len(self.clients)]
                worker_index += 1

                future = executor.submit(
                    self._process_with_remote_worker,
                    idx,
                    file_path,
                    file_id,
                    client,
                    len(files),
                    process_file_func,
                    progress_callback,
                )
                future_to_item[future] = (idx, file_path, file_id)

            # Process completed tasks as they finish with timeout per batch
            batch_timeout = self.config.remote_worker_timeout + 10
            for future in as_completed(future_to_item, timeout=batch_timeout):
                idx, file_path, file_id = future_to_item[future]

                try:
                    result = future.result(timeout=5)
                    results.append(result)
                    if result.status == "completed":
                        processed_count += 1
                    elif result.status == "failed":
                        failed_count += 1

                    if processed_count % self.config.progress_log_interval == 0:
                        self._log_batch_progress(processed_count, failed_count, len(work_items))

                except Exception as e:
                    self.logger.exception(
                        f"[DISTRIBUTED] Error in worker task for {file_path}: {e}"
                    )
                    result = ProcessingResult(
                        file_path=file_path,
                        chunks=[],
                        file_id=file_id,
                        status="failed",
                        error_message=f"Worker task error: {str(e)}",
                        processing_time=0.0,
                    )
                    results.append(result)
                    failed_count += 1

        self.logger.info(
            f"[DISTRIBUTED DONE] Processed {processed_count} files with {failed_count} errors"
        )

        return results

    def _process_with_remote_worker(
        self,
        idx: int,
        file_path: Path,
        file_id: str,
        client: RemoteWorkerClient,
        total_files: int,
        fallback_func: Callable[[Path, Optional[Callable]], List[DocumentChunk]],
        progress_callback: Optional[Callable] = None,
    ) -> ProcessingResult:
        """Process file with remote worker, with fallback to local processing."""
        file_start = time.time()

        self._log_file_progress(idx, total_files, file_path, "Sending to remote worker")

        try:
            # Try remote worker first
            chunk_dicts = client.process_file(
                str(file_path),
                self.config.chunk_size,
                self.config.chunk_overlap,
            )

            if chunk_dicts is not None:
                # Convert chunk dicts back to DocumentChunk objects
                chunks = self._deserialize_chunks(chunk_dicts, file_path)

                processing_time = time.time() - file_start
                self._log_file_progress(
                    idx,
                    total_files,
                    file_path,
                    f"Remote completed ({len(chunks)} chunks, {processing_time:.2f}s)",
                )

                # Call progress callback if provided
                if progress_callback:
                    wrapped_callback = self._create_progress_callback(
                        progress_callback, idx, total_files
                    )
                    if wrapped_callback:
                        wrapped_callback(file_path, len(chunks))

                return ProcessingResult(
                    file_path=file_path,
                    chunks=chunks,
                    file_id=file_id,
                    status="completed",
                    processing_time=processing_time,
                )

            # Fallback to local processing if remote failed
            self.logger.warning(
                f"[DISTRIBUTED] Remote processing failed for {file_path}, falling back to local"
            )

            wrapped_callback = self._create_progress_callback(
                progress_callback, idx, total_files
            )
            chunks = fallback_func(file_path, wrapped_callback)

            if not chunks:
                self._log_file_progress(idx, total_files, file_path, "No chunks created (local fallback)")
                return ProcessingResult(
                    file_path=file_path,
                    chunks=[],
                    file_id=file_id,
                    status="failed",
                    error_message="Remote worker failed and local fallback produced no chunks",
                    processing_time=time.time() - file_start,
                )

            processing_time = time.time() - file_start
            self._log_file_progress(
                idx,
                total_files,
                file_path,
                f"Local fallback completed ({len(chunks)} chunks, {processing_time:.2f}s)",
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
            self.logger.exception(
                f"[FILE {idx}/{total_files}] Error in distributed processing {file_path}: {e}"
            )
            return ProcessingResult(
                file_path=file_path,
                chunks=[],
                file_id=file_id,
                status="failed",
                error_message=str(e),
                processing_time=processing_time,
            )

    def _deserialize_chunks(self, chunk_dicts: List[dict], file_path: Path) -> List[DocumentChunk]:
        """Convert chunk dictionaries from remote worker to DocumentChunk objects.
        
        Expected format from remote worker:
        {
            "content": "chunk text",
            "metadata": {
                "file_path": "...",
                "file_name": "...",
                "chunk_index": 0,
                ...
            }
        }
        """
        chunks = []

        for i, chunk_dict in enumerate(chunk_dicts):
            try:
                chunk = DocumentChunk(
                    content=chunk_dict.get("content", ""),
                    source_file=file_path,
                    chunk_index=i,
                    metadata=chunk_dict.get("metadata", {
                        "file_path": str(file_path),
                        "file_name": file_path.name,
                        "chunk_index": i,
                        "file_size": file_path.stat().st_size if file_path.exists() else 0,
                    }),
                )
                chunks.append(chunk)
            except Exception as e:
                self.logger.error(f"Error deserializing chunk {i} from remote worker: {e}")
                continue

        return chunks
