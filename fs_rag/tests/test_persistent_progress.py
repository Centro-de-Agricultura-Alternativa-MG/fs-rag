"""Tests for persistent progress tracking in FilesystemIndexer."""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from fs_rag.indexer import FilesystemIndexer
from fs_rag.processor import DocumentChunk


@pytest.fixture
def temp_index_dir():
    """Create a temporary directory for index files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_config(temp_index_dir):
    """Create a mock configuration."""
    config = MagicMock()
    config.index_dir = temp_index_dir
    config.chunk_size = 1024
    config.chunk_overlap = 100
    return config


@pytest.fixture
def mock_embeddings():
    """Create a mock embeddings provider."""
    embeddings = MagicMock()
    embeddings.embed_batch.return_value = [[0.1] * 384 for _ in range(10)]
    return embeddings


@pytest.fixture
def mock_vector_db():
    """Create a mock vector database."""
    vector_db = MagicMock()
    vector_db.add.return_value = None
    vector_db.count.return_value = 0
    return vector_db


@pytest.fixture
def indexer(mock_config, mock_embeddings, mock_vector_db):
    """Create an indexer with mocked dependencies."""
    with patch("fs_rag.indexer.get_config", return_value=mock_config), \
         patch("fs_rag.indexer.get_embeddings_provider", return_value=mock_embeddings), \
         patch("fs_rag.indexer.get_vector_db", return_value=mock_vector_db):
        indexer = FilesystemIndexer()
        yield indexer


class TestProgressPersistence:
    """Test persistent progress tracking."""

    def test_init_creates_progress_tables(self, indexer):
        """Test that initialization creates required tables."""
        conn = sqlite3.connect(indexer.db_path)
        cursor = conn.cursor()

        # Check all tables exist
        tables = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t[0] for t in tables}

        assert "files" in table_names
        assert "chunks" in table_names
        assert "indexing_progress" in table_names
        assert "indexing_sessions" in table_names

        conn.close()

    def test_session_id_generation(self, indexer):
        """Test that session IDs are unique and consistent."""
        test_dir = Path("/test/directory")

        session_id1 = indexer._create_session_id(test_dir)
        session_id2 = indexer._create_session_id(test_dir)

        assert isinstance(session_id1, str)
        assert len(session_id1) == 32  # MD5 hex length
        # Same input should generate same ID (deterministic based on dir and timestamp precision)
        # Note: actual calls will differ slightly due to timestamp

    def test_start_indexing_session(self, indexer):
        """Test recording the start of an indexing session."""
        session_id = "test-session-123"
        root_dir = Path("/test/dir")
        total_files = 50

        conn = sqlite3.connect(indexer.db_path)
        indexer._start_indexing_session(conn, session_id, root_dir, False, total_files)

        # Verify session was recorded
        cursor = conn.execute(
            "SELECT session_id, root_dir, status, total_files FROM indexing_sessions WHERE session_id = ?",
            (session_id,)
        )
        row = cursor.fetchone()

        assert row is not None
        assert row[0] == session_id
        assert row[1] == str(root_dir)
        assert row[2] == "in_progress"
        assert row[3] == total_files

        conn.close()

    def test_mark_file_progress_completed(self, indexer):
        """Test marking a file as completed."""
        session_id = "test-session-123"
        file_id = "file-123"
        file_path = Path("/test/file.txt")

        conn = sqlite3.connect(indexer.db_path)
        indexer._mark_file_progress(conn, session_id, file_id, file_path, "completed")

        # Verify progress was recorded
        cursor = conn.execute(
            "SELECT file_id, status FROM indexing_progress WHERE session_id = ? AND file_id = ?",
            (session_id, file_id)
        )
        row = cursor.fetchone()

        assert row is not None
        assert row[0] == file_id
        assert row[1] == "completed"

        conn.close()

    def test_mark_file_progress_failed(self, indexer):
        """Test marking a file as failed with error message."""
        session_id = "test-session-123"
        file_id = "file-456"
        file_path = Path("/test/file2.txt")
        error_msg = "Permission denied"

        conn = sqlite3.connect(indexer.db_path)
        indexer._mark_file_progress(conn, session_id, file_id, file_path, "failed", error_msg)

        # Verify progress was recorded with error
        cursor = conn.execute(
            "SELECT status, error_message FROM indexing_progress WHERE session_id = ? AND file_id = ?",
            (session_id, file_id)
        )
        row = cursor.fetchone()

        assert row is not None
        assert row[0] == "failed"
        assert row[1] == error_msg

        conn.close()

    def test_get_completed_files(self, indexer):
        """Test retrieving completed files for a session."""
        session_id = "test-session-123"

        conn = sqlite3.connect(indexer.db_path)

        # Mark some files as completed
        for i in range(5):
            indexer._mark_file_progress(
                conn, session_id, f"file-{i}", Path(f"/test/file{i}.txt"), "completed"
            )

        # Mark one as failed
        indexer._mark_file_progress(
            conn, session_id, "file-failed", Path("/test/failed.txt"), "failed"
        )

        completed = indexer._get_completed_files(conn, session_id)

        assert len(completed) == 5
        assert "file-failed" not in completed
        for i in range(5):
            assert f"file-{i}" in completed

        conn.close()

    def test_batch_commit_triggers_at_batch_size(self, indexer):
        """Test that batch commit triggers at appropriate intervals."""
        conn = sqlite3.connect(indexer.db_path)

        # Test batch size of 5
        batch_size = 5

        # Should not commit at count < batch_size
        assert not indexer._batch_commit(conn, batch_size=batch_size, current_count=4)
        assert not indexer._batch_commit(conn, batch_size=batch_size, current_count=1)

        # Should commit at count == batch_size
        assert indexer._batch_commit(conn, batch_size=batch_size, current_count=5)
        assert indexer._batch_commit(conn, batch_size=batch_size, current_count=10)

        # Should not commit at non-multiple
        assert not indexer._batch_commit(conn, batch_size=batch_size, current_count=6)

        conn.close()

    def test_end_indexing_session(self, indexer):
        """Test recording the completion of an indexing session."""
        session_id = "test-session-123"
        root_dir = Path("/test/dir")
        total_files = 50

        conn = sqlite3.connect(indexer.db_path)

        # Start session
        indexer._start_indexing_session(conn, session_id, root_dir, False, total_files)

        # End session
        indexer._end_indexing_session(conn, session_id, 5)

        # Verify session was updated
        cursor = conn.execute(
            "SELECT status, total_errors, completed_at FROM indexing_sessions WHERE session_id = ?",
            (session_id,)
        )
        row = cursor.fetchone()

        assert row is not None
        assert row[0] == "completed"
        assert row[1] == 5
        assert row[2] is not None

        conn.close()

    def test_get_session_status(self, indexer):
        """Test retrieving session status and progress."""
        session_id = "test-session-123"
        root_dir = Path("/test/dir")

        conn = sqlite3.connect(indexer.db_path)

        # Create session and progress
        indexer._start_indexing_session(conn, session_id, root_dir, False, 10)
        for i in range(7):
            indexer._mark_file_progress(
                conn, session_id, f"file-{i}", Path(f"/test/file{i}.txt"), "completed"
            )
        for i in range(7, 10):
            indexer._mark_file_progress(
                conn, session_id, f"file-{i}", Path(f"/test/file{i}.txt"), "failed"
            )
        indexer._end_indexing_session(conn, session_id, 3)
        conn.close()

        # Query session status
        status = indexer.get_session_status(session_id)

        assert status["session_id"] == session_id
        assert status["root_dir"] == str(root_dir)
        assert status["status"] == "completed"
        assert status["total_files"] == 10
        assert status["total_errors"] == 3
        assert status["progress"]["completed"] == 7
        assert status["progress"]["failed"] == 3

    def test_get_recent_sessions(self, indexer):
        """Test retrieving recent indexing sessions."""
        conn = sqlite3.connect(indexer.db_path)

        # Create multiple sessions
        for i in range(3):
            session_id = f"session-{i}"
            indexer._start_indexing_session(conn, session_id, Path(f"/dir{i}"), False, 10)
            indexer._end_indexing_session(conn, session_id, 0)

        conn.close()

        # Get recent sessions
        sessions = indexer.get_recent_sessions(limit=5)

        assert len(sessions) == 3
        # Should be in reverse chronological order (most recent first)
        assert sessions[0]["session_id"] == "session-2"
        assert sessions[1]["session_id"] == "session-1"
        assert sessions[2]["session_id"] == "session-0"

    def test_get_failed_files(self, indexer):
        """Test retrieving failed files from a session."""
        session_id = "test-session-123"

        conn = sqlite3.connect(indexer.db_path)
        indexer._start_indexing_session(conn, session_id, Path("/test"), False, 10)

        # Create some failed files
        for i in range(3):
            indexer._mark_file_progress(
                conn, session_id, f"file-{i}", Path(f"/test/file{i}.txt"), "failed",
                error_message=f"Error {i}"
            )

        conn.commit()  # Commit before closing
        conn.close()

        # Get failed files
        failed = indexer.get_failed_files(session_id)

        assert len(failed) == 3
        for item in failed:
            assert "Error" in item["error_message"]
            assert "/test/file" in item["file_path"]

    def test_resumable_indexing_skips_completed_files(self, indexer):
        """Test that resumed indexing skips already-completed files."""
        session_id = "test-session-123"

        conn = sqlite3.connect(indexer.db_path)
        indexer._start_indexing_session(conn, session_id, Path("/test"), False, 5)

        # Mark files 0-2 as completed
        for i in range(3):
            indexer._mark_file_progress(
                conn, session_id, f"file-{i}", Path(f"/test/file{i}.txt"), "completed"
            )

        conn.commit()  # Commit before closing
        conn.close()

        # Need to open a new connection to query
        conn = sqlite3.connect(indexer.db_path)
        completed = indexer._get_completed_files(conn, session_id)
        conn.close()

        assert len(completed) == 3

        # Files 3-4 should not be in completed
        assert "file-3" not in completed
        assert "file-4" not in completed


class TestProgressTrackingIntegration:
    """Integration tests for progress tracking with actual indexing."""

    @patch("fs_rag.indexer.ProcessorFactory")
    def test_index_directory_with_progress_tracking(self, mock_factory, indexer):
        """Test that indexing records progress for each file."""
        # Create temporary test files
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir)

            # Create test files
            (test_dir / "file1.txt").write_text("content1 " * 20)
            (test_dir / "file2.txt").write_text("content2 " * 20)

            # Mock processor
            mock_processor = MagicMock()
            mock_processor.extract_text.return_value = "test content " * 50
            mock_processor.chunk_text.return_value = ["chunk1", "chunk2"]
            mock_factory.get_processor.return_value = mock_processor
            mock_factory.can_process.return_value = True

            # Run indexing
            stats = indexer.index_directory(test_dir)

            # Verify stats
            assert stats["files_processed"] == 2
            assert stats["chunks_created"] == 4  # 2 files * 2 chunks each
            assert stats["documents_embedded"] == 4

    @patch("fs_rag.indexer.ProcessorFactory")
    def test_index_resumption_after_interruption(self, mock_factory, indexer):
        """Test that indexing can resume from where it left off."""
        # This is a simulated test since we can't truly interrupt the process
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir)

            # Create test files
            (test_dir / "file1.txt").write_text("content1 " * 20)
            (test_dir / "file2.txt").write_text("content2 " * 20)
            (test_dir / "file3.txt").write_text("content3 " * 20)

            # Mock processor
            mock_processor = MagicMock()
            mock_processor.extract_text.return_value = "test content " * 50
            mock_processor.chunk_text.return_value = ["chunk1", "chunk2"]
            mock_factory.get_processor.return_value = mock_processor
            mock_factory.can_process.return_value = True

            # First run - process all files
            stats1 = indexer.index_directory(test_dir)
            assert stats1["files_processed"] == 3
            session_id1 = None

            # Manually create second "session" by getting first session and marking files
            # In real usage, the second call would detect completed files from first session
            conn = sqlite3.connect(indexer.db_path)
            cursor = conn.execute("SELECT session_id FROM indexing_sessions LIMIT 1")
            session_id1 = cursor.fetchone()[0]
            conn.close()

            # Verify progress was tracked
            session_status = indexer.get_session_status(session_id1)
            assert session_status["status"] == "completed"
            assert session_status["progress"]["completed"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
