#!/usr/bin/env python
"""Examples of using the parallel and distributed indexing features."""

from pathlib import Path
from fs_rag.indexer import FilesystemIndexer
import os


def example_1_sequential():
    """Example 1: Sequential processing (default, backward compatible)."""
    print("\n=== Example 1: Sequential Processing ===\n")
    
    indexer = FilesystemIndexer()
    
    # Index a directory sequentially
    stats = indexer.index_directory(
        root_dir=Path('./data'),
        force_reindex=False,
    )
    
    print(f"Files processed: {stats['files_processed']}")
    print(f"Chunks created: {stats['chunks_created']}")
    print(f"Errors: {stats['errors']}")
    print(f"Skipped: {stats['skipped']}")


def example_2_parallel_threads():
    """Example 2: Parallel processing with threads.
    
    To use this, set environment variables:
    export PARALLEL_PROCESSING_ENABLED=true
    export PARALLEL_WORKERS=4
    export PARALLEL_STRATEGY=threads
    """
    print("\n=== Example 2: Parallel Processing (Threads) ===\n")
    
    # Set environment variables for parallel processing
    os.environ['PARALLEL_PROCESSING_ENABLED'] = 'true'
    os.environ['PARALLEL_WORKERS'] = '4'
    os.environ['PARALLEL_STRATEGY'] = 'threads'
    
    # Need to reload config to pick up env changes
    import importlib
    import fs_rag.core.config as config_module
    importlib.reload(config_module)
    
    # Create indexer with parallel strategy
    indexer = FilesystemIndexer()
    print(f"Strategy: {indexer.strategy.__class__.__name__}")
    print(f"Workers: {indexer.strategy.max_workers}\n")
    
    # Index a directory in parallel
    stats = indexer.index_directory(
        root_dir=Path('./data'),
        force_reindex=False,
    )
    
    print(f"\nFiles processed: {stats['files_processed']}")
    print(f"Chunks created: {stats['chunks_created']}")
    print(f"Errors: {stats['errors']}")


def example_3_resumable_indexing():
    """Example 3: Resumable indexing with progress tracking."""
    print("\n=== Example 3: Resumable Indexing ===\n")
    
    indexer = FilesystemIndexer()
    
    # First session
    print("Starting first indexing session...")
    stats1 = indexer.index_directory(
        root_dir=Path('./data'),
        force_reindex=False,
    )
    print(f"Session 1 - Processed: {stats1['files_processed']}")
    
    # The session ID is returned in logs
    # You can see session IDs and resume them later
    sessions = indexer.get_recent_sessions(limit=5)
    for session in sessions:
        print(f"\nSession: {session['session_id'][:16]}...")
        print(f"  Status: {session['status']}")
        print(f"  Files: {session['total_files']}")


def example_4_error_handling():
    """Example 4: Error handling and failure recovery."""
    print("\n=== Example 4: Error Handling ===\n")
    
    indexer = FilesystemIndexer()
    
    # Index directory
    stats = indexer.index_directory(Path('./data'))
    
    if stats['errors'] > 0:
        print(f"Found {stats['errors']} errors during indexing\n")
        
        # Get failed files
        failed_files = indexer.get_failed_files()
        for failed in failed_files[:5]:  # Show first 5
            print(f"Failed: {failed['file_path']}")
            print(f"  Error: {failed['error_message']}")
    else:
        print("All files processed successfully!")


def example_5_monitoring():
    """Example 5: Monitoring and statistics."""
    print("\n=== Example 5: Monitoring ===\n")
    
    indexer = FilesystemIndexer()
    
    # Get index statistics
    stats = indexer.get_index_stats()
    print("Index Statistics:")
    print(f"  Total files: {stats['total_files']}")
    print(f"  Indexed files: {stats['indexed_files']}")
    print(f"  Total chunks: {stats['total_chunks']}")
    print(f"  Vector DB size: {stats['vector_db_size']}")
    
    # Get recent sessions
    sessions = indexer.get_recent_sessions(limit=3)
    print(f"\nRecent sessions ({len(sessions)}):")
    for session in sessions:
        status = indexer.get_session_status(session['session_id'])
        progress = status.get('progress', {})
        print(f"  {session['session_id'][:16]}...")
        print(f"    Status: {status['status']}")
        print(f"    Progress: {progress}")


def example_6_distributed():
    """Example 6: Distributed processing with remote workers.
    
    To use this, set environment variables:
    export DISTRIBUTED_PROCESSING_ENABLED=true
    export REMOTE_WORKER_URLS=http://worker1:8001,http://worker2:8002
    
    And make sure remote workers are running and accessible.
    """
    print("\n=== Example 6: Distributed Processing ===\n")
    
    # Set environment variables for distributed processing
    os.environ['DISTRIBUTED_PROCESSING_ENABLED'] = 'true'
    os.environ['REMOTE_WORKER_URLS'] = 'http://localhost:8001'
    os.environ['REMOTE_WORKER_TIMEOUT'] = '30'
    os.environ['REMOTE_WORKER_RETRIES'] = '2'
    
    # Need to reload config
    import importlib
    import fs_rag.core.config as config_module
    importlib.reload(config_module)
    
    try:
        indexer = FilesystemIndexer()
        print(f"Strategy: {indexer.strategy.__class__.__name__}")
        print(f"Workers: {indexer.strategy.worker_urls}\n")
        
        # Index with distributed workers
        stats = indexer.index_directory(Path('./data'))
        print(f"Files processed: {stats['files_processed']}")
    except ValueError as e:
        print(f"Note: {e}")
        print("Make sure remote workers are running at the configured URLs.")


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        example_num = sys.argv[1]
        
        examples = {
            '1': example_1_sequential,
            '2': example_2_parallel_threads,
            '3': example_3_resumable_indexing,
            '4': example_4_error_handling,
            '5': example_5_monitoring,
            '6': example_6_distributed,
        }
        
        if example_num in examples:
            examples[example_num]()
        else:
            print(f"Example {example_num} not found")
            print("Available examples: 1-6")
    else:
        print("Parallel & Distributed Indexing Examples")
        print("=" * 50)
        print("\nUsage: python example_parallel_indexing.py <number>")
        print("\n1. Sequential processing (default)")
        print("2. Parallel processing with threads")
        print("3. Resumable indexing with progress tracking")
        print("4. Error handling and failure recovery")
        print("5. Monitoring and statistics")
        print("6. Distributed processing with remote workers")
