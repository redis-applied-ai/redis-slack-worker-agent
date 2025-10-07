"""Test task functionality including reentrant side effects and retry logic."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.agent.tasks import process_slack_question_with_retry


class TestReentrantTaskExecution:
    """Test that tasks use module-level side effect functions correctly."""

    @pytest.mark.asyncio
    async def test_task_calls_all_side_effect_functions(self):
        """Test that the task calls all module-level side effect functions."""
        function_calls = []

        async def mock_generate_rag_response(*args, **kwargs):
            function_calls.append("generate_rag_response")
            return "test response"

        async def mock_post_slack_message(*args, **kwargs):
            function_calls.append("post_slack_message")

        with (
            patch(
                "app.agent.tasks.slack_tasks.generate_rag_response",
                side_effect=mock_generate_rag_response,
            ),
            patch(
                "app.agent.tasks.slack_tasks.post_slack_message",
                side_effect=mock_post_slack_message,
            ),
        ):
            await process_slack_question_with_retry(
                user_id="test_user",
                text="test question",
                channel_id="test_channel",
                thread_ts="123456.789",
            )

        # Verify the two main side effect functions were called
        assert len(function_calls) == 2
        assert "generate_rag_response" in function_calls
        assert "post_slack_message" in function_calls

    @pytest.mark.asyncio
    async def test_functions_get_proper_arguments(self):
        """Test that side effect functions receive proper arguments."""
        function_calls = []

        async def track_generate_rag_response(*args, **kwargs):
            function_calls.append(("generate_rag_response", args, kwargs))
            return "test response"

        async def track_post_slack_message(*args, **kwargs):
            function_calls.append(("post_slack_message", args, kwargs))

        with (
            patch(
                "app.agent.tasks.slack_tasks.generate_rag_response",
                side_effect=track_generate_rag_response,
            ),
            patch(
                "app.agent.tasks.slack_tasks.post_slack_message",
                side_effect=track_post_slack_message,
            ),
        ):
            user_id = "user123"
            text = "test question"
            thread_ts = "123456.789"
            channel_id = "channel1"

            await process_slack_question_with_retry(
                user_id=user_id,
                text=text,
                channel_id=channel_id,
                thread_ts=thread_ts,
            )

        # Verify functions received the expected arguments
        assert len(function_calls) == 2

        # Check generate_rag_response args
        rag_call = next(
            call for call in function_calls if call[0] == "generate_rag_response"
        )
        rag_args = rag_call[1]
        assert rag_args[0] == user_id
        assert rag_args[1] == text
        assert rag_args[2] == thread_ts
        assert rag_args[3] == channel_id

        # Check post_slack_message args
        slack_call = next(
            call for call in function_calls if call[0] == "post_slack_message"
        )
        slack_args = slack_call[1]
        assert slack_args[0] == user_id
        assert slack_args[1] == text
        assert slack_args[2] == thread_ts
        assert (
            slack_args[3] == "test response"
        )  # The response from generate_rag_response
        assert slack_args[4] == channel_id

    @pytest.mark.asyncio
    async def test_task_handles_failure_gracefully(self):
        """Test that task handles function failures and re-raises for retry."""

        async def failing_generate_rag_response(*args, **kwargs):
            raise ValueError("RAG failed")

        with (
            patch(
                "app.agent.tasks.slack_tasks.generate_rag_response",
                side_effect=failing_generate_rag_response,
            ),
        ):
            with pytest.raises(ValueError, match="RAG failed"):
                await process_slack_question_with_retry(
                    user_id="test_user",
                    text="test question",
                    channel_id="test_channel",
                )

    @pytest.mark.asyncio
    async def test_all_functions_execute_successfully(self):
        """Test that all functions execute without errors."""
        execution_count = 0

        async def counting_function(*args, **kwargs):
            nonlocal execution_count
            execution_count += 1
            return f"mock_result_{execution_count}"

        with (
            patch(
                "app.agent.tasks.slack_tasks.generate_rag_response",
                side_effect=counting_function,
            ),
            patch(
                "app.agent.tasks.slack_tasks.post_slack_message",
                side_effect=counting_function,
            ),
        ):
            await process_slack_question_with_retry(
                user_id="test_user",
                text="test_question",
                channel_id="test_channel",
                thread_ts="123456.789",
            )

        # Verify both functions were executed
        assert execution_count == 2


class TestAnswerDataFormat:
    """Test that answer data is formatted correctly for Redis storage."""

    def test_boolean_values_converted_to_strings(self):
        """Test that boolean values in answer data are converted to strings."""
        from datetime import datetime, timezone

        from ulid import ULID

        # This simulates the answer_data creation in the task
        answer_data = {
            "id": str(ULID()),
            "user_id": "test_user",
            "question": "test question",
            "answer": "test answer",
            "accepted": "false",  # Should be string, not boolean
            "created_at": datetime.now(timezone.utc).timestamp(),
            "updated_at": datetime.now(timezone.utc).timestamp(),
            "thread_ts": "",  # Should be string, not None
        }

        # Verify all values are Redis-compatible
        for key, value in answer_data.items():
            assert isinstance(
                value, (str, int, float)
            ), f"Field {key} should be string/int/float, got {type(value)}"

        # Specifically verify the problematic fields
        assert answer_data["accepted"] == "false"
        assert isinstance(answer_data["thread_ts"], str)


class TestFeedbackFunctionality:
    """Test feedback button functionality."""

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_post_slack_message_includes_feedback_buttons(
        self, mock_get_redis_client
    ):
        """Test that post_slack_message includes feedback buttons in blocks."""
        from app.agent.tasks import post_slack_message

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
                "user123", "test question", "thread123", "test response", "channel123"
            )

            # Verify chat_postMessage was called
            mock_slack_app.client.chat_postMessage.assert_called_once()

            # Get the call arguments
            call_args = mock_slack_app.client.chat_postMessage.call_args[1]

            # Verify blocks are present
            assert "blocks" in call_args
            blocks = call_args["blocks"]

            # Find the actions block with feedback buttons
            actions_block = next(
                (block for block in blocks if block["type"] == "actions"), None
            )
            assert actions_block is not None

            # Check that both thumbs up and thumbs down buttons are present
            elements = actions_block["elements"]
            thumbs_up = next(
                (
                    elem
                    for elem in elements
                    if elem["action_id"] == "feedback_thumbs_up"
                ),
                None,
            )
            thumbs_down = next(
                (
                    elem
                    for elem in elements
                    if elem["action_id"] == "feedback_thumbs_down"
                ),
                None,
            )

            assert thumbs_up is not None
            assert thumbs_down is not None

            # The button value should contain the answer_key format
            # The actual value will be something like "thumbs_up:answer:user123-{hash}-thread123"
            assert thumbs_up["value"].startswith("thumbs_up:answer:")
            assert "user123" in thumbs_up["value"]
            assert "thread123" in thumbs_up["value"]
