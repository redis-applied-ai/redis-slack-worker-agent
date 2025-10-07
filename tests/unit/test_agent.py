"""
Unit tests for the RAG (Retrieval Augmented Generation) module.
"""

import json
import logging
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.agent import answer_question
from app.agent.tools.search_knowledge_base import (
    search_knowledge_base as retrieve_context,
)
from app.utilities.database import get_document_index, get_vectorizer

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def initialize_globals():
    """Initialize global vectorizer and index once for all tests to avoid concurrent initialization"""
    logger.info("Pre-initializing vectorizer and index for test session...")
    try:
        # Pre-warm the global instances
        vectorizer = get_vectorizer()
        index = get_document_index()
        logger.info("Global instances initialized successfully")
        return {"vectorizer": vectorizer, "index": index}
    except Exception as e:
        logger.error(f"Failed to initialize globals: {e}")
        pytest.fail(f"Could not initialize test dependencies: {e}")


class TestRAGFunctions:
    """Test cases for RAG utility functions."""

    @pytest.mark.asyncio
    @patch("app.agent.tools.search_knowledge_base.VectorQuery")
    async def test_retrieve_context_with_search_query(self, mock_vector_query):
        """Test retrieve_context with search query (agentic RAG mode)."""
        # Setup
        mock_index = AsyncMock()
        mock_vectorizer = Mock()
        mock_vectorizer.embed.return_value = b"fake_vector"
        mock_results = [
            {
                "name": "Andrew",
                "description": "Agent specialist",
            }
        ]
        mock_index.query.return_value = mock_results
        search_query = "agents"

        # Execute
        result = await retrieve_context(mock_index, mock_vectorizer, search_query)

        # Verify - should return formatted string with search query header
        expected = "Search results for 'agents':\n1. Andrew: Agent specialist"
        assert result == expected
        mock_index.query.assert_called_once()

        # Check that VectorQuery was called with correct parameters
        call_args = mock_vector_query.call_args
        assert call_args[1]["vector"] == b"fake_vector"
        assert call_args[1]["vector_field_name"] == "vector"
        assert call_args[1]["return_fields"] == ["name", "description"]
        assert call_args[1]["num_results"] == 5

    @pytest.mark.asyncio
    @patch("app.agent.tools.search_knowledge_base.VectorQuery")
    async def test_retrieve_context_without_search_query(self, mock_vector_query):
        """Test retrieve_context without search query (legacy mode)."""
        # Setup
        mock_index = AsyncMock()
        mock_vectorizer = Mock()
        mock_vectorizer.embed.return_value = b"fake_vector"
        mock_results = [
            {
                "name": "Andrew",
                "description": "Agent specialist",
            }
        ]
        mock_index.query.return_value = mock_results

        # Execute
        result = await retrieve_context(mock_index, mock_vectorizer, "")

        # Verify - should return formatted string with search query header (even for empty query)
        expected = "Search results for '':\n1. Andrew: Agent specialist"
        assert result == expected
        mock_index.query.assert_called_once()

        # Check that VectorQuery was called with correct parameters
        call_args = mock_vector_query.call_args
        assert call_args[1]["vector"] == b"fake_vector"
        assert call_args[1]["vector_field_name"] == "vector"
        assert call_args[1]["return_fields"] == ["name", "description"]
        assert call_args[1]["num_results"] == 5

    @pytest.mark.asyncio
    @patch("app.agent.tools.search_knowledge_base.VectorQuery")
    async def test_retrieve_context_empty_results(self, mock_vector_query):
        """Test retrieve_context handles empty results gracefully."""
        # Setup
        mock_index = AsyncMock()
        mock_vectorizer = Mock()
        mock_vectorizer.embed.return_value = b"fake_vector"
        mock_index.query.return_value = []

        # Test with search query
        result = await retrieve_context(mock_index, mock_vectorizer, "test")
        assert result == "No relevant information found for query: 'test'"

        # Verify first call was made
        assert mock_index.query.call_count == 1

        # Reset mock for second test
        mock_index.reset_mock()
        mock_index.query.return_value = []  # Reset the return value too

        # Test without search query
        result = await retrieve_context(mock_index, mock_vectorizer, "")
        assert result == "No relevant information found for query: ''"

        # Verify second call was made
        assert mock_index.query.call_count == 1

    @pytest.mark.asyncio
    @patch("app.agent.tools.search_knowledge_base.VectorQuery")
    async def test_retrieve_context_with_multiple_results(self, mock_vector_query):
        """Test retrieve_context handles multiple results correctly."""
        mock_index = AsyncMock()
        mock_vectorizer = Mock()
        mock_vectorizer.embed.return_value = b"fake_vector"

        # Test with multiple results
        test_results = [
            {
                "name": "Andrew",
                "description": "Agent specialist",
            },
            {
                "name": "Tyler",
                "description": "RedisVL expert",
            },
            {
                "name": "Justin",
                "description": "Research background",
            },
        ]

        mock_index.query.return_value = test_results

        # Test with search query (agentic mode)
        result = await retrieve_context(mock_index, mock_vectorizer, "team")

        # Should handle multiple results gracefully
        assert isinstance(result, str)
        assert len(result) > 0

        # Should contain information from the results
        lines = result.split("\n")
        assert len(lines) == 4  # 1 header + 3 results

        # Verify all team members are included
        assert "1. Andrew: Agent specialist" in result
        assert "2. Tyler: RedisVL expert" in result
        assert "3. Justin: Research background" in result
        assert "Search results for 'team':" in result

        # Test without search query (legacy mode)
        mock_index.reset_mock()
        result = await retrieve_context(mock_index, mock_vectorizer, "")
        lines = result.split("\n")
        assert len(lines) == 4  # Header + 3 team members

        # Verify all team members are included with numbering
        assert "Andrew: Agent specialist" in result
        assert "Tyler: RedisVL expert" in result
        assert "Justin: Research background" in result

    @pytest.mark.asyncio
    @patch("app.agent.tools.search_knowledge_base.search_knowledge_base")
    @patch("app.agent.tools.web_search.perform_web_search")
    @patch("app.agent.tools.glean_search.search_glean")
    @patch("app.agent.create_initial_message_without_search")
    @patch("app.agent.core.get_instrumented_client")
    async def test_answer_question_success(
        self,
        mock_get_instrumented_client,
        mock_create_initial_message_without_search,
        mock_search_glean,
        mock_web_search,
        mock_knowledge_search,
    ):
        """Test that answer_question returns the expected response."""
        # Setup mocks
        mock_client = Mock()
        mock_chat = Mock()
        mock_completions = Mock()
        mock_create = Mock()

        mock_client.chat = mock_chat
        mock_chat.completions = mock_completions
        mock_completions.create = mock_create

        mock_instrumented_client = Mock()
        mock_instrumented_client._client = mock_client
        mock_get_instrumented_client.return_value = mock_instrumented_client

        mock_create_initial_message_without_search.return_value = "Test message"

        # Mock tool functions
        mock_knowledge_search.return_value = "Knowledge base search results"
        mock_web_search.return_value = "Web search results"
        mock_search_glean.return_value = "Glean search results"

        # Mock response
        mock_response = Mock()
        mock_message = Mock()
        mock_message.content = "Andrew is the best choice for agents."
        mock_message.tool_calls = None
        mock_message.model_dump.return_value = {
            "role": "assistant",
            "content": "Andrew is the best choice for agents.",
        }
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = mock_message
        # Add usage attribute for metrics tracking
        mock_usage = Mock()
        mock_usage.total_tokens = 100
        mock_response.usage = mock_usage
        mock_create.return_value = mock_response

        # Mock index and vectorizer
        mock_index = AsyncMock()
        mock_vectorizer = Mock()

        # Execute
        result = await answer_question(
            mock_index, mock_vectorizer, "test query", "test_session", "test_user"
        )

        # Verify
        assert result == "Andrew is the best choice for agents."
        assert mock_create.call_count >= 1

    @pytest.mark.asyncio
    @patch("app.agent.create_initial_message_without_search")
    @patch("app.agent.core.get_instrumented_client")
    async def test_answer_question_uses_system_prompt(
        self, mock_get_instrumented_client, mock_create_initial_message_without_search
    ):
        """Test that answer_question uses the correct system prompt."""
        # Setup mocks
        mock_client = Mock()
        mock_chat = Mock()
        mock_completions = Mock()
        mock_create = Mock()

        mock_client.chat = mock_chat
        mock_chat.completions = mock_completions
        mock_completions.create = mock_create

        mock_instrumented_client = Mock()
        mock_instrumented_client._client = mock_client
        mock_get_instrumented_client.return_value = mock_instrumented_client

        mock_create_initial_message_without_search.return_value = "Test message"

        # Mock response
        mock_response = Mock()
        mock_message = Mock()
        mock_message.content = "Test response"
        mock_message.tool_calls = None
        mock_message.model_dump.return_value = {
            "role": "assistant",
            "content": "Test response",
        }
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = mock_message
        # Add usage attribute for metrics tracking
        mock_usage = Mock()
        mock_usage.total_tokens = 150
        mock_response.usage = mock_usage
        mock_create.return_value = mock_response

        # Mock index and vectorizer
        mock_index = AsyncMock()
        mock_vectorizer = Mock()

        # Execute
        await answer_question(
            mock_index, mock_vectorizer, "test query", "test_session", "test_user"
        )

        # Verify OpenAI was called
        assert mock_create.call_count >= 1

        # Verify system prompt was used - use the first call
        call_args = mock_create.call_args_list[0]
        messages = call_args[1]["messages"]
        system_msg = next(msg for msg in messages if msg["role"] == "system")
        assert "Applied AI team at Redis" in system_msg["content"]

    @pytest.mark.asyncio
    @patch("app.agent.create_initial_message_without_search")
    @patch("app.agent.core.get_instrumented_client")
    async def test_answer_question_openai_error(
        self, mock_get_instrumented_client, mock_create_initial_message_without_search
    ):
        """Test answer_question handles OpenAI API errors gracefully."""
        # Setup mocks
        mock_client = Mock()
        mock_chat = Mock()
        mock_completions = Mock()
        mock_create = Mock()

        mock_client.chat = mock_chat
        mock_chat.completions = mock_completions
        mock_completions.create = mock_create

        mock_instrumented_client = Mock()
        mock_instrumented_client._client = mock_client
        mock_get_instrumented_client.return_value = mock_instrumented_client

        mock_create_initial_message_without_search.return_value = "Test message"

        # Mock OpenAI error
        mock_create.side_effect = Exception("OpenAI API Error")

        # Mock index and vectorizer
        mock_index = AsyncMock()
        mock_vectorizer = Mock()

        # Execute and verify error is raised
        with pytest.raises(Exception, match="OpenAI API Error"):
            await answer_question(
                mock_index, mock_vectorizer, "test query", "test_session", "test_user"
            )

    @pytest.mark.asyncio
    @patch("app.agent.create_initial_message_without_search")
    @patch("app.agent.core.get_instrumented_client")
    async def test_answer_question_with_different_queries(
        self, mock_get_instrumented_client, mock_create_initial_message_without_search
    ):
        """Test answer_question with different types of queries."""
        # Setup mocks
        mock_client = Mock()
        mock_chat = Mock()
        mock_completions = Mock()
        mock_create = Mock()

        mock_client.chat = mock_chat
        mock_chat.completions = mock_completions
        mock_completions.create = mock_create

        mock_instrumented_client = Mock()
        mock_instrumented_client._client = mock_client
        mock_get_instrumented_client.return_value = mock_instrumented_client

        mock_create_initial_message_without_search.return_value = "Test message"

        # Mock response
        mock_response = Mock()
        mock_message = Mock()
        mock_message.content = "Here's information about Redis AI capabilities."
        mock_message.tool_calls = None
        mock_message.model_dump.return_value = {
            "role": "assistant",
            "content": "Here's information about Redis AI capabilities.",
        }
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = mock_message
        # Add usage attribute for metrics tracking
        mock_usage = Mock()
        mock_usage.total_tokens = 200
        mock_response.usage = mock_usage
        mock_create.return_value = mock_response

        # Mock index and vectorizer
        mock_index = AsyncMock()
        mock_vectorizer = Mock()

        # Test different queries
        queries = [
            "What is Redis?",
            "How does vector search work?",
            "Tell me about AI capabilities",
        ]

        for query in queries:
            result = await answer_question(
                mock_index, mock_vectorizer, query, "test_session", "test_user"
            )
            assert result == "Here's information about Redis AI capabilities."

        # Verify OpenAI was called for each query (at least once per query)
        assert mock_create.call_count >= len(queries)


