# Workflow State Tracking for Indexing

## Overview

The indexing system now tracks the complete workflow state for each file, allowing sessions to be resumed at any point in the processing pipeline. This enables robust recovery from interruptions without losing progress.

## Workflow Stages

Each file progresses through the following stages:

1. **scanned** - File has been discovered and added to the index
2. **processed** - File has been read and split into chunks
3. **embedded** - Chunks have been converted to embeddings
4. **stored** - Embeddings have been stored in the vector database
5. **completed** - All stages completed successfully and metadata updated

## Features

### 1. Enhanced Logging with File Output

- **Console logging**: All messages logged to stderr with colored output
- **File logging**: All messages also logged to `data/logs/indexer.log`
- **Debug information**: Comprehensive debug logs help diagnose issues
- **Automatic rotation**: Log files rotate at 100MB with 7-day retention

**Configuration:**
- Log level is controlled via `LOG_LEVEL` environment variable (default: INFO)
- Logs stored in directory specified by `logs_dir` config (default: `./data/logs`)

**Usage:**
```python
from fs_rag.core import get_config
from fs_rag.core.logger import get_logger

config = get_config()
config.ensure_dirs()
logger = get_logger(__name__, level=config.log_level, log_file=config.logs_dir / "indexer.log")
```

### 2. Workflow State Persistence

All workflow states are saved to the `workflow_state` database table:

```sql
CREATE TABLE workflow_state (
    session_id TEXT NOT NULL,
    file_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    stage TEXT NOT NULL,              -- scanned|processed|embedded|stored|completed
    stage_status TEXT DEFAULT 'pending',  -- pending|in_progress|completed|failed
    completed_at REAL,
    data TEXT,                        -- JSON with stage-specific metadata
    error_message TEXT,
    PRIMARY KEY (session_id, file_id, stage)
)
```

### 3. Session Resumption with Workflow Awareness

When resuming a session with `--interactive` flag:

1. System discovers interrupted sessions
2. User selects which session to resume
3. For each file in the session:
   - Check current workflow progress
   - Skip already-completed stages
   - Continue from the next pending stage
4. All intermediate states are preserved until final completion

**Example workflow for interrupted session:**

```
File: document.pdf
Initial run (interrupted after processing):
  - scanned: ✓ completed
  - processed: ✓ completed (3 chunks)
  - embedded: ✗ interrupted
  
Resume run:
  - scanned: skipped (already done)
  - processed: skipped (already done, load chunks)
  - embedded: ▶ execute (next pending stage)
  - stored: ▶ execute
  - completed: ▶ execute
```

### 4. State-Specific Data Storage

Each workflow stage can store metadata in JSON format:

```
scanned:
  - file_path (implicit)

processed:
  - chunk_count: number of chunks created
  - processing_time: seconds taken

embedded:
  - embedding_count: number of embeddings
  - embedding_time: seconds taken

stored:
  - chunk_ids_count: number of chunk IDs
  - storage_time: seconds taken
```

## Error Handling

If any stage fails:

1. Error is logged with detailed context
2. Error message stored in `workflow_state.error_message`
3. Stage marked as `failed` in database
4. File marked as failed in `indexing_progress`
5. Processing continues to next file
6. Session can be resumed later

Example error scenario:

```
File: large_document.pdf
[PROCESS] Processing...
[ERROR] Failed to process large_document.pdf: 'utf-8' codec can't decode byte 0xff...
  - workflow_state.processed = 'failed'
  - workflow_state.error_message = full error text
  - Can resume and either:
    a) Try processing again (if error was transient)
    b) Skip and continue (if error is permanent)
```

## Interactive Session Selection

When using `--interactive` flag:

```bash
python -m fs_rag.cli index /path/to/docs --interactive
```

The system displays:

