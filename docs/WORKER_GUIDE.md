# FS-RAG Remote Worker Guide

## Overview

The FS-RAG Remote Worker is an HTTP service that provides distributed chunk processing capabilities. It exposes REST endpoints that allow other indexers to delegate file processing tasks, enabling:

- **Horizontal Scaling**: Run multiple workers on different machines
- **Load Balancing**: Distribute processing load across workers
- **Simple Integration**: HTTP API - works with any client
- **Reusable**: Leverages the same ProcessorFactory as the main indexer

## Quick Start

### 1. Run Worker Locally

```bash
# Default: runs on localhost:8001 with 1 worker
./run-worker.sh

# Custom port
./run-worker.sh 8002

# Custom port and host
./run-worker.sh 8001 0.0.0.0

# Multiple workers (uvicorn)
./run-worker.sh 8001 0.0.0.0 4
```

### 2. Check Health

```bash
curl http://localhost:8001/health

# Response:
{
  "status": "healthy",
  "service": "fs-rag-worker",
  "version": "1.0.0"
}
```

### 3. Get Info

```bash
curl http://localhost:8001/info

# Response:
{
  "worker": "fs-rag-remote-worker",
  "version": "1.0.0",
  "chunk_size": 512,
  "chunk_overlap": 50,
  "supported_formats": [".txt", ".pdf", ".docx", ...]
}
```

### 4. Process a File

```bash
curl -X POST http://localhost:8001/process \
  -H "Content-Type: application/json" \
  -d '{
    "filepath": "/path/to/file.txt",
    "chunk_size": 512,
    "chunk_overlap": 50
  }'

# Response:
{
  "chunks": [
    {
      "content": "chunk text...",
      "metadata": {
        "file_path": "/path/to/file.txt",
        "file_name": "file.txt",
        "chunk_index": 0,
        "file_size": 1024,
        "total_chunks": 3
      }
    },
    ...
  ],
  "error": null
}
```

## API Endpoints

### GET /health
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "service": "fs-rag-worker",
  "version": "1.0.0"
}
```

### GET /info
Get worker information and supported formats.

**Response:**
```json
{
  "worker": "fs-rag-remote-worker",
  "version": "1.0.0",
  "chunk_size": 512,
  "chunk_overlap": 50,
  "supported_formats": [...]
}
```

### POST /process
Process a file and return chunks.

**Request:**
```json
{
  "filepath": "/path/to/file",
  "chunk_size": 512,
  "chunk_overlap": 50
}
```

**Response (Success):**
```json
{
  "chunks": [
    {
      "content": "chunk text",
      "metadata": {
        "file_path": "...",
        "file_name": "...",
        "chunk_index": 0,
        "file_size": 1024,
        "total_chunks": 1
      }
    }
  ],
  "error": null
}
```

**Response (Error):**
```json
{
  "chunks": null,
  "error": "Error description"
}
```

## Configuration

Worker configuration is read from `.env` file:

```bash
# Chunk processing
CHUNK_SIZE=512              # Size of each chunk
CHUNK_OVERLAP=50            # Overlap between chunks

# Logging
LOG_LEVEL=INFO              # Log level

# File processing
FILEPATH_PREFIX_TO_REMOVE=  # Prefix to remove from paths
ENABLE_FILEPATH_INJECTION=true
```

## Integration with Distributed Indexer

Configure the main indexer to use this worker:

```bash
# Enable distributed processing
DISTRIBUTED_PROCESSING_ENABLED=true

# Point to workers
REMOTE_WORKER_URLS=http://localhost:8001,http://localhost:8002

# Worker communication settings
REMOTE_WORKER_TIMEOUT=30
REMOTE_WORKER_RETRIES=2
```

Then index normally:

```python
from fs_rag.indexer import FilesystemIndexer
from pathlib import Path

indexer = FilesystemIndexer()
stats = indexer.index_directory(Path('./data'))
```

The indexer will:
1. Scan files
2. Send each to a worker via HTTP POST /process
3. Collect chunks from worker responses
4. Process embeddings and store in vector DB
5. Automatically fallback to local processing if worker fails

## Deployment

### Local Testing
```bash
# Terminal 1: Start worker
./run-worker.sh 8001

# Terminal 2: Start indexer with distributed config
export DISTRIBUTED_PROCESSING_ENABLED=true
export REMOTE_WORKER_URLS=http://localhost:8001
python your_indexing_script.py
```

### Multi-Worker Setup
```bash
# Terminal 1: Worker on port 8001
./run-worker.sh 8001 0.0.0.0 4

# Terminal 2: Worker on port 8002
./run-worker.sh 8002 0.0.0.0 4