class TestRAGIntegration:
    """Integration tests for the RAG pipeline."""

    @pytest.mark.asyncio
    @patch("app.agent.create_initial_message_without_search")
    @patch("app.agent.core.get_instrumented_client")
    async def test_full_rag_pipeline_simplified(
        self, mock_get_instrumented_client, mock_create_initial_message_without_search
    ):
        """Test the full RAG pipeline with mocked components."""
        # Setup mocks
        mock_client = Mock()
        mock_chat = Mock()
        mock_completions = Mock()
        mock_create = Mock()

        mock_client.chat = mock_chat
        mock_chat.completions = mock_completions
        mock_completions.create = mock_create

        mock_instrumented_client = Mock()
        mock_instrumented_client._client = mock_client
        mock_get_instrumented_client.return_value = mock_instrumented_client

        mock_create_initial_message_without_search.return_value = "Test message"

        # Mock response
        mock_response = Mock()
        mock_message = Mock()
        mock_message.content = "Redis offers vector database capabilities for AI."
        mock_message.tool_calls = None
        mock_message.model_dump.return_value = {
            "role": "assistant",
            "content": "Redis offers vector database capabilities for AI.",
        }
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = mock_message
        # Add usage attribute for metrics tracking
        mock_usage = Mock()
        mock_usage.total_tokens = 180
        mock_response.usage = mock_usage
        mock_create.return_value = mock_response

        # Mock index and vectorizer
        mock_index = AsyncMock()
        mock_vectorizer = Mock()

        # Execute
        result = await answer_question(
            mock_index, mock_vectorizer, "What is Redis?", "test_session", "test_user"
        )

        # Verify
        assert result == "Redis offers vector database capabilities for AI."
        assert mock_create.call_count >= 1

    @pytest.mark.asyncio
    @patch("app.agent.create_initial_message_without_search")
    @patch("app.agent.core.get_instrumented_client")
    async def test_rag_system_prompt_content(
        self, mock_get_instrumented_client, mock_create_initial_message_without_search
    ):
        """Test that the system prompt contains expected content."""
        # Setup mocks
        mock_client = Mock()
        mock_chat = Mock()
        mock_completions = Mock()
        mock_create = Mock()

        mock_client.chat = mock_chat
        mock_chat.completions = mock_completions
        mock_completions.create = mock_create

        mock_instrumented_client = Mock()
        mock_instrumented_client._client = mock_client
        mock_get_instrumented_client.return_value = mock_instrumented_client

        mock_create_initial_message_without_search.return_value = "Test message"

        # Mock response
        mock_response = Mock()
        mock_message = Mock()
        mock_message.content = "Test response"
        mock_message.tool_calls = None
        mock_message.model_dump.return_value = {
            "role": "assistant",
            "content": "Test response",
        }
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = mock_message
        # Add usage attribute for metrics tracking
        mock_usage = Mock()
        mock_usage.total_tokens = 120
        mock_response.usage = mock_usage
        mock_create.return_value = mock_response

        # Mock index and vectorizer
        mock_index = AsyncMock()
        mock_vectorizer = Mock()

        # Execute
        await answer_question(
            mock_index, mock_vectorizer, "test query", "test_session", "test_user"
        )

        # Verify OpenAI was called
        assert mock_create.call_count >= 1

        # Verify system prompt was used - use the first call
        call_args = mock_create.call_args_list[0]
        messages = call_args[1]["messages"]
        system_msg = next(msg for msg in messages if msg["role"] == "system")
        assert "Applied AI team at Redis" in system_msg["content"]
        assert "Vector database" in system_msg["content"]
        assert "Available Tools" in system_msg["content"]
