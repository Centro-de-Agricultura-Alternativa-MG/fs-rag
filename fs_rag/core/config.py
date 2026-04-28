"""Configuration management for FS-RAG."""

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


class VectorDBType(str, Enum):
    """Supported vector database types."""
    CHROMADB = "chromadb"
    QDRANT = "qdrant"


class EmbeddingsType(str, Enum):
    """Supported embedding providers."""
    OLLAMA = "ollama"
    OPENAI = "openai"


class LLMType(str, Enum):
    """Supported LLM providers."""
    OLLAMA = "ollama"
    OPENAI = "openai"


class Config(BaseSettings):
    """Application configuration from environment variables."""

    # Vector DB Configuration
    vector_db_type: VectorDBType = VectorDBType.CHROMADB
    vector_db_path: Path = Path("./data/vector_db")
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None

    # Embeddings Configuration
    embeddings_type: EmbeddingsType = EmbeddingsType.OLLAMA
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "nomic-embed-text"
    openai_api_key: Optional[str] = None
    openai_embedding_model: str = "text-embedding-3-small"
    ocr_use_gpu: bool = False

    # LLM Configuration
    llm_type: LLMType = LLMType.OLLAMA
    ollama_llm_base_url: str = "http://localhost:11434"
    ollama_llm_model: str = "mistral"
    openai_llm_api_key: Optional[str] = None
    openai_llm_model: str = "gpt-4"

    # Indexing Configuration
    index_dir: Path = Path("./data/index")
    index_batch_size: int = 32
    chunk_size: int = 512
    chunk_overlap: int = 50
    enable_filepath_injection: bool = True
    filepath_prefix_to_remove: str = ''

    # Search Configuration
    search_top_k: int = 5
    search_score_threshold: float = 0.5
    rag_search_optimizer: bool = True
    rag_optimizer_max_tokens: int = 32

    # Application Configuration
    log_level: str = "INFO"
    debug: bool = False
    skill_port: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def ensure_dirs(self) -> None:
        """Create necessary directories."""
        self.vector_db_path.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        Path("./data").mkdir(parents=True, exist_ok=True)


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get or create global config instance."""
    global _config
    if _config is None:
        _config = Config()
        _config.ensure_dirs()
    return _config
