"""Async processor for Knowledge Feedback Memory pipeline."""

import threading
import traceback
from typing import Optional

from fs_rag.core import get_config, get_logger
from fs_rag.core.knowledge_feedback import (
    KnowledgeFeedbackEvaluator,
    KnowledgeFeedbackIndexer,
)

logger = get_logger(__name__)


class KnowledgeFeedbackProcessor:
    """Orchestrates async evaluation and indexing of responses."""

    def __init__(self):
        self.config = get_config()
        self.evaluator = KnowledgeFeedbackEvaluator()
        self.indexer = KnowledgeFeedbackIndexer()

    def process_async(
        self,
        question: str,
        response: str,
        search_results: Optional[list] = None,
        context: str = "",
    ) -> None:
        """
        Process response asynchronously (non-blocking).

        Spawns a daemon thread that evaluates and conditionally indexes the response.

        Args:
            question: Original user question
            response: Generated response
            search_results: List of SearchResult objects from retrieval
            context: Retrieved context text (optional)
        """
        if not self.config.knowledge_feedback_enabled:
            logger.debug("Knowledge feedback disabled, skipping async processing")
            return

        if not self.config.knowledge_feedback_async_processing:
            logger.debug("Async processing disabled, skipping")
            return

        # Spawn daemon thread to avoid blocking user response
        thread = threading.Thread(
            target=self._process_internal,
            args=(question, response, search_results, context),
            daemon=True,
        )
        thread.start()
        logger.debug(f"Spawned async feedback processor thread: {thread.name}")

    def process_sync(
        self,
        question: str,
        response: str,
        search_results: Optional[list] = None,
        context: str = "",
    ) -> dict:
        """
        Process response synchronously (blocking).

        Useful for testing or when you need immediate results.

        Args:
            question: Original user question
            response: Generated response
            search_results: List of SearchResult objects from retrieval
            context: Retrieved context text (optional)

        Returns:
            Dict with keys: approved, evaluated, indexed, score, error
        """
        return self._process_internal(question, response, search_results, context)

    def _process_internal(
        self,
        question: str,
        response: str,
        search_results: Optional[list] = None,
        context: str = "",
    ) -> dict:
        """Internal processing logic."""
        result = {
            "approved": False,
            "evaluated": False,
            "indexed": False,
            "score": 0.0,
            "error": None,
        }

        try:
            if not question or not response:
                logger.warning("Empty question or response, skipping")
                result["error"] = "Empty question or response"
                return result

            logger.info(
                f"Processing feedback for question: {question[:50]}..."
            )

            # Step 1: Evaluate response
            logger.debug("Step 1: Evaluating response...")
            evaluation = self.evaluator.evaluate(question, response, context)

            result["evaluated"] = True
            result["score"] = evaluation.get("usefulness_score", 0.0)
            result["approved"] = evaluation.get("approved", False)

            if not result["approved"]:
                logger.info(
                    f"Response rejected by evaluator (score: {result['score']:.2f}). "
                    f"Reason: {evaluation.get('justification', 'unknown')}"
                )
                return result

            min_score = self.config.knowledge_feedback_min_usefulness_score
            if result["score"] < min_score:
                logger.info(
                    f"Response score {result['score']:.2f} below minimum {min_score}. Rejected."
                )
                result["approved"] = False
                return result

            # Step 2: Index approved response
            logger.debug("Step 2: Indexing approved response...")
            indexed = self.indexer.index_response(
                question=question,
                response=response,
                usefulness_score=result["score"],
                search_results=search_results,
            )

            result["indexed"] = indexed

            if indexed:
                logger.info(
                    f"Successfully processed feedback response (score: {result['score']:.2f})"
                )
            else:
                logger.warning("Failed to index approved response")

            return result

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Error processing feedback: {error_msg}")
            logger.debug(traceback.format_exc())
            result["error"] = error_msg
            return result
