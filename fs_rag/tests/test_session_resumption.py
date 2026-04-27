"""Tests for session resumption and directory scan caching."""

import sqlite3
import tempfile
import json
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


class TestDirectoryScanCaching:
    """Test directory scan caching functionality."""

    def test_directory_scans_table_created(self, indexer):
        """Test that directory_scans table is created."""
        conn = sqlite3.connect(indexer.db_path)
        cursor = conn.cursor()
        
        # Check table exists
        tables = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='directory_scans'"
        ).fetchall()
        
        assert len(tables) == 1
        conn.close()

    def test_save_directory_scan(self, indexer):
        """Test saving a directory scan to cache."""
        session_id = "test-session-123"
        root_dir = Path("/test/dir")
        files = [Path("/test/dir/file1.txt"), Path("/test/dir/file2.txt")]
        
        conn = sqlite3.connect(indexer.db_path)
        indexer._save_directory_scan(conn, session_id, root_dir, files)
        
        # Verify it was saved
        cursor = conn.execute(
            "SELECT file_count FROM directory_scans WHERE session_id = ?",
            (session_id,)
        )
        row = cursor.fetchone()
        
        assert row is not None
        assert row[0] == 2
        conn.close()

    def test_load_directory_scan(self, indexer):
        """Test loading a cached directory scan."""
        session_id = "test-session-123"
        root_dir = Path("/test/dir")
        files = [Path("/test/dir/file1.txt"), Path("/test/dir/file2.txt")]
        
        conn = sqlite3.connect(indexer.db_path)
        indexer._save_directory_scan(conn, session_id, root_dir, files)
        
        # Load it back
        result = indexer._load_directory_scan(conn, session_id)
        
        assert result is not None
        loaded_root_dir, loaded_files = result
        assert loaded_root_dir == root_dir
        assert len(loaded_files) == 2
        assert loaded_files[0] == Path("/test/dir/file1.txt")
        
        conn.close()

    def test_load_nonexistent_scan(self, indexer):
        """Test loading a scan that doesn't exist."""
        conn = sqlite3.connect(indexer.db_path)
        result = indexer._load_directory_scan(conn, "nonexistent-session")
        
        assert result is None
        conn.close()


class TestSessionResumption:
    """Test session resumption functionality."""

    def test_resume_session_basic(self, indexer):
        """Test resuming a session and loading its cached scan."""
        session_id = "test-session-123"
        root_dir = Path("/test/dir")
        files = [Path("/test/dir/file1.txt"), Path("/test/dir/file2.txt")]
        
        conn = sqlite3.connect(indexer.db_path)
        
        # Create session
        indexer._start_indexing_session(conn, session_id, root_dir, False, 2)
        
        # Save scan
        indexer._save_directory_scan(conn, session_id, root_dir, files)
        
        conn.close()
        
        # Resume session
        result = indexer.resume_session(session_id)
        
        assert result is not None
        loaded_session_id, loaded_files = result
        assert loaded_session_id == session_id
        assert len(loaded_files) == 2

    def test_resume_nonexistent_session(self, indexer):
        """Test trying to resume a session that doesn't exist."""
        result = indexer.resume_session("nonexistent-session-id")
        
        assert result is None

    def test_resume_session_without_scan(self, indexer):
        """Test resuming a session that has no cached scan."""
        session_id = "test-session-no-scan"
        root_dir = Path("/test/dir")
        
        conn = sqlite3.connect(indexer.db_path)
        indexer._start_indexing_session(conn, session_id, root_dir, False, 0)
        conn.close()
        
        # Try to resume without saved scan
        result = indexer.resume_session(session_id)
        
        assert result is None


class TestSessionSelection:
    """Test session selection UI."""

    def test_select_session_single_option(self, indexer):
        """Test automatic selection when only one session exists."""
        session = {
            'session_id': 'only-session',
            'status': 'in_progress',
            'root_dir': '/data'
        }
        
        # Capture logger output
        with patch('fs_rag.indexer.logger.info') as mock_logger:
            result = indexer._select_session_interactive([session])
        
        assert result == 'only-session'
        mock_logger.assert_called()

    def test_select_session_no_sessions(self, indexer):
        """Test selection with no available sessions."""
        result = indexer._select_session_interactive([])
        
        assert result is None

    def test_select_session_new_session_choice(self, indexer):
        """Test selecting to start a new session (choice 0)."""
        sessions = [
            {
                'session_id': 'session-1',
                'status': 'completed',
                'root_dir': '/data',
                'total_files': 100,
                'total_errors': 0,
                'started_at': 1234567890.0
            },
            {
                'session_id': 'session-2',
                'status': 'in_progress',
                'root_dir': '/other',
                'total_files': 50,
                'total_errors': 5,
                'started_at': 1234567900.0
            }
        ]
        
        with patch('builtins.input', return_value='0'):
            result = indexer._select_session_interactive(sessions)
        
        assert result is None  # Starting new session

    def test_select_session_resume_choice(self, indexer):
        """Test selecting to resume a session."""
        sessions = [
            {
                'session_id': 'session-1',
                'status': 'in_progress',
                'root_dir': '/data',
                'total_files': 100,
                'total_errors': 5,
                'started_at': 1234567890.0
            },
            {
                'session_id': 'session-2',
                'status': 'completed',
                'root_dir': '/other',
                'total_files': 50,
                'total_errors': 0,
                'started_at': 1234567900.0
            }
        ]
        
        with patch('builtins.input', return_value='2'):
            result = indexer._select_session_interactive(sessions)
        
        assert result == 'session-2'

    def test_select_session_invalid_choice(self, indexer):
        """Test handling invalid user input."""
        sessions = [
            {
                'session_id': 'session-1',
                'status': 'in_progress',
                'root_dir': '/data',
                'total_files': 100,
                'total_errors': 0,
                'started_at': 1234567890.0
            },
            {
                'session_id': 'session-2',
                'status': 'completed',
                'root_dir': '/other',
                'total_files': 50,
                'total_errors': 0,
                'started_at': 1234567900.0
            }
        ]
        
        # Invalid choice triggers new session
        with patch('builtins.input', return_value='999'):
            result = indexer._select_session_interactive(sessions)
        
        assert result is None

    def test_select_session_keyboard_interrupt(self, indexer):
        """Test handling keyboard interrupt."""
        sessions = [
            {
                'session_id': 'session-1',
                'status': 'in_progress',
                'root_dir': '/data',
                'total_files': 100,
                'total_errors': 0,
                'started_at': 1234567890.0
            },
            {
                'session_id': 'session-2',
                'status': 'completed',
                'root_dir': '/other',
                'total_files': 50,
                'total_errors': 0,
                'started_at': 1234567900.0
            }
        ]
        
        with patch('builtins.input', side_effect=KeyboardInterrupt):
            result = indexer._select_session_interactive(sessions)
        
        assert result is None


