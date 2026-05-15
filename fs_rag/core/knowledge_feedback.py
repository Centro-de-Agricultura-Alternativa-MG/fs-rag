"""Knowledge Feedback Memory system for RAG auto-enrichment."""

import json
import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

from fs_rag.core import get_config, get_logger
from fs_rag.core.embeddings import get_embeddings_provider
from fs_rag.core.vector_db import get_vector_db
from fs_rag.rag import get_rag_pipeline

from fs_rag.processor import DocumentProcessor


logger = get_logger(__name__)


class KnowledgeFeedbackEvaluator:
    """Evaluates if a generated response deserves to be saved as knowledge."""

    def __init__(self):
        self.config = get_config()
        self.llm = self._get_llm()

    def _get_llm(self):
        """Get LLM provider for evaluation."""
        from fs_rag.rag import OllamaLLM, OpenAILLM

        if self.config.llm_type.value == "ollama":
            return OllamaLLM()
        elif self.config.llm_type.value == "openai":
            return OpenAILLM()
        else:
            raise ValueError(f"Unknown LLM type: {self.config.llm_type.value}")

    def _load_evaluator_instruction(self) -> str:
        """Load the knowledge feedback evaluator system instruction."""
        instruction_path = (
            Path(__file__).resolve().parents[1]
            / "system-instructions"
            / "knowledge_feedback_evaluator.md"
        )

        if not instruction_path.exists():
            logger.warning(f"Evaluator instruction not found: {instruction_path}")
            return ""

        try:
            return instruction_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to load evaluator instruction: {e}")
            return ""

    def _build_evaluation_prompt(
        self, question: str, response: str, context: str = ""
    ) -> str:
        """Build prompt for LLM evaluation."""
        instruction = self._load_evaluator_instruction()

        prompt = f"""{instruction}

---

## Input Data

**Original Question**:
{question}

**Generated Response**:
{response}

{"**Retrieved Context**:" + "\n" + context if context else ""}

---

Now evaluate and respond with JSON only."""
        print(prompt)
        return prompt

    def evaluate(
        self, question: str, response: str, context: str = ""
    ) -> dict:
        """
        Evaluate if a response should be saved as knowledge.

        Args:
            question: Original user question
            response: Generated response
            context: Retrieved context used for generation (optional)

        Returns:
            Dict with keys: approved (bool), usefulness_score (float), justification (str)
        """
        if not self.config.knowledge_feedback_enabled:
            logger.debug("Knowledge feedback is disabled")
            return {"approved": False, "usefulness_score": 0.0, "justification": ""}

        if not response or not response.strip():
            logger.debug("Empty response, rejecting")
            return {
                "approved": False,
                "usefulness_score": 0.0,
                "justification": "Empty response",
            }

        try:
            prompt = self._build_evaluation_prompt(question, response, context)

            logger.debug(f"Evaluating response for question: {question[:50]}...")

            eval_response = self.llm.generate(
                prompt, max_tokens=self.config.knowledge_feedback_evaluator_max_tokens
            )

            # Parse JSON response
            try:
                # Try to extract JSON if there's extra text
                json_start = eval_response.find("{")
                json_end = eval_response.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = eval_response[json_start:json_end]
                    result = json.loads(json_str)
                else:
                    result = json.loads(eval_response)

                # Validate required fields
                if (
                    "approved" not in result
                    or "usefulness_score" not in result
                    or "justification" not in result
                ):
                    logger.warning(
                        "Evaluator response missing required fields, rejecting"
                    )
                    return {
                        "approved": False,
                        "usefulness_score": 0.0,
                        "justification": "Invalid evaluator response",
                    }

                # Ensure usefulness_score is float and in [0, 1]
                score = float(result["usefulness_score"])
                score = max(0.0, min(1.0, score))

                return {
                    "approved": bool(result["approved"]),
                    "usefulness_score": score,
                    "justification": str(result["justification"])[:500],
                }

            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse evaluator JSON response: {e}")
                return {
                    "approved": False,
                    "usefulness_score": 0.0,
                    "justification": "Failed to parse evaluation",
                }

        except Exception as e:
            logger.error(f"Error evaluating response: {e}")
            return {
                "approved": False,
                "usefulness_score": 0.0,
                "justification": f"Evaluation error: {str(e)[:100]}",
            }


