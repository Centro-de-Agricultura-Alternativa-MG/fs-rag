"""OpenWebUI/OpenClaw skill wrapper for FS-RAG."""

from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

from fs_rag.core import get_config, get_logger
from fs_rag.indexer import FilesystemIndexer
from fs_rag.search import HybridSearchEngine
from fs_rag.rag import get_rag_pipeline

logger = get_logger(__name__)

# Request/Response models
class IndexRequest(BaseModel):
    directory: str
    force: bool = False


class IndexResponse(BaseModel):
    status: str
    stats: dict


class SearchRequest(BaseModel):
    query: str
    method: str = "hybrid"
    top_k: int = 5


class SearchResult(BaseModel):
    file_path: str
    content: str
    score: float
    metadata: dict


class SearchResponse(BaseModel):
    results: list[SearchResult]
    query: str
    method: str
    count: int


class AskRequest(BaseModel):
    question: str
    method: str = "hybrid"
    top_k: int = 5
    include_sources: bool = True


class Source(BaseModel):
    file: str
    score: float
    preview: str


class AskResponse(BaseModel):
    answer: str
    sources: list[Source] = []
    search_results_count: int
    method: str


# FastAPI app
app = FastAPI(
    title="FS-RAG Skill",
    description="Filesystem indexing and RAG-powered Q&A skill for OpenWebUI/OpenClaw",
    version="0.1.0"
)

config = get_config()


@app.post("/index", response_model=IndexResponse)
async def index(request: IndexRequest):
    """Index a directory for search."""
    try:
        logger.info(f"Received index request for: {request.directory}")
        indexer = FilesystemIndexer()
        stats = indexer.index_directory(request.directory, force_reindex=request.force)

        return IndexResponse(
            status="success",
            stats=stats
        )
    except Exception as e:
        logger.error(f"Indexing failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """Search the indexed documents."""
    try:
        logger.info(f"Search request: {request.query} (method: {request.method})")
        search_engine = HybridSearchEngine()
        results = search_engine.search(
            request.query,
            top_k=request.top_k,
            method=request.method
        )

        formatted_results = [
            SearchResult(
                file_path=r.file_path,
                content=r.content,
                score=r.score,
                metadata=r.metadata
            )
            for r in results
        ]

        return SearchResponse(
            results=formatted_results,
            query=request.query,
            method=request.method,
            count=len(formatted_results)
        )
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    """Answer a question using RAG."""
    try:
        logger.info(f"Question: {request.question}")
        rag = get_rag_pipeline()
        response = rag.answer_question(
            request.question,
            top_k=request.top_k,
            search_method=request.method,
            include_sources=request.include_sources
        )

        sources = []
        if request.include_sources and "sources" in response:
            sources = [
                Source(
                    file=s["file"],
                    score=s["score"],
                    preview=s["preview"]
                )
                for s in response["sources"]
            ]

        return AskResponse(
            answer=response["answer"],
            sources=sources,
            search_results_count=response["search_results_count"],
            method=request.method
        )
    except Exception as e:
        logger.error(f"Question answering failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/stats")
async def get_stats():
    """Get index statistics."""
    try:
        indexer = FilesystemIndexer()
        stats = indexer.get_index_stats()
        return stats
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "ok"}


@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    logger.info("FS-RAG Skill starting up")
    config.ensure_dirs()


def run_skill(host: str = "0.0.0.0", port: int = None):
    """Run the skill server."""
    if port is None:
        port = config.skill_port

    logger.info(f"Starting FS-RAG Skill on {host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_skill()