# Terminal 3: Indexer configured with both
export REMOTE_WORKER_URLS=http://localhost:8001,http://localhost:8002
python your_indexing_script.py
```

### Docker (Future)
```dockerfile
FROM python:3.11
WORKDIR /app
COPY . .
RUN ./setup.sh
EXPOSE 8001
CMD ["./run-worker.sh", "8001", "0.0.0.0"]
```

## Monitoring

### Check if Worker is Running

```bash
# Health check
curl http://localhost:8001/health

# Get logs (if using run-worker.sh)
# Logs appear in console output
```

### Logs
The worker logs all processing activity with prefixes:

```
[PROCESS]       - File processing request
[PROCESSOR]     - Processor selection
[EXTRACT]       - Text extraction
[CHUNK]         - Text chunking
[PROCESS DONE]  - Successful completion
[ERROR]         - Processing errors
```

Example:
```
[PROCESS] Received request for: /path/to/file.pdf
[PROCESSOR] Using: PDFProcessor
[EXTRACT] Extracting text from: /path/to/file.pdf
[EXTRACT DONE] Extracted 5234 characters
[CHUNK] Chunking text (size=512, overlap=50)
[CHUNK DONE] Created 15 chunks
[PROCESS DONE] Successfully processed /path/to/file.pdf
```

## Performance

### Single Worker
- **Throughput**: ~10-50 files/minute (depends on file size and type)
- **Memory**: ~500MB per worker
- **CPU**: Single core utilization

### Multiple Workers
```
Workers: 1  →  ~10-50 files/min
Workers: 2  →  ~20-100 files/min
Workers: 4  →  ~40-200 files/min
```

### Optimization Tips

1. **Run multiple workers**: `./run-worker.sh 8001 0.0.0.0 4`
2. **Use load balancer**: In production, use nginx/haproxy to distribute
3. **Adjust timeouts**: Increase `REMOTE_WORKER_TIMEOUT` for large files
4. **Monitor memory**: Adjust `CHUNK_SIZE` if memory is limited

## Troubleshooting

### Worker not responding

**Problem**: `Connection refused on localhost:8001`

**Solution**: 
1. Verify virtual environment is activated
2. Check if port is already in use: `lsof -i :8001`
3. Try different port: `./run-worker.sh 8002`

### File not found error

**Problem**: `"error": "File not found: /path/to/file"`

**Solution**:
- Ensure filepath is absolute and correct
- Verify file exists on worker machine
- Check file permissions (worker must be able to read)

### Unsupported file type

**Problem**: `"error": "No processor found for file type: .xyz"`

**Solution**:
- Check supported formats: `curl http://localhost:8001/info`
- File type is not supported by ProcessorFactory
- Convert to supported format (PDF, DOCX, TXT, etc.)

### Timeout during processing

**Problem**: `Worker request timeout (attempt 1/2)`

**Solution**:
1. Increase timeout: `REMOTE_WORKER_TIMEOUT=60`
2. Reduce chunk size: `CHUNK_SIZE=256`
3. Check worker resources (CPU, memory)
4. Use local processing instead: `DISTRIBUTED_PROCESSING_ENABLED=false`

### Worker crashes

**Problem**: Worker process exits unexpectedly

**Solution**:
1. Check logs for errors
2. Ensure dependencies are installed: `./setup.sh`
3. Verify Python version (3.9+): `python --version`
4. Check disk space and memory availability

## Advanced Usage

### Custom Port and Concurrency

```bash
# 8 concurrent workers on port 9000
./run-worker.sh 9000 0.0.0.0 8
```

### Python API

```python
from fs_rag.worker.server import create_app
from fastapi.testclient import TestClient

app = create_app()
client = TestClient(app)

# Process file directly
response = client.post("/process", json={
    "filepath": "/path/to/file.txt",
    "chunk_size": 512,
    "chunk_overlap": 50
})

chunks = response.json()["chunks"]
```

### Integration in Custom Code

```python
import requests

# Send file to worker for processing
response = requests.post(
    "http://localhost:8001/process",
    json={
        "filepath": "/path/to/file.txt",
        "chunk_size": 512,
        "chunk_overlap": 50
    },
    timeout=30
)

if response.status_code == 200:
    result = response.json()
    chunks = result.get("chunks", [])
    error = result.get("error")
else:
    print(f"Error: {response.status_code}")
```

## Architecture

```
Client (Indexer)
    ↓ HTTP POST /process
FS-RAG Worker
    ├─ FastAPI Server (uvicorn)
    ├─ ProcessorFactory
    │   ├─ TextProcessor
    │   ├─ PDFProcessor
    │   ├─ DocxProcessor
    │   └─ ... (more processors)
    ├─ Text Extraction
    ├─ Text Chunking
    └─ Response Serialization
    ↑ HTTP 200 + JSON chunks
Client
```

## Conclusion

The FS-RAG Remote Worker provides a simple, scalable way to distribute file processing across multiple machines. Combine with the distributed indexer for true horizontal scaling of document indexing pipelines.
