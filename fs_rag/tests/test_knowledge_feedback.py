"""Tests for Knowledge Feedback Memory system."""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from fs_rag.core.knowledge_feedback import (
    KnowledgeFeedbackEvaluator,
    KnowledgeFeedbackIndexer,
)
from fs_rag.feedback import KnowledgeFeedbackProcessor


class TestKnowledgeFeedbackEvaluator:
    """Test the feedback evaluator."""

    def test_evaluator_initialization(self):
        """Test evaluator can be initialized."""
        evaluator = KnowledgeFeedbackEvaluator()
        assert evaluator is not None
        assert evaluator.config is not None

    def test_load_evaluator_instruction(self):
        """Test loading evaluator system instruction."""
        evaluator = KnowledgeFeedbackEvaluator()
        instruction = evaluator._load_evaluator_instruction()
        assert instruction is not None
        assert len(instruction) > 0
        assert "Knowledge Feedback Evaluator" in instruction or "evaluation" in instruction.lower()

    def test_build_evaluation_prompt(self):
        """Test prompt building for evaluation."""
        evaluator = KnowledgeFeedbackEvaluator()
        question = "How do I implement JWT auth?"
        response = "JWT is JSON Web Token. Use PyJWT library."
        context = "JWT documentation..."

        prompt = evaluator._build_evaluation_prompt(question, response, context)
        assert question in prompt
        assert response in prompt
        assert context in prompt

    @patch('fs_rag.core.knowledge_feedback.KnowledgeFeedbackEvaluator._get_llm')
    def test_evaluate_approved_response(self, mock_llm):
        """Test evaluating an approved response."""
        # Mock LLM response
        mock_llm_instance = MagicMock()
        mock_llm_instance.generate.return_value = json.dumps({
            "approved": True,
            "usefulness_score": 0.85,
            "justification": "Good implementation guidance"
        })
        mock_llm.return_value = mock_llm_instance

        evaluator = KnowledgeFeedbackEvaluator()
        evaluator.llm = mock_llm_instance

        result = evaluator.evaluate(
            question="How to implement JWT?",
            response="Use PyJWT library. Install with pip install PyJWT...",
            context=""
        )

        assert result["approved"] is True
        assert result["usefulness_score"] == 0.85
        assert "Good implementation" in result["justification"]

    @patch('fs_rag.core.knowledge_feedback.KnowledgeFeedbackEvaluator._get_llm')
    def test_evaluate_rejected_response(self, mock_llm):
        """Test evaluating a rejected response."""
        mock_llm_instance = MagicMock()
        mock_llm_instance.generate.return_value = json.dumps({
            "approved": False,
            "usefulness_score": 0.25,
            "justification": "Too generic"
        })
        mock_llm.return_value = mock_llm_instance

        evaluator = KnowledgeFeedbackEvaluator()
        evaluator.llm = mock_llm_instance

        result = evaluator.evaluate(
            question="What is AI?",
            response="AI is artificial intelligence.",
            context=""
        )

        assert result["approved"] is False
        assert result["usefulness_score"] < 0.5

    def test_evaluate_empty_response(self):
        """Test that empty responses are rejected."""
        evaluator = KnowledgeFeedbackEvaluator()
        result = evaluator.evaluate("Question?", "", "")
        assert result["approved"] is False


class TestKnowledgeFeedbackIndexer:
    """Test the feedback indexer."""

    def test_indexer_initialization(self):
        """Test indexer can be initialized."""
        indexer = KnowledgeFeedbackIndexer()
        assert indexer is not None
        assert indexer.config is not None
        assert indexer.embeddings is not None
        assert indexer.vector_db is not None

    def test_generate_feedback_id(self):
        """Test feedback ID generation."""
        indexer = KnowledgeFeedbackIndexer()
        question = "Test question"
        response = "Test response"

        id1 = indexer._generate_feedback_id(question, response)
        id2 = indexer._generate_feedback_id(question, response)

        assert id1.startswith("feedback_")
        assert id1 == id2  # Same input should produce same ID

    def test_create_combined_text(self):
        """Test combining question and response for embedding."""
        indexer = KnowledgeFeedbackIndexer()
        question = "How to code?"
        response = "Learn programming."
        summary = "Programming basics"

        combined = indexer._create_combined_text(question, response, summary)

        assert "Question:" in combined
        assert "Answer:" in combined
        assert "Summary:" in combined
        assert question in combined
        assert response in combined

    def test_generate_summary(self):
        """Test summary generation."""
        indexer = KnowledgeFeedbackIndexer()
        response = "First sentence. Second sentence. Third sentence."

        summary = indexer._generate_summary(response)

        assert summary is not None
        assert len(summary) > 0
        assert "First sentence" in summary

    @patch('fs_rag.core.knowledge_feedback.get_embeddings_provider')
    @patch('fs_rag.core.knowledge_feedback.get_vector_db')
    def test_index_response(self, mock_get_vector_db, mock_get_embeddings):
        """Test indexing an approved response."""
        import numpy as np
        
        mock_embeddings = MagicMock()
        mock_embeddings.embed.return_value = np.array([0.1] * 768)
        mock_get_embeddings.return_value = mock_embeddings
        
        mock_vector_db = MagicMock()
        mock_vector_db.add = MagicMock()
        mock_get_vector_db.return_value = mock_vector_db

        indexer = KnowledgeFeedbackIndexer()

        result = indexer.index_response(
            question="Test Q",
            response="Test response",
            usefulness_score=0.85
        )

        # Should not raise exception and should attempt to add to vector DB
        assert result is not None
        mock_vector_db.add.assert_called_once()


