#!/bin/bash
# Run FS-RAG Skill Server

if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Run ./setup.sh first."
    exit 1
fi

source venv/bin/activate

# Check if port is specified
PORT=${1:-8000}

echo "Starting FS-RAG Skill Server on port $PORT..."
python3 -m fs_rag.skill.server --port $PORT
