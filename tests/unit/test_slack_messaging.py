"""Tests for Slack messaging functionality related to issue #25."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.agent import SYSTEM_PROMPT
from app.agent.tasks import (
    generate_rag_response,
    post_error_message,
    post_slack_message,
)


class TestSlackMessaging:
    """Test Slack messaging block type and character limit fixes."""

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_post_slack_message_uses_markdown_block(self, mock_get_redis_client):
        """Test that post_slack_message uses markdown block type."""
        # Mock Redis for side effects
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis
        mock_redis.get.return_value = None  # Side effect not completed
        mock_redis.set = AsyncMock()

        with patch("app.agent.tasks.slack_tasks.get_slack_app") as mock_get_slack_app:
            mock_slack_app = Mock()
            mock_slack_app.client.chat_postMessage = AsyncMock()
            mock_get_slack_app.return_value = mock_slack_app

            await post_slack_message(
                "user123", "question", "thread123", "response", "channel123"
            )

            # Check that chat_postMessage was called with markdown block
            mock_slack_app.client.chat_postMessage.assert_called_once()
            call_args = mock_slack_app.client.chat_postMessage.call_args[1]

            assert call_args["blocks"][0]["type"] == "markdown"
            assert call_args["blocks"][0]["text"] == "response"

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_post_error_message_uses_markdown_block(self, mock_get_redis_client):
        """Test that post_error_message uses markdown block type."""
        # Mock Redis for side effects
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis
        mock_redis.get.return_value = None  # Side effect not completed
        mock_redis.set = AsyncMock()

        with patch("app.agent.tasks.slack_tasks.get_slack_app") as mock_get_slack_app:
            mock_slack_app = Mock()
            mock_slack_app.client.chat_postMessage = AsyncMock()
            mock_get_slack_app.return_value = mock_slack_app

            await post_error_message(
                "user123", "question", "thread123", "error", "channel123", 3
            )

            # Check that chat_postMessage was called with markdown block
            mock_slack_app.client.chat_postMessage.assert_called_once()
            call_args = mock_slack_app.client.chat_postMessage.call_args[1]

            assert call_args["blocks"][0]["type"] == "markdown"

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_post_slack_message_truncates_long_messages(
        self, mock_get_redis_client
    ):
        """Test that post_slack_message truncates messages over 12,000 characters."""
        # Mock Redis for side effects
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis
        mock_redis.get.return_value = None  # Side effect not completed
        mock_redis.set = AsyncMock()

        with patch("app.agent.tasks.slack_tasks.get_slack_app") as mock_get_slack_app:
            mock_slack_app = Mock()
            mock_slack_app.client.chat_postMessage = AsyncMock()
            mock_get_slack_app.return_value = mock_slack_app

            # Create a message over 12,000 characters
            long_response = "A" * 13000

            await post_slack_message(
                "user123", "question", "thread123", long_response, "channel123"
            )

            # Check that the message was truncated
            mock_slack_app.client.chat_postMessage.assert_called_once()
            call_args = mock_slack_app.client.chat_postMessage.call_args[1]

            sent_text = call_args["blocks"][0]["text"]
            assert len(sent_text) <= 12000
            assert sent_text.endswith("...(Message too long)")

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_post_error_message_truncates_long_messages(
        self, mock_get_redis_client
    ):
        """Test that post_error_message truncates messages over 12,000 characters."""
        # Mock Redis for side effects
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis
        mock_redis.get.return_value = None  # Side effect not completed
        mock_redis.set = AsyncMock()

        with patch("app.agent.tasks.slack_tasks.get_slack_app") as mock_get_slack_app:
            mock_slack_app = Mock()
            mock_slack_app.client.chat_postMessage = AsyncMock()
            mock_get_slack_app.return_value = mock_slack_app

            # Create a long error message
            long_error = "E" * 13000

            await post_error_message(
                "user123", "question", "thread123", long_error, "channel123", 3
            )

            # Check that the message was truncated
            mock_slack_app.client.chat_postMessage.assert_called_once()
            call_args = mock_slack_app.client.chat_postMessage.call_args[1]

            sent_text = call_args["blocks"][0]["text"]
            assert len(sent_text) <= 12000
            assert sent_text.endswith("...(Message too long)")

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_post_slack_message_doesnt_truncate_short_messages(
        self, mock_get_redis_client
    ):
        """Test that post_slack_message doesn't truncate messages under 12,000 characters."""
        # Mock Redis for side effects
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis
        mock_redis.get.return_value = None  # Side effect not completed
        mock_redis.set = AsyncMock()

        with patch("app.agent.tasks.slack_tasks.get_slack_app") as mock_get_slack_app:
            mock_slack_app = Mock()
            mock_slack_app.client.chat_postMessage = AsyncMock()
            mock_get_slack_app.return_value = mock_slack_app

            short_response = "This is a short response"

            await post_slack_message(
                "user123", "question", "thread123", short_response, "channel123"
            )

            # Check that the message was NOT truncated
            mock_slack_app.client.chat_postMessage.assert_called_once()
            call_args = mock_slack_app.client.chat_postMessage.call_args[1]

            sent_text = call_args["blocks"][0]["text"]
            assert sent_text == short_response
            assert not sent_text.endswith("...(Message too long)")

    def test_system_prompt_contains_character_limit_guidance(self):
        """Test that SYSTEM_PROMPT includes character limit guidance."""
        assert "12,000 characters" in SYSTEM_PROMPT
        assert "character limit" in SYSTEM_PROMPT.lower()
        assert "keep all responses under" in SYSTEM_PROMPT.lower()

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_generate_rag_response_uses_markdown_block(
        self, mock_get_redis_client
    ):
        """Test that generate_rag_response progress callback uses markdown block type."""
        # Mock Redis for side effects
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis
        mock_redis.get.return_value = None  # Side effect not completed
        mock_redis.set = AsyncMock()

        with (
            patch("app.agent.tasks.slack_tasks.get_slack_app") as mock_get_slack_app,
            patch("app.utilities.database.get_document_index") as mock_get_doc_index,
            patch("app.utilities.database.get_vectorizer") as mock_get_vectorizer,
            patch(
                "app.agent.tasks.slack_tasks.answer_question"
            ) as mock_answer_question,
            patch(
                "app.agent.tasks.slack_tasks.get_thread_context"
            ) as mock_get_thread_context,
        ):
            mock_slack_app = Mock()
            mock_slack_app.client.chat_postMessage = AsyncMock()
            mock_get_slack_app.return_value = mock_slack_app

            mock_get_doc_index.return_value = Mock()
            mock_get_vectorizer.return_value = Mock()
            mock_answer_question.return_value = "test response"
            mock_get_thread_context.return_value = []

            await generate_rag_response(
                "user123", "test question", "thread123", "channel123"
            )

            # Check that the progress callback used markdown block
            mock_slack_app.client.chat_postMessage.assert_called()
            call_args = mock_slack_app.client.chat_postMessage.call_args[1]

            assert call_args["blocks"][0]["type"] == "markdown"
            assert "_Thinking..._" in call_args["blocks"][0]["text"]