```
================================================================================
AVAILABLE SESSIONS FOR RESUMPTION
================================================================================

1) Session: abc123def456 (in_progress) [root_dir_name]
   Progress: 45/100 files (45 completed, 10 failed, 45 pending)
   Latest: document42.pdf [embedded - pending]

2) Session: xyz789uvw012 (completed) [other_root_dir]
   Progress: 100/100 files (100 completed, 0 failed, 0 pending)
```

User selects session, and processing resumes from the last interrupted stage.

## Database Tables

### New Table: `workflow_state`

Tracks progress through each processing stage for every file:

| Column | Type | Purpose |
|--------|------|---------|
| session_id | TEXT | Links to indexing_sessions |
| file_id | TEXT | File hash (md5 of path + mtime) |
| file_path | TEXT | Full file path for logging |
| stage | TEXT | Processing stage name |
| stage_status | TEXT | pending/in_progress/completed/failed |
| completed_at | REAL | Unix timestamp when stage completed |
| data | TEXT | JSON with stage-specific metadata |
| error_message | TEXT | Error details if stage failed |

### Existing Table: `indexing_progress`

Still used for overall file status (pending/completed/failed):

| Column | Type | Purpose |
|--------|------|---------|
| session_id | TEXT | Links to indexing_sessions |
| file_id | TEXT | File hash |
| file_path | TEXT | Full file path |
| status | TEXT | Overall file status |
| processed_at | REAL | Timestamp of last update |
| error_message | TEXT | Overall error message |

## Sequential Processing Model

The indexing now follows a strictly sequential model **per file**:

```
For each file:
  ├─ Stage: scanned
  ├─ Stage: processed → chunks
  ├─ Stage: embedded → embeddings
  ├─ Stage: stored → vector DB
  └─ Stage: completed → metadata DB
```

This ensures:
- Complete state is available at each stage
- Intermediate states can be used for recovery
- No data loss if process is interrupted
- Deterministic and debuggable behavior

## Configuration

Add to `.env` to control logging:

```env
LOG_LEVEL=DEBUG        # INFO, DEBUG, WARNING, ERROR, CRITICAL
LOGS_DIR=./data/logs   # Directory for log files
```

## Example Usage

```python
from pathlib import Path
from fs_rag.indexer import FilesystemIndexer

indexer = FilesystemIndexer()

# Start new indexing session
stats = indexer.index_directory(
    root_dir=Path("/path/to/documents"),
    force_reindex=False,
    interactive=False
)

# Resume interrupted session interactively
stats = indexer.index_directory(
    interactive=True  # Shows available sessions
)

# Resume specific session by ID
stats = indexer.index_directory(
    resume_session_id="abc123def456"
)
```

## Debugging

### View Workflow State

```sql
-- Check workflow progress for a specific file
SELECT * FROM workflow_state 
WHERE session_id = 'abc123' 
AND file_path LIKE '%document.pdf%'
ORDER BY stage;

-- Find failed stages
SELECT * FROM workflow_state 
WHERE session_id = 'abc123' 
AND stage_status = 'failed';

-- Check latest error
SELECT file_path, stage, error_message 
FROM workflow_state 
WHERE session_id = 'abc123' 
AND error_message IS NOT NULL
ORDER BY completed_at DESC
LIMIT 1;
```

### View Logs

```bash
# Follow logs in real-time
tail -f data/logs/indexer.log

# Search for errors
grep "ERROR" data/logs/indexer.log

# See debug info
grep "DEBUG" data/logs/indexer.log | head -20
```

## Performance Considerations

- **Batch commits**: Database commits happen every 5 files to balance persistence vs performance
- **State tracking**: Minimal overhead - only 1 DB write per stage per file
- **Memory usage**: Fixed - only current file in memory at any time
- **Recovery time**: Depends on number of pending stages, not total files

## Future Enhancements

1. **Chunk caching**: Serialize processed chunks to avoid reprocessing
2. **Parallel resumption**: Resume multiple stages in parallel for same file
3. **Stage skipping**: Allow skipping failed stages with manual override
4. **State export**: Export workflow state to JSON for analysis
5. **Time estimates**: Predict completion time based on stage timing