class KnowledgeFeedbackIndexer:
    """Indexes approved responses as reusable knowledge."""

    def __init__(self):
        self.config = get_config()
        self.embeddings = get_embeddings_provider()
        self.vector_db = get_vector_db()

    def _generate_feedback_id(self, question: str, response: str) -> str:
        """Generate unique ID for feedback response."""
        content = f"{question}:{response}"
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"feedback_{timestamp}_{content_hash}"

    def _create_combined_text(
        self, question: str, response: str, summary: str = ""
    ) -> str:
        """
        Create combined text for embedding.

        Combines question, response, and optional summary for better semantic understanding.
        """
        text = f"Question: {question}\n\nAnswer: {response}"
        if summary:
            text += f"\n\nSummary: {summary}"
        return text

    def _generate_summary(self, response: str) -> str:
        """Generate a brief summary of the response."""
        # Simple approach: take first 2 sentences or first 150 chars
        sentences = response.split(".")
        summary_parts = []
        for sentence in sentences[:2]:
            sentence = sentence.strip()
            if sentence:
                summary_parts.append(sentence)
        summary = ". ".join(summary_parts)
        if len(summary) > 150:
            summary = summary[:150] + "..."
        return summary

    def index_response(
        self,
        question: str,
        response: str,
        usefulness_score: float,
        search_results: Optional[list] = None,
    ) -> bool:
        """
        Index an approved response as knowledge.

        Args:
            question: Original user question
            response: Generated response
            usefulness_score: Score from evaluator
            search_results: Optional list of SearchResult objects for context

        Returns:
            True if successfully indexed, False otherwise
        """
        summary = self._generate_summary(response)
        combined_text = self._create_combined_text(question, response, summary)
        chunks = DocumentProcessor.chunk_text( file_path='knowledge_base' , text=combined_text)

        for combined_text in chunks:
            try:
                feedback_id = self._generate_feedback_id(question, response)

                # Create combined text for embedding

                # Generate embedding
                logger.debug(f"Generating embedding for feedback {feedback_id}")
                embedding = self.embeddings.embed(combined_text)

                # Create metadata
                metadata = {
                    "source_type": "knowledge_feedback",
                    "original_question": question[:500],
                    "usefulness_score": float(usefulness_score),
                    "created_at": datetime.now().isoformat(),
                    "summary": summary,
                }

                # Add source documents if available
                if search_results:
                    source_files = [
                        r.metadata.get("file_path", "unknown") for r in search_results[:3]
                    ]
                    metadata["source_documents"] = ";".join(source_files)

                # Index in vector DB
                logger.debug(f"Indexing feedback response {feedback_id} to vector DB")
                self.vector_db.add(
                    ids=[feedback_id],
                    embeddings=[embedding],
                    metadatas=[metadata],
                    documents=[combined_text],
                )

                # Store metadata in SQLite
                self._save_feedback_metadata(
                    feedback_id, question, response, usefulness_score, summary
                )

                logger.info(
                    f"Successfully indexed feedback response {feedback_id} with score {usefulness_score:.2f}"
                )
                return True

            except Exception as e:
                logger.error(f"Failed to index response: {e}")
                return False

    def _save_feedback_metadata(
        self,
        feedback_id: str,
        question: str,
        response: str,
        usefulness_score: float,
        summary: str,
    ) -> None:
        """Save feedback metadata to SQLite."""
        try:
            db_path = self.config.index_dir / "index.db"

            # Ensure table exists
            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback_responses (
                    id TEXT PRIMARY KEY,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    summary TEXT,
                    usefulness_score REAL NOT NULL,
                    embedding_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    source_type TEXT DEFAULT 'knowledge_feedback'
                )
            """
            )

            conn.execute(
                """
                INSERT INTO feedback_responses 
                (id, question, answer, summary, usefulness_score, embedding_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    feedback_id,
                    question[:2000],
                    response[:5000],
                    summary[:500],
                    usefulness_score,
                    feedback_id,
                ),
            )
            conn.commit()
            conn.close()

            logger.debug(f"Saved feedback metadata for {feedback_id}")

        except Exception as e:
            logger.warning(f"Failed to save feedback metadata: {e}")
