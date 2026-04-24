"""Tests for filesystem tree context building."""

import pytest
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

from fs_rag.core.context_tree import (
    FilesystemTreeBuilder,
    GitHistoryReader,
    format_context_with_tree,
)


class TestGitHistoryReader:
    """Tests for GitHistoryReader."""

    def test_git_history_reader_init(self):
        """Test GitHistoryReader initialization."""
        reader = GitHistoryReader()
        assert reader.repo_path == Path.cwd()

    def test_git_history_reader_custom_path(self):
        """Test GitHistoryReader with custom path."""
        custom_path = Path("/tmp")
        reader = GitHistoryReader(custom_path)
        assert reader.repo_path == custom_path

    @patch("subprocess.run")
    def test_get_file_change_frequency(self, mock_run):
        """Test getting file change frequency."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="file1.txt\nfile2.txt\nfile1.txt\n"
        )
        
        reader = GitHistoryReader()
        result = reader.get_file_change_frequency()
        
        assert "file1.txt" in result
        assert result["file1.txt"] == 2
        assert result["file2.txt"] == 1

    @patch("subprocess.run")
    def test_get_recent_commits(self, mock_run):
        """Test getting recent commits."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="abc1234 Initial commit\ndef5678 Add feature\n"
        )
        
        reader = GitHistoryReader()
        result = reader.get_recent_commits(limit=2)
        
        assert len(result) == 2
        assert result[0]["sha"] == "abc1234"
        assert "Initial commit" in result[0]["message"]


class TestFilesystemTreeBuilder:
    """Tests for FilesystemTreeBuilder."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary SQLite database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "index.db"
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE files (
                    id TEXT PRIMARY KEY,
                    path TEXT NOT NULL UNIQUE,
                    size INTEGER,
                    modified_time REAL,
                    indexed_time REAL,
                    content_hash TEXT,
                    is_indexed BOOLEAN DEFAULT 0
                )
            """)
            
            test_files = [
                "src/main.py",
                "src/utils.py",
                "data/input.txt",
                "data/output.txt",
                "README.md",
            ]
            
            for file_path in test_files:
                conn.execute(
                    "INSERT INTO files (id, path, is_indexed) VALUES (?, ?, 1)",
                    (f"id_{file_path}", file_path)
                )
            
            conn.commit()
            conn.close()
            yield db_path

    def test_builder_init(self, temp_db):
        """Test FilesystemTreeBuilder initialization."""
        builder = FilesystemTreeBuilder(temp_db)
        assert builder.index_db_path == temp_db

    def test_get_indexed_files(self, temp_db):
        """Test retrieving indexed files."""
        builder = FilesystemTreeBuilder(temp_db)
        files = builder._get_indexed_files()
        
        assert len(files) == 5
        assert "src/main.py" in files
        assert "data/input.txt" in files

    def test_build_tree_structure(self, temp_db):
        """Test building tree structure."""
        builder = FilesystemTreeBuilder(temp_db)
        files = builder._get_indexed_files()
        tree = builder._build_tree_structure(files)
        
        assert "src" in tree
        assert "data" in tree
        assert "README.md" in tree
        assert "main.py" in tree["src"]

    def test_tree_to_string(self, temp_db):
        """Test converting tree to string."""
        builder = FilesystemTreeBuilder(temp_db)
        tree = {
            "src": {
                "main.py": {"__file__": True},
                "utils.py": {"__file__": True},
            },
            "data": {
                "input.txt": {"__file__": True},
            }
        }
        
        lines = builder._tree_to_string(tree)
        result = "\n".join(lines)
        
        assert "src/" in result
        assert "main.py" in result
        assert "data/" in result

    def test_build_context_tree(self, temp_db):
        """Test building complete context tree."""
        builder = FilesystemTreeBuilder(temp_db)
        context = builder.build_context_tree()
        
        assert "Indexed Filesystem Structure" in context
        assert "src/" in context
        assert "main.py" in context

    def test_get_directory_structure_for_files(self, temp_db):
        """Test building structure for specific files."""
        builder = FilesystemTreeBuilder(temp_db)
        files = ["src/main.py", "src/utils.py", "data/input.txt"]
        structure = builder.get_directory_structure_for_files(files)
        
        assert "Relevant Files Structure" in structure
        assert "src/" in structure
        assert "main.py" in structure
        assert "data/" in structure


class TestContextFormatting:
    """Tests for context formatting utilities."""

    def test_format_context_with_tree_basic(self):
        """Test basic context formatting with tree."""
        base_context = "Document 1: Some content\n"
        files = ["src/main.py", "data/input.txt"]
        
        result = format_context_with_tree(base_context, files)
        
        assert "Document 1: Some content" in result
        assert "Relevant Files Structure" in result
        assert "src/" in result

    def test_format_context_with_tree_empty_files(self):
        """Test formatting with no files."""
        base_context = "Document 1: Some content\n"
        files = []
        
        result = format_context_with_tree(base_context, files)
        
        assert "Document 1: Some content" in result
