"""Skill server entry point."""
import argparse
from fs_rag.skill import run_skill

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FS-RAG Skill Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    args = parser.parse_args()

    run_skill(host=args.host, port=args.port)
