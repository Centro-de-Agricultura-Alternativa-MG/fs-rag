#!/bin/bash
# Run FS-RAG CLI

if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Run ./setup.sh first."
    exit 1
fi

source venv/bin/activate
python3 -m fs_rag.cli.main "$@"
