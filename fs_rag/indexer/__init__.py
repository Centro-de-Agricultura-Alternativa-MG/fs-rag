"""Filesystem indexer for building document databases."""

from pathlib import Path
from typing import Optional, Callable, List
import sqlite3
from datetime import datetime
import time
import json

from fs_rag.core import get_config, get_logger
from fs_rag.core.embeddings import get_embeddings_provider
from fs_rag.core.vector_db import get_vector_db
from fs_rag.processor import ProcessorFactory, DocumentChunk
from fs_rag.indexer.strategy import ProcessingStrategy
from fs_rag.indexer.local import LocalSequentialStrategy
from fs_rag.indexer.parallel import ThreadPoolStrategy, ProcessPoolStrategy
from fs_rag.core.config import ParallelStrategy

# Initialize config early to set up logging
config = get_config()
config.ensure_dirs()
logger = get_logger(__name__, level=config.log_level, log_file=config.logs_dir / "indexer.log")


class FilesystemIndexer:
    """Indexes files in a filesystem for search and retrieval."""

    def __init__(self):
        self.config = get_config()
        self.embeddings = get_embeddings_provider()
        self.vector_db = get_vector_db()
        self.db_path = self.config.index_dir / "index.db"
        self._init_db()
        self.strategy = self._create_strategy()

    def _create_strategy(self) -> ProcessingStrategy:
        """Create appropriate processing strategy based on PARALLEL_STRATEGY configuration.
        
        The strategy determines HOW files are dispatched (sequential, threads, processes).
        The DISTRIBUTED_PROCESSING_ENABLED config determines WHERE they are processed (local or remote).
        These are independent and work together.
        
        Returns:
            ProcessingStrategy instance
        """
        # Determine strategy based on PARALLEL_STRATEGY (independent of distributed setting)
        if self.config.parallel_processing_enabled:
            if self.config.parallel_strategy == ParallelStrategy.PROCESSES:
                logger.info(
                    "[STRATEGY] Using ProcessPoolStrategy (parallel processes). "
                    f"Distributed workers: {'ENABLED' if self.config.distributed_processing_enabled else 'disabled'}"
                )
                return ProcessPoolStrategy(
                    self.config, self.embeddings, self.vector_db, logger
                )
            elif self.config.parallel_strategy in (ParallelStrategy.THREADS, ParallelStrategy.ASYNC):
                logger.info(
                    "[STRATEGY] Using ThreadPoolStrategy (parallel threads). "
                    f"Distributed workers: {'ENABLED' if self.config.distributed_processing_enabled else 'disabled'}"
                )
                return ThreadPoolStrategy(
                    self.config, self.embeddings, self.vector_db, logger
                )

        # Default to sequential processing
        logger.info(
            "[STRATEGY] Using LocalSequentialStrategy (sequential). "
            f"Distributed workers: {'ENABLED' if self.config.distributed_processing_enabled else 'disabled'}"
        )
        return LocalSequentialStrategy(
            self.config, self.embeddings, self.vector_db, logger
        )

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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS indexing_progress (
                session_id TEXT NOT NULL,
                file_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                processed_at REAL,
                error_message TEXT,
                PRIMARY KEY (session_id, file_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS indexing_sessions (
                session_id TEXT PRIMARY KEY,
                root_dir TEXT NOT NULL,
                started_at REAL NOT NULL,
                completed_at REAL,
                force_reindex BOOLEAN DEFAULT 0,
                total_files INTEGER,
                total_errors INTEGER,
                status TEXT DEFAULT 'in_progress'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS directory_scans (
                scan_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                root_dir TEXT NOT NULL,
                file_paths TEXT NOT NULL,
                scanned_at REAL NOT NULL,
                file_count INTEGER,
                FOREIGN KEY (session_id) REFERENCES indexing_sessions(session_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflow_state (
                session_id TEXT NOT NULL,
                file_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                stage TEXT NOT NULL,
                stage_status TEXT DEFAULT 'pending',
                completed_at REAL,
                data TEXT,
                error_message TEXT,
                PRIMARY KEY (session_id, file_id, stage),
                FOREIGN KEY (session_id) REFERENCES indexing_sessions(session_id)
            )
        """)
        conn.commit()
        conn.close()

    def _get_file_hash(self, file_path: Path) -> str:
        """Get a hash of file path and modified time."""
        import hashlib
        try:
            stat = file_path.stat()
            data = f"{file_path}:{stat.st_mtime}:{stat.st_size}".encode()
        except (FileNotFoundError, OSError) as e:
            # If file doesn't exist, use path only
            logger.warning(f"File not found or inaccessible for hashing: {file_path} - {e}")
            data = f"{file_path}:0:0".encode()
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

    def _create_session_id(self, root_dir: Path) -> str:
        """Create a unique session ID for this indexing run."""
        import hashlib
        timestamp = str(datetime.now().timestamp())
        data = f"{root_dir}:{timestamp}".encode()
        return hashlib.md5(data).hexdigest()

    def _start_indexing_session(self, conn: sqlite3.Connection, session_id: str, root_dir: Path, force_reindex: bool, total_files: int) -> None:
        """Record the start of an indexing session."""
        conn.execute("""
            INSERT OR REPLACE INTO indexing_sessions 
            (session_id, root_dir, started_at, force_reindex, total_files, status) 
            VALUES (?, ?, ?, ?, ?, 'in_progress')
        """, (session_id, str(root_dir), datetime.now().timestamp(), force_reindex, total_files))
        conn.commit()

    def _end_indexing_session(self, conn: sqlite3.Connection, session_id: str, total_errors: int) -> None:
        """Record the completion of an indexing session."""
        conn.execute("""
            UPDATE indexing_sessions 
            SET status = 'completed', completed_at = ?, total_errors = ?
            WHERE session_id = ?
        """, (datetime.now().timestamp(), total_errors, session_id))
        conn.commit()

    def _get_completed_files(self, conn: sqlite3.Connection, session_id: str) -> set:
        """Get the set of file IDs already processed in this session."""
        cursor = conn.execute(
            "SELECT file_id FROM indexing_progress WHERE session_id = ? AND status = 'completed'",
            (session_id,)
        )
        return {row[0] for row in cursor.fetchall()}

    def _mark_file_progress(self, conn: sqlite3.Connection, session_id: str, file_id: str, file_path: Path, status: str, error_message: str = None) -> None:
        """Record the processing status of a file."""
        conn.execute("""
            INSERT OR REPLACE INTO indexing_progress 
            (session_id, file_id, file_path, status, processed_at, error_message) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, file_id, str(file_path), status, datetime.now().timestamp(), error_message))

    def _batch_commit(self, conn: sqlite3.Connection, batch_size: int = 10, current_count: int = 0) -> bool:
        """Commit changes in batches to balance persistence vs performance."""
        if current_count > 0 and current_count % batch_size == 0:
            conn.commit()
            return True
        return False

    def _save_directory_scan(self, conn: sqlite3.Connection, session_id: str, root_dir: Path, files: list[Path]) -> None:
        """Cache the directory scan results for later resumption."""
        import json
        file_paths_json = json.dumps([str(f) for f in files])
        scan_id = f"{session_id}:scan"
        
        conn.execute("""
            INSERT OR REPLACE INTO directory_scans 
            (scan_id, session_id, root_dir, file_paths, scanned_at, file_count) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (scan_id, session_id, str(root_dir), file_paths_json, datetime.now().timestamp(), len(files)))
        conn.commit()

    def _load_directory_scan(self, conn: sqlite3.Connection, session_id: str) -> Optional[tuple[Path, list[Path]]]:
        """Load cached directory scan results from a previous session."""
        cursor = conn.execute(
            "SELECT root_dir, file_paths FROM directory_scans WHERE session_id = ?",
            (session_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        root_dir = Path(row[0])
        file_paths = [Path(p) for p in json.loads(row[1])]
        return (root_dir, file_paths)

    def _save_workflow_state(
        self, 
        conn: sqlite3.Connection, 
        session_id: str, 
        file_id: str, 
        file_path: Path, 
        stage: str, 
        status: str = "completed",
        data: Optional[dict] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Save workflow state for a file at a specific processing stage.
        
        Stages: scanned, processed, embedded, stored, completed
        Statuses: pending, in_progress, completed, failed
        """
        data_json = json.dumps(data) if data else None
        conn.execute("""
            INSERT OR REPLACE INTO workflow_state 
            (session_id, file_id, file_path, stage, stage_status, completed_at, data, error_message) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, file_id, str(file_path), stage, status, datetime.now().timestamp(), data_json, error_message))
        logger.debug(f"[WORKFLOW] Saved {stage} state for {file_id}: {status}")

    def _load_workflow_state(
        self, 
        conn: sqlite3.Connection, 
        session_id: str, 
        file_id: str, 
        stage: str
    ) -> Optional[dict]:
        """Load workflow state for a file at a specific stage."""
        cursor = conn.execute(
            "SELECT stage_status, data, error_message FROM workflow_state WHERE session_id = ? AND file_id = ? AND stage = ?",
            (session_id, file_id, stage)
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        status, data_json, error_msg = row
        return {
            "status": status,
            "data": json.loads(data_json) if data_json else None,
            "error": error_msg
        }

    def _get_workflow_progress(self, conn: sqlite3.Connection, session_id: str, file_id: str) -> dict:
        """Get the workflow progress for a file (which stages have been completed)."""
        stages = ["scanned", "processed", "embedded", "stored", "completed"]
        progress = {}
        
        cursor = conn.execute(
            "SELECT stage, stage_status FROM workflow_state WHERE session_id = ? AND file_id = ?",
            (session_id, file_id)
        )
        
        for stage in stages:
            progress[stage] = "pending"
        
        for row in cursor.fetchall():
            stage, status = row
            progress[stage] = status
        
        return progress

    def _get_next_workflow_stage(self, workflow_progress: dict) -> Optional[str]:
        """Get the next stage that needs processing based on current progress."""
        stages = ["scanned", "processed", "embedded", "stored", "completed"]
        
        for stage in stages:
            if workflow_progress.get(stage) != "completed":
                return stage
        
        return None


    def _select_session_interactive(self, sessions: list[dict]) -> Optional[str]:
        """Allow user to select a session from available options interactively."""
        if not sessions:
            return None
        
        if len(sessions) == 1:
            logger.info(f"[RESUME] Automatically resuming only available session: {sessions[0]['session_id']}")
            return sessions[0]['session_id']
        
        print("\n" + "=" * 80)
        print("AVAILABLE SESSIONS FOR RESUMPTION")
        print("=" * 80)
        
        for i, session in enumerate(sessions, start=1):
            status = session['status']
            root_dir = Path(session['root_dir']).name if session['root_dir'] else 'unknown'
            total = session['total_files'] or 0
            errors = session['total_errors'] or 0
            
            # Get detailed progress
            progress_info = self.get_session_status(session['session_id'])
            progress = progress_info.get('progress', {})
            completed = progress.get('completed', 0)
            pending = progress.get('pending', 0)
            failed = progress.get('failed', 0)
            
            # Calculate and display progress bar
            progress_percentage = 0
            if total > 0:
                progress_percentage = int((completed / total) * 100)
            
            # Create progress bar visualization
            bar_length = 30
            filled = int(bar_length * completed / max(total, 1))
            bar = '█' * filled + '░' * (bar_length - filled)
            
            started = datetime.fromtimestamp(session['started_at']).strftime('%Y-%m-%d %H:%M:%S')
            
            print(f"\n[{i}] Session ID: {session['session_id'][:24]}...")
            print(f"    Directory: {root_dir}")
            print(f"    Status: {status}")
            print(f"    Progress: [{bar}] {progress_percentage}%")
            print(f"    Indexed: {completed}/{total} files")
            if failed > 0:
                print(f"    Failed: {failed} | Pending: {pending}")
            print(f"    Started: {started}")
        
        print("\n" + "=" * 80)
        print("[0] Start new session")
        print(f"[1-{len(sessions)}] Resume session")
        print("=" * 80)
        
        try:
            choice = input(f"\nSelect session (0-{len(sessions)}): ").strip()
            choice_num = int(choice)
            
            if choice_num == 0:
                return None
            elif 1 <= choice_num <= len(sessions):
                return sessions[choice_num - 1]['session_id']
            else:
                logger.warning("Invalid choice, starting new session")
                return None
        except (ValueError, KeyboardInterrupt):
            logger.info("No selection made, starting new session")
            return None

    def resume_session(self, session_id: str) -> Optional[tuple[str, list[Path]]]:
        """Resume a previous indexing session and load its cached directory scan.
        
        Returns:
            Tuple of (session_id, file_paths) if session found, None otherwise.
        """
        conn = sqlite3.connect(self.db_path)
        
        # Check if session exists
        cursor = conn.execute(
            "SELECT status FROM indexing_sessions WHERE session_id = ?",
            (session_id,)
        )
        session = cursor.fetchone()
        
        if not session:
            logger.error(f"Session {session_id} not found")
            conn.close()
            return None
        
        # Load cached directory scan
        scan_result = self._load_directory_scan(conn, session_id)
        conn.close()
        
        if not scan_result:
            logger.error(f"No cached directory scan found for session {session_id}")
            return None
        
        root_dir, files = scan_result
        logger.info(f"[RESUME] Loaded {len(files)} files from previous scan (session {session_id})")
        
        return (session_id, files)

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
        # Check if file exists before processing
        if not file_path.exists():
            logger.warning(f"File not found, skipping: {file_path}")
            return []
        
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
                file_path,
                text,
                chunk_size=self.config.chunk_size,
                chunk_overlap=self.config.chunk_overlap
            )

            chunks = []
            for i, chunk_text in enumerate(chunks_text):
                try:
                    file_size = file_path.stat().st_size
                except (FileNotFoundError, OSError):
                    file_size = 0
                
                chunk = DocumentChunk(
                    content=chunk_text,
                    source_file=file_path,
                    chunk_index=i,
                    metadata={
                        "file_path": str(file_path),
                        "file_name": file_path.name,
                        "chunk_index": i,
                        "file_size": file_size,
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
        root_dir: Optional[Path] = None,
        force_reindex: bool = False,
        progress_callback: Optional[Callable] = None,
        resume_session_id: Optional[str] = None,
        interactive: bool = False
    ) -> dict:
        """Index all files in a directory with detailed logging and persistent progress tracking.
        
        Progress is saved at each iteration, enabling resumable indexing if interrupted.
        
        Args:
            root_dir: Directory to index. Not required if resume_session_id is provided.
            force_reindex: Force reindexing even if files were already processed.
            progress_callback: Optional callback for progress updates.
            resume_session_id: Resume a specific previous session (skips new scan).
            interactive: If True and no session_id, prompt user to select a session.
        
        Returns:
            Dictionary with indexing statistics.
        """
        conn = sqlite3.connect(self.db_path)
        
        # Handle session resumption
        if resume_session_id:
            result = self.resume_session(resume_session_id)
            if not result:
                logger.error(f"Failed to resume session {resume_session_id}")
                conn.close()
                raise ValueError(f"Session {resume_session_id} not found or corrupted")
            
            session_id, files = result
            # Get root_dir from session metadata
            cursor = conn.execute("SELECT root_dir FROM indexing_sessions WHERE session_id = ?", (session_id,))
            root_dir_row = cursor.fetchone()
            root_dir = Path(root_dir_row[0]) if root_dir_row else None
            
            logger.info(f"[RESUME] Continuing session {session_id} with {len(files)} files")
            
        elif interactive:
            # List recent sessions and let user choose
            sessions = self.get_recent_sessions(limit=10)
            selected_id = self._select_session_interactive(sessions)
            
            if selected_id:
                result = self.resume_session(selected_id)
                if result:
                    session_id, files = result
                    cursor = conn.execute("SELECT root_dir FROM indexing_sessions WHERE session_id = ?", (selected_id,))
                    root_dir_row = cursor.fetchone()
                    root_dir = Path(root_dir_row[0]) if root_dir_row else None
                    logger.info(f"[RESUME] User selected session {selected_id}")
                else:
                    # Fall through to new session
                    if not root_dir:
                        conn.close()
                        raise ValueError("root_dir required when not resuming a session")
                    files = None
            else:
                # Start new session
                if not root_dir:
                    conn.close()
                    raise ValueError("root_dir required when not resuming a session")
                files = None
        else:
            # Normal new session
            if not root_dir:
                conn.close()
                raise ValueError("root_dir required when not resuming a session")
            files = None
        
        # Ensure root_dir is set
        if not root_dir:
            conn.close()
            raise ValueError("Could not determine root directory")
        
        root_dir = Path(root_dir)
        if not root_dir.exists():
            conn.close()
            raise ValueError(f"Directory does not exist: {root_dir}")

        start_time = time.time()
        
        # Create session if not resuming
        if not resume_session_id and not (interactive and 'session_id' in locals()):
            session_id = self._create_session_id(root_dir)
            logger.info(f"[START] Indexing directory: {root_dir} at {datetime.now().isoformat()} | session_id={session_id}")
        
        # Scan for files if not loaded from cache
        if files is None:
            scan_start = time.time()
            files = self._scan_directory(root_dir)
            logger.info(f"[SCAN] Found {len(files)} processable files in {time.time() - scan_start:.2f}s")
            
            self._start_indexing_session(conn, session_id, root_dir, force_reindex, len(files))
            # Cache the scan for future resumption
            self._save_directory_scan(conn, session_id, root_dir, files)
        else:
            # Already have session_id and files from resumption
            logger.info(f"[CACHED SCAN] Using {len(files)} files from previous scan")

        # Get already-completed files in this session to support resumable indexing
        completed_files = self._get_completed_files(conn, session_id)
        if completed_files:
            logger.info(f"[RESUME] Found {len(completed_files)} already processed files from previous run")

        stats = {
            "files_processed": 0,
            "chunks_created": 0,
            "documents_embedded": 0,
            "errors": 0,
            "skipped": len(completed_files),
        }

        try:
            # Process files through complete pipeline with workflow state tracking
            # Each file goes through: scanned → processed → embedded → stored → completed
            # If interrupted, resumption continues from the last completed stage
            
            for idx, file_path in enumerate(files, start=1):
                file_id = self._get_file_hash(file_path)
                
                logger.info(f"[FILE {idx}/{len(files)}] Processing: {file_path}")
                
                # Get current workflow progress for this file
                workflow_progress = self._get_workflow_progress(conn, session_id, file_id)
                
                # Check if already fully completed
                if workflow_progress.get("completed") == "completed":
                    logger.debug(f"[SKIPPED] {file_path} (already completed in previous run)")
                    stats["skipped"] += 1
                    continue
                
                # Mark as scanned if not already
                if workflow_progress.get("scanned") != "completed":
                    try:
                        logger.debug(f"[SCAN] {file_path}")
                        self._save_workflow_state(conn, session_id, file_id, file_path, "scanned", "completed")
                        conn.commit()
                    except Exception as e:
                        logger.error(f"[ERROR] Failed to mark scanned: {file_path}: {e}")
                        self._save_workflow_state(conn, session_id, file_id, file_path, "scanned", "failed", error_message=str(e))
                        conn.commit()
                        stats["errors"] += 1
                        continue
                
                # Process file into chunks (only if not already processed)
                chunks = None
                if workflow_progress.get("processed") != "completed":
                    try:
                        logger.info(f"[PROCESS] {file_path}")
                        process_start = time.time()
                        
                        wrapped_callback = None
                        if progress_callback:
                            wrapped_callback = lambda p, c, fp=file_path: progress_callback(fp, c)
                        
                        # Use strategy to process single file
                        processing_results = self.strategy.process_files(
                            files=[file_path],
                            file_hasher=self._get_file_hash,
                            process_file_func=self._process_file,
                            progress_callback=wrapped_callback,
                            skip_file_ids=set(),
                        )
                        
                        if not processing_results:
                            logger.error(f"[ERROR] No result returned from strategy for {file_path}")
                            self._save_workflow_state(conn, session_id, file_id, file_path, "processed", "failed", error_message="No result from strategy")
                            self._mark_file_progress(conn, session_id, file_id, file_path, "failed", "No result from strategy")
                            conn.commit()
                            stats["errors"] += 1
                            continue
                        
                        result = processing_results[0]
                        
                        if result.status == "failed":
                            logger.warning(f"[ERROR] Processing failed for {file_path}: {result.error_message}")
                            self._save_workflow_state(conn, session_id, file_id, file_path, "processed", "failed", error_message=result.error_message)
                            self._mark_file_progress(conn, session_id, file_id, file_path, "failed", result.error_message or "Processing failed")
                            conn.commit()
                            stats["errors"] += 1
                            continue
                        
                        chunks = result.chunks
                        if not chunks:
                            logger.warning(f"[ERROR] No chunks created from {file_path}")
                            self._save_workflow_state(conn, session_id, file_id, file_path, "processed", "failed", error_message="No chunks created")
                            self._mark_file_progress(conn, session_id, file_id, file_path, "failed", "No chunks created")
                            conn.commit()
                            stats["errors"] += 1
                            continue
                        
                        process_time = time.time() - process_start
                        logger.info(f"[PROCESS DONE] {file_path} ({len(chunks)} chunks, {process_time:.2f}s)")
                        
                        # Save processed state with chunks data
                        self._save_workflow_state(
                            conn, session_id, file_id, file_path, "processed", "completed",
                            data={"chunk_count": len(chunks), "processing_time": process_time}
                        )
                        conn.commit()
                        
                    except Exception as e:
                        logger.error(f"[ERROR] Failed to process {file_path}: {e}")
                        self._save_workflow_state(conn, session_id, file_id, file_path, "processed", "failed", error_message=str(e))
                        self._mark_file_progress(conn, session_id, file_id, file_path, "failed", str(e))
                        conn.commit()
                        stats["errors"] += 1
                        continue
                else:
                    # Load chunks from previous processing if not just processed
                    try:
                        logger.debug(f"[LOAD] Loading previously processed chunks for {file_path}")
                        # For now, we need to reprocess to get chunks
                        # In a real implementation, you'd serialize chunks to workflow_state.data
                        wrapped_callback = None
                        if progress_callback:
                            wrapped_callback = lambda p, c, fp=file_path: progress_callback(fp, c)
                        
                        processing_results = self.strategy.process_files(
                            files=[file_path],
                            file_hasher=self._get_file_hash,
                            process_file_func=self._process_file,
                            progress_callback=wrapped_callback,
                            skip_file_ids=set(),
                        )
                        
                        if processing_results and processing_results[0].chunks:
                            chunks = processing_results[0].chunks
                        else:
                            raise ValueError("Failed to load chunks")
                    except Exception as e:
                        logger.error(f"[ERROR] Failed to load chunks for {file_path}: {e}")
                        self._save_workflow_state(conn, session_id, file_id, file_path, "processed", "failed", error_message=str(e))
                        stats["errors"] += 1
                        continue
                
                if not chunks:
                    logger.error(f"[ERROR] No chunks available for {file_path}")
                    stats["errors"] += 1
                    continue
                
                # Check if already indexed globally
                cursor = conn.execute("SELECT is_indexed FROM files WHERE id = ?", (file_id,))
                existing = cursor.fetchone()
                
                if existing and existing[0] and not force_reindex:
                    logger.info(f"[SKIP] Already indexed globally: {file_path}")
                    self._save_workflow_state(conn, session_id, file_id, file_path, "completed", "completed")
                    self._mark_file_progress(conn, session_id, file_id, file_path, "completed")
                    conn.commit()
                    stats["skipped"] += 1
                    continue
                
                # Embedding (only if not already done)
                embeddings = None
                if workflow_progress.get("embedded") != "completed":
                    try:
                        logger.info(f"[EMBED] Generating embeddings for {len(chunks)} chunks from: {file_path}")
                        embed_start = time.time()
                        embeddings = self.embeddings.embed_batch([c.content for c in chunks])
                        embed_time = time.time() - embed_start
                        logger.info(f"[EMBED DONE] Completed in {embed_time:.2f}s")
                        
                        self._save_workflow_state(
                            conn, session_id, file_id, file_path, "embedded", "completed",
                            data={"embedding_count": len(embeddings), "embedding_time": embed_time}
                        )
                        conn.commit()
                        
                    except Exception as e:
                        logger.error(f"[ERROR] Failed to embed {file_path}: {e}")
                        self._save_workflow_state(conn, session_id, file_id, file_path, "embedded", "failed", error_message=str(e))
                        self._mark_file_progress(conn, session_id, file_id, file_path, "failed", str(e))
                        conn.commit()
                        stats["errors"] += 1
                        continue
                else:
                    # Need to get embeddings from previous run or recompute
                    try:
                        logger.debug(f"[LOAD EMBEDDINGS] {file_path}")
                        embeddings = self.embeddings.embed_batch([c.content for c in chunks])
                    except Exception as e:
                        logger.error(f"[ERROR] Failed to load embeddings for {file_path}: {e}")
                        stats["errors"] += 1
                        continue
                
                if not embeddings:
                    logger.error(f"[ERROR] No embeddings for {file_path}")
                    stats["errors"] += 1
                    continue
                
                # Store in vector DB (only if not already done)
                if workflow_progress.get("stored") != "completed":
                    try:
                        store_start = time.time()
                        logger.info(f"[STORE] Saving embeddings to vector DB for: {file_path}")
                        
                        chunk_ids = [f"{file_id}:{i}" for i in range(len(chunks))]
                        self.vector_db.add(
                            ids=chunk_ids,
                            embeddings=embeddings,
                            metadatas=[c.metadata for c in chunks],
                            documents=[c.content for c in chunks]
                        )
                        
                        store_time = time.time() - store_start
                        logger.info(f"[STORE DONE] Stored in {store_time:.2f}s")
                        
                        self._save_workflow_state(
                            conn, session_id, file_id, file_path, "stored", "completed",
                            data={"chunk_ids_count": len(chunk_ids), "storage_time": store_time}
                        )
                        conn.commit()
                        
                    except Exception as e:
                        logger.error(f"[ERROR] Failed to store {file_path}: {e}")
                        self._save_workflow_state(conn, session_id, file_id, file_path, "stored", "failed", error_message=str(e))
                        self._mark_file_progress(conn, session_id, file_id, file_path, "failed", str(e))
                        conn.commit()
                        stats["errors"] += 1
                        continue
                
                # Update metadata DB
                try:
                    db_start = time.time()
                    logger.debug(f"[DB] Updating metadata for: {file_path}")
                    
                    # Check if file still exists before accessing stats
                    if not file_path.exists():
                        logger.warning(f"[DB] File no longer exists, skipping metadata update: {file_path}")
                        self._save_workflow_state(conn, session_id, file_id, file_path, "completed", "failed", 
                                               error_message="File not found when updating metadata")
                        stats["errors"] += 1
                        conn.commit()
                        continue
                    
                    try:
                        file_size = file_path.stat().st_size
                        file_mtime = file_path.stat().st_mtime
                    except (FileNotFoundError, OSError) as e:
                        logger.warning(f"[DB] Could not stat file {file_path}: {e}")
                        file_size = 0
                        file_mtime = datetime.now().timestamp()
                    
                    cursor = conn.execute("SELECT id FROM files WHERE id = ?", (file_id,))
                    if cursor.fetchone():
                        conn.execute(
                            "UPDATE files SET is_indexed = 1, indexed_time = ? WHERE id = ?",
                            (datetime.now().timestamp(), file_id)
                        )
                    else:
                        conn.execute(
                            """INSERT INTO files 
                            (id, path, size, modified_time, indexed_time, content_hash, is_indexed) 
                            VALUES (?, ?, ?, ?, ?, ?, 1)""",
                            (
                                file_id,
                                str(file_path),
                                file_size,
                                file_mtime,
                                datetime.now().timestamp(),
                                file_id
                            )
                        )
                    
                    # Mark file as completely done
                    self._mark_file_progress(conn, session_id, file_id, file_path, "completed")
                    self._save_workflow_state(conn, session_id, file_id, file_path, "completed", "completed")
                    
                    logger.debug(f"[DB DONE] Metadata updated in {time.time() - db_start:.2f}s")
                    
                    # Stats
                    stats["files_processed"] += 1
                    stats["chunks_created"] += len(chunks)
                    stats["documents_embedded"] += len(chunks)
                    
                    logger.info(f"[FILE DONE] {file_path} | {len(chunks)} chunks indexed")
                    
                    # Batch commit
                    if self._batch_commit(conn, batch_size=5, current_count=stats["files_processed"]):
                        logger.debug(f"[CHECKPOINT] Committed progress for {stats['files_processed']} files")
                    else:
                        conn.commit()
                    
                except Exception as e:
                    logger.exception(f"[ERROR] Failed updating metadata for {file_path}: {e}")
                    self._mark_file_progress(conn, session_id, file_id, file_path, "failed", str(e))
                    stats["errors"] += 1
                    conn.commit()
            
            # Final commit
            conn.commit()
            self._end_indexing_session(conn, session_id, stats["errors"])

        finally:
            conn.close()

        total_time = time.time() - start_time
        logger.info(f"[END] Indexing complete in {total_time:.2f}s | stats={stats} | session_id={session_id}")

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

    def get_session_status(self, session_id: str) -> dict:
        """Get the status of a specific indexing session."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get session metadata
        session_row = cursor.execute(
            "SELECT session_id, root_dir, started_at, completed_at, status, total_files, total_errors FROM indexing_sessions WHERE session_id = ?",
            (session_id,)
        ).fetchone()

        if not session_row:
            conn.close()
            return {"error": f"Session {session_id} not found"}

        # Get progress breakdown
        progress = cursor.execute(
            "SELECT status, COUNT(*) FROM indexing_progress WHERE session_id = ? GROUP BY status",
            (session_id,)
        ).fetchall()

        progress_dict = {status: count for status, count in progress}

        result = {
            "session_id": session_row[0],
            "root_dir": session_row[1],
            "started_at": session_row[2],
            "completed_at": session_row[3],
            "status": session_row[4],
            "total_files": session_row[5],
            "total_errors": session_row[6],
            "progress": progress_dict,
        }

        conn.close()
        return result

    def get_recent_sessions(self, limit: int = 5) -> list:
        """Get the most recent indexing sessions."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        sessions = cursor.execute("""
            SELECT session_id, root_dir, started_at, completed_at, status, total_files, total_errors
            FROM indexing_sessions
            ORDER BY started_at DESC
            LIMIT ?
        """, (limit,)).fetchall()

        result = [
            {
                "session_id": s[0],
                "root_dir": s[1],
                "started_at": s[2],
                "completed_at": s[3],
                "status": s[4],
                "total_files": s[5],
                "total_errors": s[6],
            }
            for s in sessions
        ]

        conn.close()
        return result

    def get_failed_files(self, session_id: str = None) -> list:
        """Get files that failed to process. If session_id is None, get all failed files."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if session_id:
            failed = cursor.execute("""
                SELECT file_path, error_message, processed_at
                FROM indexing_progress
                WHERE session_id = ? AND status = 'failed'
                ORDER BY processed_at DESC
            """, (session_id,)).fetchall()
        else:
            failed = cursor.execute("""
                SELECT file_path, error_message, processed_at
                FROM indexing_progress
                WHERE status = 'failed'
                ORDER BY processed_at DESC
            """).fetchall()

        result = [
            {
                "file_path": f[0],
                "error_message": f[1],
                "processed_at": f[2],
            }
            for f in failed
        ]

        conn.close()
        return result

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
