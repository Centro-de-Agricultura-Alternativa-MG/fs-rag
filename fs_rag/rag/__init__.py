"""RAG pipeline for question answering over indexed documents."""

from typing import Optional
from abc import ABC, abstractmethod

from fs_rag.core import get_config, get_logger
from fs_rag.search import HybridSearchEngine, SearchResult
from pathlib import Path
import tiktoken

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
logger = get_logger(__name__)
console = Console()


class LLMProvider(ABC):
    """Base class for LLM providers."""

    @abstractmethod
    def generate(self, prompt: str, max_tokens: int = 512) -> str:
        """Generate text from a prompt."""
        pass


class OllamaLLM(LLMProvider):
    """Ollama LLM provider."""

    def __init__(self, base_url: str = "", model: str = ""):
        self.base_url = base_url or get_config().ollama_llm_base_url
        self.model = model or get_config().ollama_llm_model

        try:
            import ollama
            self.client = ollama.Client(host=self.base_url)
        except ImportError:
            logger.error("ollama library not installed. Install with: pip install ollama")
            self.client = None

    def generate(self, prompt: str, max_tokens: int = 512) -> str:
        if not self.client:
            raise RuntimeError("Ollama client not initialized")

        try:
            response = self.client.generate(
                model=self.model,
                prompt=prompt,
                stream=False,
            )
            return response["response"].strip()
        except Exception as e:
            logger.error(f"Error generating with Ollama: {e}")
            raise


class OpenAILLM(LLMProvider):
    """OpenAI LLM provider."""

    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = api_key or get_config().openai_llm_api_key
        self.model = model or get_config().openai_llm_model

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

    def generate(self, prompt: str, max_tokens: int = 512) -> str:
        if not self.client:
            raise RuntimeError("OpenAI client not initialized")

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.7,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error generating with OpenAI: {e}")
            raise


class RAGPipeline:
    """RAG (Retrieval-Augmented Generation) pipeline."""

    def __init__(self, llm_type: Optional[str] = None):
        self.config = get_config()
        self.search_engine = HybridSearchEngine()

        # Initialize LLM
        if llm_type is None:
            llm_type = self.config.llm_type.value

        if llm_type == "ollama":
            self.llm = OllamaLLM()
        elif llm_type == "openai":
            self.llm = OpenAILLM()
        else:
            raise ValueError(f"Unknown LLM type: {llm_type}")

    def _format_context(self, search_results: list[SearchResult], max_context_length: int = 2000) -> str:
        """Format search results into context for the LLM."""
        context_parts = []
        current_length = 0

        for i, result in enumerate(search_results):
            file_path = result.metadata.get("file_path", "unknown")
            snippet = f"{result.content} [CHUNK TRUNCADA]"
            result_text = f"[Documento {i+1}: {file_path}]\n{snippet}\n"

            #if current_length + len(result_text) > max_context_length:
            #    break

            context_parts.append(result_text)
            current_length += len(result_text)

        return "\n".join(context_parts)

    def _build_prompt(self, question: str, context: str , request_type: str) -> str:
        """Build the prompt for the LLM."""
        import os
        from dotenv import load_dotenv
        load_dotenv()
        DEFAULT_MODEL = "gpt-4o-mini"

        system_instructions = 'default.txt'
        
        if request_type:
            system_instructions = f'{request_type}.txt'


        # Load template
        template_path = Path(__file__).resolve().parents[1] / "system-instructions" / f"{system_instructions}"
        prompt_template = template_path.read_text(encoding="utf-8")

        prompt = prompt_template.format(context=context, question=question)

        # --- Model selection ---
        openai_model = os.getenv("OPENAI_LLM_MODEL")
        ollama_model = os.getenv("OLLAMA_LLM_MODEL")

        if openai_model:
            model = openai_model
        elif ollama_model:
            model = ollama_model
        else:
            model = DEFAULT_MODEL

        # --- Encoding selection with fallback ---
        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            # fallback if model not supported
            encoding = tiktoken.encoding_for_model(DEFAULT_MODEL)

        # --- Token counting ---
        tokens = len(encoding.encode(prompt))

        console.print(Panel(prompt, title="Prompt"))


        logger.info(f"Model used for tokenization: {model}")
        logger.info(f"Token estimate: {tokens}")

        return prompt


    def answer_question(
        self,
        question: str,
        top_k: int = 5,
        search_method: str = "hybrid",
        include_sources: bool = True,
        max_tokens: int = 512,
        request_type: str = "default"
    ) -> dict:
        """
        Answer a question using the RAG pipeline.

        Args:
            question: The question to answer
            top_k: Number of documents to retrieve
            search_method: Search method ("keyword", "semantic", or "hybrid")
            include_sources: Whether to include source documents in the response
            max_tokens: Maximum tokens for LLM response

        Returns:
            Dictionary with answer, sources, and metadata
        """
        logger.info(f"Answering question: {question}")

        # Retrieve relevant documents
        search_results = self.search_engine.search(
            question,
            top_k=top_k,
            method=search_method
        )

        if not search_results:
            logger.warning("No search results found")
            return {
                "answer": "I could not find relevant documents to answer this question.",
                "sources": [],
                "search_results_count": 0,
                "method": search_method,
            }

        # Format context
        context = self._format_context(search_results)

        # Build and execute prompt
        prompt = self._build_prompt(question, context , request_type)

        try:
            answer = self.llm.generate(prompt, max_tokens=max_tokens)
        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            return {
                "answer": f"Error generating answer: {str(e)}",
                "sources": [],
                "search_results_count": len(search_results),
                "method": search_method,
                "error": str(e),
            }

        # Format response
        response = {
            "answer": answer,
            "search_results_count": len(search_results),
            "method": search_method,
        }

        if include_sources:
            response["sources"] = [
                {
                    "file": result.metadata.get("file_path", "unknown"),
                    "score": round(result.score, 3),
                    "preview": result.content[:200],
                }
                for result in search_results
            ]

        return response

    def batch_answer_questions(
        self,
        questions: list[str],
        top_k: int = 5,
        search_method: str = "hybrid",
        include_sources: bool = True
    ) -> list[dict]:
        """Answer multiple questions."""
        return [
            self.answer_question(q, top_k=top_k, search_method=search_method, include_sources=include_sources)
            for q in questions
        ]


def get_rag_pipeline(llm_type: Optional[str] = None) -> RAGPipeline:
    """Get a RAG pipeline instance."""
    return RAGPipeline(llm_type=llm_type)