class TestIndexDirectoryWithResumption:
    """Test index_directory with resumption parameters."""

    @patch("fs_rag.indexer.ProcessorFactory")
    def test_index_directory_backwards_compatible(self, mock_factory, indexer):
        """Test that old-style calls still work."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir)
            (test_dir / "file1.txt").write_text("content " * 50)
            
            mock_processor = MagicMock()
            mock_processor.extract_text.return_value = "test content " * 50
            mock_processor.chunk_text.return_value = ["chunk1", "chunk2"]
            mock_factory.get_processor.return_value = mock_processor
            mock_factory.can_process.return_value = True
            
            # Old-style call with just root_dir
            stats = indexer.index_directory(test_dir)
            
            assert "files_processed" in stats
            assert "chunks_created" in stats

    @patch("fs_rag.indexer.ProcessorFactory")
    def test_index_directory_with_resume(self, mock_factory, indexer):
        """Test resuming indexing from a previous session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir)
            (test_dir / "file1.txt").write_text("content " * 50)
            (test_dir / "file2.txt").write_text("content " * 50)
            
            mock_processor = MagicMock()
            mock_processor.extract_text.return_value = "test content " * 50
            mock_processor.chunk_text.return_value = ["chunk1"]
            mock_factory.get_processor.return_value = mock_processor
            mock_factory.can_process.return_value = True
            
            # First run - complete indexing
            stats1 = indexer.index_directory(test_dir)
            session_id = indexer.get_recent_sessions(limit=1)[0]['session_id']
            
            # Second run - resume from session
            stats2 = indexer.index_directory(resume_session_id=session_id)
            
            # Verify resumption worked
            assert stats2["files_processed"] == 0  # Already processed
            assert stats2["skipped"] > 0  # Files were skipped

    def test_index_directory_requires_root_dir_or_resume(self, indexer):
        """Test that either root_dir or resume_session_id is required."""
        with pytest.raises(ValueError):
            indexer.index_directory()

    def test_index_directory_invalid_root_dir(self, indexer):
        """Test error handling for invalid root directory."""
        with pytest.raises(ValueError):
            indexer.index_directory(Path("/nonexistent/path"))


class TestScanCachingIntegration:
    """Integration tests for scan caching."""

    @patch("fs_rag.indexer.ProcessorFactory")
    def test_scan_cached_on_first_run(self, mock_factory, indexer):
        """Test that scan is cached during initial indexing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir)
            (test_dir / "file1.txt").write_text("content " * 50)
            
            mock_processor = MagicMock()
            mock_processor.extract_text.return_value = "test content " * 50
            mock_processor.chunk_text.return_value = ["chunk1"]
            mock_factory.get_processor.return_value = mock_processor
            mock_factory.can_process.return_value = True
            
            # Run indexing
            indexer.index_directory(test_dir)
            
            # Verify scan was cached
            session_id = indexer.get_recent_sessions(limit=1)[0]['session_id']
            
            conn = sqlite3.connect(indexer.db_path)
            cursor = conn.execute(
                "SELECT file_count FROM directory_scans WHERE session_id = ?",
                (session_id,)
            )
            result = cursor.fetchone()
            
            assert result is not None
            assert result[0] == 1  # One file scanned
            
            conn.close()

    @patch("fs_rag.indexer.ProcessorFactory")
    def test_scan_reused_on_resume(self, mock_factory, indexer):
        """Test that cached scan is reused when resuming."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir)
            (test_dir / "file1.txt").write_text("content " * 50)
            
            mock_processor = MagicMock()
            mock_processor.extract_text.return_value = "test content " * 50
            mock_processor.chunk_text.return_value = ["chunk1"]
            mock_factory.get_processor.return_value = mock_processor
            mock_factory.can_process.return_value = True
            
            # First run
            indexer.index_directory(test_dir)
            session_id = indexer.get_recent_sessions(limit=1)[0]['session_id']
            
            # Track number of scan calls
            original_scan = indexer._scan_directory
            scan_count = 0
            
            def tracked_scan(path):
                nonlocal scan_count
                scan_count += 1
                return original_scan(path)
            
            indexer._scan_directory = tracked_scan
            
            # Resume - should not call _scan_directory
            indexer.index_directory(resume_session_id=session_id)
            
            assert scan_count == 0  # Scan was not called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