class TestKnowledgeFeedbackProcessor:
    """Test the feedback processor."""

    def test_processor_initialization(self):
        """Test processor can be initialized."""
        processor = KnowledgeFeedbackProcessor()
        assert processor is not None
        assert processor.config is not None
        assert processor.evaluator is not None
        assert processor.indexer is not None

    def test_process_async_skipped_when_disabled(self):
        """Test that async processing is skipped when disabled."""
        processor = KnowledgeFeedbackProcessor()
        
        with patch.object(processor.config, 'knowledge_feedback_enabled', False):
            # Should return None without processing
            result = processor.process_async("Q", "R")
            assert result is None

    @patch.object(KnowledgeFeedbackEvaluator, 'evaluate')
    @patch.object(KnowledgeFeedbackIndexer, 'index_response')
    def test_process_sync_approved_and_indexed(self, mock_index, mock_evaluate):
        """Test sync processing of approved response that gets indexed."""
        mock_evaluate.return_value = {
            "approved": True,
            "usefulness_score": 0.85,
            "justification": "Good"
        }
        mock_index.return_value = True

        processor = KnowledgeFeedbackProcessor()
        result = processor.process_sync(
            question="Test Q",
            response="Test R"
        )

        assert result["evaluated"] is True
        assert result["approved"] is True
        assert result["indexed"] is True
        assert result["score"] == 0.85

    @patch.object(KnowledgeFeedbackEvaluator, 'evaluate')
    def test_process_sync_approved_but_below_threshold(self, mock_evaluate):
        """Test sync processing when score is below minimum."""
        mock_evaluate.return_value = {
            "approved": True,
            "usefulness_score": 0.5,  # Below default 0.7 threshold
            "justification": "Below threshold"
        }

        processor = KnowledgeFeedbackProcessor()
        result = processor.process_sync(
            question="Test Q",
            response="Test R"
        )

        assert result["evaluated"] is True
        assert result["approved"] is False  # Should be rejected due to threshold
        assert result["indexed"] is False

    @patch.object(KnowledgeFeedbackEvaluator, 'evaluate')
    def test_process_sync_rejected(self, mock_evaluate):
        """Test sync processing of rejected response."""
        mock_evaluate.return_value = {
            "approved": False,
            "usefulness_score": 0.3,
            "justification": "Too generic"
        }

        processor = KnowledgeFeedbackProcessor()
        result = processor.process_sync(
            question="Test Q",
            response="Test R"
        )

        assert result["evaluated"] is True
        assert result["approved"] is False
        assert result["indexed"] is False

    def test_process_sync_empty_question(self):
        """Test that empty questions are rejected."""
        processor = KnowledgeFeedbackProcessor()
        result = processor.process_sync(
            question="",
            response="Test R"
        )

        assert result["evaluated"] is False
        assert result["approved"] is False
        assert result["error"] is not None

    def test_process_async_spawns_thread(self):
        """Test that async processing spawns a thread."""
        processor = KnowledgeFeedbackProcessor()
        
        with patch('threading.Thread') as mock_thread:
            processor.process_async("Q", "R")
            # Thread should be started
            mock_thread.assert_called_once()
            mock_thread.return_value.start.assert_called_once()


class TestIntegration:
    """Integration tests."""

    def test_full_pipeline_disabled(self):
        """Test that full pipeline can be disabled."""
        processor = KnowledgeFeedbackProcessor()
        
        # When knowledge_feedback_enabled is False, async should not spawn thread
        with patch.object(processor.config, 'knowledge_feedback_enabled', False):
            # process_async should return None without spawning thread
            with patch('threading.Thread') as mock_thread:
                result = processor.process_async("Q?", "R")
                # Thread should NOT be created when disabled
                mock_thread.assert_not_called()
