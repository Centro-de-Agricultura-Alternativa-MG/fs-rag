#!/bin/bash
# Run FS-RAG Remote Worker

if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Run ./setup.sh first."
    exit 1
fi

source venv/bin/activate

# Check if port is specified
PORT=${1:-8001}
HOST=${2:-0.0.0.0}
WORKERS=${3:-1}

echo "Starting FS-RAG Remote Worker..."
echo "  Port: $PORT"
echo "  Host: $HOST"
echo "  Workers: $WORKERS"
echo ""

python3 -m fs_rag.worker.server --port $PORT --host $HOST --workers $WORKERS
