"""Remote worker service for distributed chunk processing.

This service exposes a FastAPI HTTP endpoint that other indexers can
use to delegate file processing. The worker uses the standard
ProcessorFactory to extract and chunk documents.

Usage:
    python -m fs_rag.worker.server --port 8001
    
Configuration (via .env):
    WORKER_PORT=8001
    CHUNK_SIZE=512
    CHUNK_OVERLAP=50
    LOG_LEVEL=INFO
"""

import argparse
import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

from fs_rag.core import get_config, get_logger
from fs_rag.processor import ProcessorFactory, DocumentChunk

logger = get_logger(__name__)


class ProcessFileRequest(BaseModel):
    """Request to process a file."""
    filepath: str
    chunk_size: int = 512
    chunk_overlap: int = 50


class ChunkResult(BaseModel):
    """Single chunk in response."""
    content: str
    metadata: dict


class ProcessFileResponse(BaseModel):
    """Response with processed chunks."""
    chunks: Optional[list[ChunkResult]] = None
    error: Optional[str] = None


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="FS-RAG Remote Worker",
        description="HTTP service for remote chunk processing",
        version="1.0.0"
    )

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "fs-rag-worker",
            "version": "1.0.0"
        }

    @app.post("/process", response_model=ProcessFileResponse)
    async def process_file(request: ProcessFileRequest):
        """Process a file and return chunks.
        
        Args:
            request: ProcessFileRequest with filepath and chunk parameters
            
        Returns:
            ProcessFileResponse with chunks or error
        """
        filepath = Path(request.filepath)
        
        logger.info(f"[PROCESS] Received request for: {filepath}")
        
        # Validate file exists
        if not filepath.exists():
            error_msg = f"File not found: {filepath}"
            logger.error(f"[ERROR] {error_msg}")
            return ProcessFileResponse(chunks=None, error=error_msg)
        
        try:
            # Get processor for this file
            processor = ProcessorFactory.get_processor(filepath)
            if not processor:
                error_msg = f"No processor found for file type: {filepath.suffix}"
                logger.warning(f"[ERROR] {error_msg}")
                return ProcessFileResponse(chunks=None, error=error_msg)
            
            logger.debug(f"[PROCESSOR] Using: {processor.__class__.__name__}")
            
            # Extract text
            logger.debug(f"[EXTRACT] Extracting text from: {filepath}")
            text = processor.extract_text(filepath)
            
            if not text or len(text.strip()) < 10:
                error_msg = f"Extracted text too short or empty from: {filepath}"
                logger.warning(f"[ERROR] {error_msg}")
                return ProcessFileResponse(chunks=None, error=error_msg)
            
            logger.debug(f"[EXTRACT DONE] Extracted {len(text)} characters")
            
            # Chunk text
            logger.debug(f"[CHUNK] Chunking text (size={request.chunk_size}, overlap={request.chunk_overlap})")
            chunks_text = processor.chunk_text(
                file_path=str(filepath),
                text=text,
                chunk_size=request.chunk_size,
                chunk_overlap=request.chunk_overlap
            )
            
            logger.info(f"[CHUNK DONE] Created {len(chunks_text)} chunks")
            
            # Build response with chunk metadata
            result_chunks = []
            for i, chunk_text in enumerate(chunks_text):
                chunk = ChunkResult(
                    content=chunk_text,
                    metadata={
                        "file_path": str(filepath),
                        "file_name": filepath.name,
                        "chunk_index": i,
                        "file_size": filepath.stat().st_size,
                        "total_chunks": len(chunks_text)
                    }
                )
                result_chunks.append(chunk)
            
            logger.info(f"[PROCESS DONE] Successfully processed {filepath}")
            return ProcessFileResponse(chunks=result_chunks, error=None)
            
        except Exception as e:
            error_msg = f"Error processing file {filepath}: {str(e)}"
            logger.exception(f"[ERROR] {error_msg}")
            return ProcessFileResponse(chunks=None, error=error_msg)

    @app.get("/info")
    async def info():
        """Get worker information and supported formats."""
        config = get_config()
        
        # Get supported formats from ProcessorFactory
        supported_formats = set()
        for processor_class in [
            getattr(ProcessorFactory, attr)
            for attr in dir(ProcessorFactory)
            if not attr.startswith('_')
        ]:
            pass  # We'll just list the main formats
        
        return {
            "worker": "fs-rag-remote-worker",
            "version": "1.0.0",
            "chunk_size": config.chunk_size,
            "chunk_overlap": config.chunk_overlap,
            "supported_formats": [
                ".txt", ".md", ".pdf", ".docx", ".doc",
                ".csv", ".json", ".xlsx", ".xls",
                ".png", ".jpg", ".jpeg"
            ]
        }

    return app


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="FS-RAG Remote Worker for distributed chunk processing"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port to run the worker on (default: 8001)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of uvicorn workers (default: 1)"
    )
    
    args = parser.parse_args()
    
    # Log startup info
    logger.info("=" * 80)
    logger.info("FS-RAG Remote Worker")
    logger.info("=" * 80)
    logger.info(f"Starting worker on {args.host}:{args.port}")
    logger.info(f"Workers: {args.workers}")
    logger.info("=" * 80)
    
    # Create app and run
    app = create_app()
    
    try:
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            workers=args.workers,
            log_level="info"
        )
    except KeyboardInterrupt:
        logger.info("Worker shutdown")
    except Exception as e:
        logger.exception(f"Worker error: {e}")
        raise


if __name__ == "__main__":
    main()
