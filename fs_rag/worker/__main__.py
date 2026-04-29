"""FS-RAG Remote Worker Module

Run with:
    python -m fs_rag.worker --port 8001
    python -m fs_rag.worker.server --port 8001
"""

from fs_rag.worker.server import main

if __name__ == "__main__":
    main()
