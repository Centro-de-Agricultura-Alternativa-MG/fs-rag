"""Tests for FS-RAG components."""

import tempfile
import pytest
from pathlib import Path

from fs_rag.processor import ProcessorFactory, TextProcessor, PDFProcessor
from fs_rag.core import get_config
from fs_rag.indexer import FilesystemIndexer


def test_text_processor():
    """Test text file processing."""
    processor = TextProcessor()
    
    # Create temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("This is a test document.\nWith multiple lines.")
        temp_path = Path(f.name)
    
    try:
        assert processor.can_process(temp_path)
        text = processor.extract_text(temp_path)
        assert "test document" in text
        
        # Test chunking
        chunks = processor.chunk_text(text, chunk_size=20, chunk_overlap=5)
        assert len(chunks) > 0
        assert all(len(chunk) <= 30 for chunk in chunks)  # Allow some overlap
    finally:
        temp_path.unlink()


def test_processor_factory():
    """Test processor factory."""
    with tempfile.NamedTemporaryFile(suffix='.txt') as f:
        temp_path = Path(f.name)
        processor = ProcessorFactory.get_processor(temp_path)
        assert processor is not None
        assert isinstance(processor, TextProcessor)


def test_config():
    """Test configuration loading."""
    config = get_config()
    assert config is not None
    assert config.chunk_size > 0
    assert config.search_top_k > 0


def test_filesystem_scanner():
    """Test filesystem scanning."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # Create test files
        (tmppath / "file1.txt").write_text("Content 1")
        (tmppath / "file2.txt").write_text("Content 2")
        subdir = tmppath / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("Content 3")
        
        # Create non-processable files
        (tmppath / ".hidden.txt").write_text("Hidden")
        (tmppath / "binary.pyc").write_bytes(b"\x00\x01\x02")
        
        # Scan
        indexer = FilesystemIndexer()
        files = indexer._scan_directory(tmppath)
        
        # Check results
        assert len(files) == 3  # Only processable files
        file_names = {f.name for f in files}
        assert "file1.txt" in file_names
        assert "file2.txt" in file_names
        assert "file3.txt" in file_names
        assert ".hidden.txt" not in file_names
        assert "binary.pyc" not in file_names


def test_indexer_basic():
    """Test basic indexing workflow."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # Create test documents
        (tmppath / "doc1.txt").write_text("The quick brown fox jumps over the lazy dog.")
        (tmppath / "doc2.txt").write_text("Machine learning is a subset of artificial intelligence.")
        
        # Index
        indexer = FilesystemIndexer()
        stats = indexer.index_directory(tmppath, force_reindex=True)
        
        # Verify
        assert stats["files_processed"] > 0
        assert stats["chunks_created"] > 0
        
        # Check stats
        index_stats = indexer.get_index_stats()
        assert index_stats["total_files"] > 0
        assert index_stats["indexed_files"] > 0


if __name__ == "__main__":
    # Run basic tests without pytest
    print("Running basic tests...")
    
    print("✓ Testing text processor...")
    test_text_processor()
    
    print("✓ Testing processor factory...")
    test_processor_factory()
    
    print("✓ Testing config...")
    test_config()
    
    print("✓ Testing filesystem scanner...")
    test_filesystem_scanner()
    
    print("✓ Testing indexer...")
    test_indexer_basic()
    
    print("\n✅ All tests passed!")
