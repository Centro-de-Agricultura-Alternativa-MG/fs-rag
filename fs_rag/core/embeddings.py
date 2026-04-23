"""Embedding providers abstraction."""

from abc import ABC, abstractmethod
from typing import Optional
import numpy as np

from fs_rag.core import get_config, get_logger

logger = get_logger(__name__)


class EmbeddingsProvider(ABC):
    """Base class for embedding providers."""

    @abstractmethod
    def embed(self, text: str) -> np.ndarray:
        """Embed a single text string."""
        pass

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        """Embed multiple text strings."""
        pass


class OllamaEmbeddings(EmbeddingsProvider):
    """Embeddings via Ollama."""

    def __init__(self, base_url: str = "", model: str = ""):
        self.base_url = base_url or get_config().ollama_base_url
        self.model = model or get_config().ollama_model

        try:
            import ollama
            self.client = ollama.Client(host=self.base_url)
        except ImportError:
            logger.error("ollama library not installed. Install with: pip install ollama")
            self.client = None

    def embed(self, text: str) -> np.ndarray:
        if not self.client:
            raise RuntimeError("Ollama client not initialized")
        try:
            response = self.client.embeddings(model=self.model, prompt=text)
            return np.array(response["embedding"])
        except Exception as e:
            logger.error(f"Error embedding text with Ollama: {e}")
            raise

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        embeddings = []
        for text in texts:
            embeddings.append(self.embed(text))
        return embeddings


class OpenAIEmbeddings(EmbeddingsProvider):
    """Embeddings via OpenAI API."""

    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = api_key or get_config().openai_api_key
        self.model = model or get_config().openai_embedding_model

        if not self.api_key:
            logger.error("OpenAI API key not configured")
            self.client = None
            return

        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key)
        except ImportError:
            logger.error("openai library not installed. Install with: pip install openai")
            self.client = None

    def embed(self, text: str) -> np.ndarray:
        if not self.client:
            raise RuntimeError("OpenAI client not initialized")
        try:
            response = self.client.embeddings.create(model=self.model, input=text)
            return np.array(response.data[0].embedding)
        except Exception as e:
            logger.error(f"Error embedding text with OpenAI: {e}")
            raise

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        if not self.client:
            raise RuntimeError("OpenAI client not initialized")
        try:
            response = self.client.embeddings.create(model=self.model, input=texts)
            embeddings = [np.array(item.embedding) for item in response.data]
            return sorted(embeddings, key=lambda x: response.data.index(x))
        except Exception as e:
            logger.error(f"Error embedding batch with OpenAI: {e}")
            raise


def get_embeddings_provider() -> EmbeddingsProvider:
    """Get the configured embeddings provider."""
    config = get_config()
    if config.embeddings_type.value == "ollama":
        return OllamaEmbeddings()
    elif config.embeddings_type.value == "openai":
        return OpenAIEmbeddings()
    else:
        raise ValueError(f"Unknown embeddings type: {config.embeddings_type}")
