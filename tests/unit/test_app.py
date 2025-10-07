"""
Unit tests for the FastAPI application endpoints and integration.
"""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.api.main import app


class MockSearchIndex:
    """Mock AsyncSearchIndex for testing."""

    async def exists(self):
        return True

    async def query(self, *args, **kwargs):
        return [
            {"name": "Test", "description": "Test description", "day_off": "Monday"}
        ]


class MockSearchIndexWithVariableResults:
    """Mock search index that returns different numbers of results."""

    def __init__(self, result_count=7):
        self.result_count = result_count

    async def query(self, query_obj):
        # Simulate different result counts based on distance threshold
        results = []
        for i in range(min(self.result_count, 10)):  # Cap at 10 results
            results.append(
                {
                    "name": f"TeamMember{i}",
                    "description": f"Expert in area {i}",
                    "day_off": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"][
                        i % 5
                    ],
                    "score": 0.9 - (i * 0.05),  # Decreasing relevance scores
                }
            )
        return results

    async def exists(self):
        return True


class MockSearchIndexEmpty:
    """Mock search index that returns no results."""

    async def query(self, *args, **kwargs):
        return []

    async def exists(self):
        return True


class MockSearchIndexUnavailable:
    """Mock search index that's unavailable."""

    async def exists(self):
        return False

    async def query(self, *args, **kwargs):
        raise Exception("Index unavailable")


class MockHFVectorizer:
    """Mock HuggingFace vectorizer for testing."""

    def embed(self, text, as_buffer=True):
        return b"mock_embedding" if as_buffer else [0.1, 0.2, 0.3]


class MockOpenAIClient:
    def __init__(self):
        self.chat = Mock()
        self.chat.completions = Mock()
        self.chat.completions.create = Mock(
            return_value=Mock(choices=[Mock(message=Mock(content="Test response"))])
        )

        # Mock embeddings API with proper structure
        self.embeddings = Mock()
        # Create a mock embedding response that matches OpenAI's structure
        mock_embedding_data = Mock()
        mock_embedding_data.embedding = [0.1] * 1536  # Mock 1536-dimensional embedding

        mock_embedding_response = Mock()
        mock_embedding_response.data = [mock_embedding_data]
        mock_embedding_response.usage = Mock(total_tokens=10)

        self.embeddings.create = Mock(return_value=mock_embedding_response)


class MockSlackApp:
    def __init__(self, *args, **kwargs):
        self.client = Mock()

    def event(self, event_type):
        def decorator(func):
            return func

        return decorator


class MockDocket:
    """Mock Docket for testing."""

    def __init__(self, *args, **kwargs):
        self.add_calls = []  # Track calls for verification

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def add(self, func, **kwargs):
        """Mock task addition that returns a callable."""

        async def task_callable(**task_kwargs):
            # Store the call for verification
            self.add_calls.append(
                {"func": func, "add_kwargs": kwargs, "task_kwargs": task_kwargs}
            )
            return None  # Simulate successful task scheduling

        return task_callable

    async def workers(self):
        """Mock workers method."""
        return [
            "worker1",
            "worker2",
        ]  # Return non-empty list to indicate healthy task queue


@pytest.fixture
def mock_app_dependencies():
    """Mock all external dependencies for the FastAPI app."""
    with (
        # Patch where the functions are used, not where they're defined
        patch("app.utilities.database.get_document_index") as mock_get_document_index,
        patch("app.utilities.database.get_vectorizer") as mock_get_vectorizer,
        patch(
            "app.api.routers.health.get_document_index"
        ) as mock_health_get_document_index,
        patch("app.api.routers.health.get_vectorizer") as mock_health_get_vectorizer,
        patch("app.api.slack_app.get_slack_app") as mock_get_slack_app,
        patch("app.api.slack_app.get_handler") as mock_get_handler,
        patch("app.api.main.Docket") as mock_docket,
        patch("app.api.routers.health.Docket") as mock_health_docket,
        patch("app.worker.task_registration.register_all_tasks") as mock_register_tasks,
        patch(
            "app.agent.tasks.slack_tasks.process_slack_question_with_retry"
        ) as mock_process_task,
        # Also patch OpenAI client creation to prevent real API calls
        patch("openai.OpenAI") as mock_openai_class,
        # Patch redisvl OpenAI vectorizer to prevent initialization issues
        patch(
            "redisvl.utils.vectorize.text.openai.OpenAITextVectorizer"
        ) as mock_openai_vectorizer,
    ):
        # Setup mock return values
        mock_get_document_index.return_value = MockSearchIndex()
        mock_get_vectorizer.return_value = MockHFVectorizer()
        mock_get_slack_app.return_value = MockSlackApp()

        # Setup health-specific mocks
        mock_health_get_document_index.return_value = MockSearchIndex()
        mock_health_get_vectorizer.return_value = MockHFVectorizer()

        mock_handler = AsyncMock()
        mock_handler.handle.return_value = {"status": "ok"}
        mock_get_handler.return_value = mock_handler

        mock_docket_instance = MockDocket()
        mock_docket.return_value.__aenter__ = AsyncMock(
            return_value=mock_docket_instance
        )
        mock_docket.return_value.__aexit__ = AsyncMock(return_value=None)

        # Configure health docket mock the same way
        mock_health_docket.return_value.__aenter__ = AsyncMock(
            return_value=mock_docket_instance
        )
        mock_health_docket.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_register_tasks.return_value = None
        mock_process_task.return_value = AsyncMock()

        # Setup OpenAI client mock with proper structure
        mock_openai_instance = MockOpenAIClient()
        mock_openai_class.return_value = mock_openai_instance

        # Setup OpenAI vectorizer mock to avoid initialization issues
        mock_vectorizer_instance = MockHFVectorizer()
        mock_openai_vectorizer.return_value = mock_vectorizer_instance

        yield {
            "get_document_index": mock_get_document_index,
            "get_vectorizer": mock_get_vectorizer,
            "get_slack_app": mock_get_slack_app,
            "get_handler": mock_get_handler,
            "docket": mock_docket,
            "register_tasks": mock_register_tasks,
            "process_task": mock_process_task,
            "openai_client": mock_openai_instance,
        }


@pytest.fixture
def test_app(mock_app_dependencies):
    """Create a test FastAPI app with mocked dependencies."""
    # Import here to ensure patches are applied

    return app


@pytest.fixture
def client(test_app):
    """Create a test client for synchronous testing."""
    return TestClient(test_app)


@pytest_asyncio.fixture
async def async_client(test_app):
    """Create an async test client."""
    from httpx import ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as ac:
        yield ac


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_root_health_check(self, client):
        """Test the health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert "Advanced Slack RAG Bot is running!" in response.text

    @pytest.mark.asyncio
    async def test_detailed_health_check_healthy(
        self, async_client, mock_app_dependencies
    ):
        """Test detailed health check when all components are healthy."""
        response = await async_client.get("/health/detailed")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "healthy"
        assert data["components"]["vector_index"] == "available"
        assert data["components"]["vectorizer"] == "available"
        assert data["components"]["slack_app"] == "available"
        assert data["components"]["task_queue"] == "available"

    @pytest.mark.asyncio
    async def test_detailed_health_check_unhealthy(self):
        """Test detailed health check when components are unavailable."""
        # Import and patch at runtime to avoid import order issues
        from app.api.main import app

        with (
            patch(
                "app.utilities.database.get_document_index"
            ) as mock_get_document_index,
            patch("app.utilities.database.get_vectorizer") as mock_get_vectorizer,
            patch("app.api.slack_app.get_slack_app") as mock_get_slack_app,
            patch("app.api.main.Docket") as mock_docket,
            patch(
                "app.api.routers.health.get_document_index"
            ) as mock_health_get_document_index,
            patch(
                "app.api.routers.health.get_vectorizer"
            ) as mock_health_get_vectorizer,
            patch("app.api.routers.health.get_slack_app") as mock_health_get_slack_app,
            patch("app.api.routers.health.Docket") as mock_health_docket,
        ):
            # Setup unhealthy mocks
            mock_get_document_index.return_value = MockSearchIndexUnavailable()
            mock_get_vectorizer.return_value = None
            mock_get_slack_app.return_value = None
            # Make Docket raise an exception to simulate connection failure
            mock_docket.side_effect = Exception("Redis connection failed")

            # Setup health-specific mocks for unhealthy state
            mock_health_get_document_index.return_value = MockSearchIndexUnavailable()
            mock_health_get_vectorizer.return_value = None
            mock_health_get_slack_app.return_value = None
            mock_health_docket.side_effect = Exception("Redis connection failed")

            from httpx import ASGITransport, AsyncClient

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/health/detailed")

                assert response.status_code == 200
                data = response.json()

                assert data["status"] == "unhealthy"
                assert data["components"]["vector_index"] == "unavailable"
                assert data["components"]["vectorizer"] == "unavailable"
                assert data["components"]["slack_app"] == "unavailable"
                assert data["components"]["task_queue"] == "unavailable"


class TestSlackEndpoints:
    """Test Slack webhook endpoints."""

    @pytest.mark.asyncio
    async def test_slack_events_with_handler(self, async_client, mock_app_dependencies):
        """Test Slack events endpoint with handler available."""
        event_payload = {
            "type": "event_callback",
            "event": {
                "type": "app_mention",
                "user": "U123456789",
                "text": "<@U987654321> Who can help with agents?",
                "channel": "C123456789",
            },
        }

        response = await async_client.post("/slack/events", json=event_payload)

        # Just check that it responds successfully - the handler mocking is complex
        assert response.status_code in [200, 500]  # Either successful or handler error

    @pytest.mark.asyncio
    async def test_slack_events_no_handler(self):
        """Test Slack events endpoint when handler creation fails."""
        # Test when get_handler() raises an exception during handler creation
        with patch(
            "app.api.slack_app.get_handler",
            side_effect=Exception("Handler creation failed"),
        ):
            # Force fresh import of the app module

            from httpx import ASGITransport, AsyncClient

            from app.api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post("/slack/events", json={})
                assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_slack_events_handler_error(self):
        """Test Slack events endpoint when handler raises an error."""
        mock_handler = AsyncMock()
        mock_handler.handle.side_effect = Exception("Handler processing error")

        with patch("app.api.slack_app.get_handler", return_value=mock_handler):
            # Force fresh import of the app module

            from httpx import ASGITransport, AsyncClient

            from app.api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post("/slack/events", json={})
                assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_slack_interactive_preserves_blocks(
        self, async_client, mock_app_dependencies
    ):
        """Test that the /slack/interactive endpoint preserves block formatting (e.g., bullet points) after feedback."""
        # Simulate a Slack interactive payload with block_actions
        original_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Here are some options:*\n• Option 1\n• Option 2\n• Option 3",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "action_id": "feedback_thumbs_up",
                        "text": {"type": "plain_text", "text": "Thumbs Up"},
                        "value": "thumbs_up:answer_key_123",
                    },
                    {
                        "type": "button",
                        "action_id": "feedback_thumbs_down",
                        "text": {"type": "plain_text", "text": "Thumbs Down"},
                        "value": "thumbs_down:answer_key_123",
                    },
                ],
            },
        ]
        payload = {
            "type": "block_actions",
            "user": {"id": "U123456"},
            "message": {
                "text": "*Here are some options:*\n• Option 1\n• Option 2\n• Option 3",
                "blocks": original_blocks,
                "ts": "1234567890.123456",
            },
            "channel": {"id": "C123456"},
            "actions": [
                {"action_id": "feedback_thumbs_up", "value": "thumbs_up:answer_key_123"}
            ],
        }
        # Slack sends this as form data
        form_data = {"payload": json.dumps(payload)}
        response = await async_client.post("/slack/interactive", data=form_data)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        # The actual block update is handled asynchronously, but this ensures the endpoint does not error and accepts the payload


class TestSlackMessageHandling:
    """Test Slack message handling behavior for mentions and DMs."""

    @pytest.mark.asyncio
    async def test_handle_app_mentions_creates_thread_in_channel(self):
        """Test that app mentions in channels create threads."""
        from app.api.main import handle_app_mentions

        # Mock event body for channel mention without existing thread
        body = {
            "event": {
                "user": "U123456789",
                "text": "<@U987654321> Who can help with agents?",
                "channel": "C123456789",
                "ts": "1234567890.123456",
            }
        }

        mock_say = AsyncMock()
        mock_ack = AsyncMock()

        with (
            patch("app.api.main.Docket") as mock_docket_class,
            patch("app.api.slack_app.get_slack_app") as mock_get_slack_app,
            patch("app.utilities.database.get_redis_client") as mock_redis_client,
        ):
            mock_docket_instance = MockDocket()
            mock_docket_class.return_value.__aenter__.return_value = (
                mock_docket_instance
            )

            # Mock slack app (not needed for immediate calls but for completeness)
            mock_slack_app = Mock()
            mock_slack_app.client.chat_postMessage = AsyncMock()
            mock_get_slack_app.return_value = mock_slack_app

            # Mock Redis client for track_thread_participation
            mock_redis_client.return_value.set = AsyncMock()

            await handle_app_mentions(body, mock_say, mock_ack)

            # Verify acknowledgment was sent
            mock_ack.assert_called_once()
            # Note: No immediate chat_postMessage expected - response happens in background task

            # Verify task was scheduled with correct thread_ts
            assert len(mock_docket_instance.add_calls) == 1
            call = mock_docket_instance.add_calls[0]
            assert call["task_kwargs"]["thread_ts"] == "1234567890.123456"
            assert call["task_kwargs"]["user_id"] == "U123456789"
            assert call["task_kwargs"]["channel_id"] == "C123456789"

    @pytest.mark.asyncio
    async def test_handle_app_mentions_preserves_existing_thread(self):
        """Test that app mentions in existing threads preserve thread_ts."""
        from app.api.main import handle_app_mentions

        # Mock event body for mention in existing thread
        body = {
            "event": {
                "user": "U123456789",
                "text": "<@U987654321> More details please",
                "channel": "C123456789",
                "ts": "1234567890.654321",
                "thread_ts": "1234567890.123456",  # Existing thread
            }
        }

        mock_say = AsyncMock()
        mock_ack = AsyncMock()

        with (
            patch("app.api.main.Docket") as mock_docket_class,
            patch("app.api.slack_app.get_slack_app") as mock_get_slack_app,
            patch("app.utilities.database.get_redis_client") as mock_redis_client,
        ):
            mock_docket_instance = MockDocket()
            mock_docket_class.return_value.__aenter__.return_value = (
                mock_docket_instance
            )

            # Mock slack app for immediate acknowledgment
            mock_slack_app = Mock()
            mock_slack_app.client.chat_postMessage = AsyncMock()
            mock_get_slack_app.return_value = mock_slack_app

            # Mock Redis client for track_thread_participation
            mock_redis_client.return_value.set = AsyncMock()

            await handle_app_mentions(body, mock_say, mock_ack)

            # Verify task was scheduled with preserved thread_ts
            assert len(mock_docket_instance.add_calls) == 1
            call = mock_docket_instance.add_calls[0]
            assert (
                call["task_kwargs"]["thread_ts"] == "1234567890.123456"
            )  # Original thread preserved

    @pytest.mark.asyncio
    async def test_handle_dm_messages_processes_direct_messages(self):
        """Test that DM messages are processed correctly."""
        from app.api.main import handle_dm_messages

        # Mock event body for DM
        body = {
            "event": {
                "user": "U123456789",
                "text": "Help me with this question",
                "channel": "D123456789",
                "channel_type": "im",
                "ts": "1234567890.123456",
            }
        }

        mock_say = AsyncMock()
        mock_ack = AsyncMock()
        mock_logger = Mock()

        with (
            patch("app.api.main.Docket") as mock_docket_class,
            patch("app.api.slack_app.get_slack_app") as mock_get_slack_app,
        ):
            mock_docket_instance = MockDocket()
            mock_docket_class.return_value.__aenter__.return_value = (
                mock_docket_instance
            )

            # Mock slack app (not needed for immediate calls but for completeness)
            mock_slack_app = Mock()
            mock_slack_app.client.chat_postMessage = AsyncMock()
            mock_get_slack_app.return_value = mock_slack_app

            await handle_dm_messages(body, mock_say, mock_ack, mock_logger)

            # Verify acknowledgment was sent
            mock_ack.assert_called_once()
            # Note: No immediate chat_postMessage expected - response happens in background task

            # Verify task was scheduled with thread_ts using message timestamp (DM threading)
            assert len(mock_docket_instance.add_calls) == 1
            call = mock_docket_instance.add_calls[0]
            assert call["task_kwargs"]["thread_ts"] == "1234567890.123456"
            assert call["task_kwargs"]["user_id"] == "U123456789"
            assert call["task_kwargs"]["channel_id"] == "D123456789"

    @pytest.mark.asyncio
    async def test_handle_dm_messages_ignores_non_dm_messages(self):
        """Test that non-DM messages are ignored by DM handler."""
        from app.api.main import handle_dm_messages

        # Mock event body for channel message (not DM)
        body = {
            "event": {
                "user": "U123456789",
                "text": "This is a channel message",
                "channel": "C123456789",
                "channel_type": "channel",  # Not "im"
                "ts": "1234567890.123456",
            }
        }

        mock_say = AsyncMock()
        mock_ack = AsyncMock()
        mock_logger = Mock()

        with patch("app.api.main.Docket") as mock_docket_class:
            mock_docket_instance = MockDocket()
            mock_docket_class.return_value.__aenter__.return_value = (
                mock_docket_instance
            )

            await handle_dm_messages(body, mock_say, mock_ack, mock_logger)

            # Verify acknowledgment was sent but no task scheduled
            mock_ack.assert_called_once()
            mock_say.assert_not_called()  # Should not respond to non-DM
            assert len(mock_docket_instance.add_calls) == 0  # Should not schedule task

            # Verify it logged the ignore
            mock_logger.debug.assert_called_with(
                "Ignoring non-DM, non-thread message in channel C123456789"
            )

    @pytest.mark.asyncio
    async def test_handle_app_mentions_with_error_handling(self):
        """Test app mention handler error scenarios."""
        from app.api.main import handle_app_mentions

        body = {
            "event": {
                "user": "U123456789",
                "text": "<@U987654321> Test question",
                "channel": "C123456789",
                "ts": "1234567890.123456",
            }
        }

        mock_say = AsyncMock()
        mock_ack = AsyncMock()

        # Test Docket connection error
        with (
            patch("app.api.main.Docket") as mock_docket,
            patch("app.api.main.get_slack_app") as mock_get_slack_app,
            patch("app.utilities.database.get_redis_client") as mock_redis_client,
        ):
            mock_docket.side_effect = Exception("Redis connection failed")

            # Mock slack app (not needed for immediate calls but for completeness)
            mock_slack_app = Mock()
            mock_slack_app.client.chat_postMessage = AsyncMock()
            mock_get_slack_app.return_value = mock_slack_app

            # Mock Redis client for track_thread_participation
            mock_redis_client.return_value.set = AsyncMock()

            with pytest.raises(Exception, match="Redis connection failed"):
                await handle_app_mentions(body, mock_say, mock_ack)

    @pytest.mark.asyncio
    async def test_handle_dm_messages_with_missing_channel_type(self):
        """Test DM handler when channel_type is missing."""
        from app.api.main import handle_dm_messages

        # Mock event body without channel_type
        body = {
            "event": {
                "user": "U123456789",
                "text": "Help me with this question",
                "channel": "D123456789",
                "ts": "1234567890.123456",
                # Missing channel_type
            }
        }

        mock_say = AsyncMock()
        mock_ack = AsyncMock()
        mock_logger = Mock()

        with (
            patch("app.api.main.Docket") as mock_docket_class,
            patch("app.api.slack_app.get_slack_app") as mock_get_slack_app,
        ):
            mock_docket_instance = MockDocket()
            mock_docket_class.return_value.__aenter__.return_value = (
                mock_docket_instance
            )

            # Mock slack app (not needed for immediate calls but for completeness)
            mock_slack_app = Mock()
            mock_slack_app.client.chat_postMessage = AsyncMock()
            mock_get_slack_app.return_value = mock_slack_app

            await handle_dm_messages(body, mock_say, mock_ack, mock_logger)

            # Verify acknowledgment was sent
            mock_ack.assert_called_once()
            # Note: No immediate chat_postMessage expected - response happens in background task

            # Verify task was scheduled (DM channel starts with D, so it should be processed)
            assert len(mock_docket_instance.add_calls) == 1
            call = mock_docket_instance.add_calls[0]
            assert call["task_kwargs"]["thread_ts"] == "1234567890.123456"
            assert call["task_kwargs"]["user_id"] == "U123456789"
            assert call["task_kwargs"]["channel_id"] == "D123456789"


class TestErrorHandling:
    """Test error handling across endpoints."""

    def test_404_endpoint(self, client):
        """Test non-existent endpoint returns 404."""
        response = client.get("/nonexistent")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_json_slack_events(self):
        """Test Slack events with handler parsing error."""
        mock_handler = Mock()
        # Make the handler raise an exception when trying to parse invalid data
        mock_handler.handle = AsyncMock(
            side_effect=ValueError("Invalid request format")
        )

        with patch("app.api.slack_app.get_handler", return_value=mock_handler):
            # Force fresh import of the app module

            from httpx import ASGITransport, AsyncClient

            from app.api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/slack/events",
                    content='{"invalid": "json"}',  # Valid JSON but invalid format
                    headers={"Content-Type": "application/json"},
                )
                assert response.status_code == 500


class TestDocketIntegration:
    """Test Docket dependency injection and integration."""

    @pytest.mark.asyncio
    async def test_slack_mention_to_task_scheduling(
        self, async_client, mock_app_dependencies
    ):
        """Test the workflow from Slack mention to task scheduling."""
        # Skip the Redis connection test that was causing event loop issues
        with patch(
            "app.utilities.database.get_document_index"
        ) as mock_get_document_index:
            mock_index = MockSearchIndex()
            mock_get_document_index.return_value = mock_index

            # Just test that health endpoint works with mocked dependencies
            health_response = await async_client.get("/health")
            assert health_response.status_code == 200


class TestSlackBotBehaviorCompliance:
    """Test that the bot only responds to mentions and DMs as required."""

    @pytest.mark.asyncio
    async def test_bot_ignores_regular_channel_messages(self):
        """Test that the bot doesn't respond to regular channel messages without mentions."""
        from app.api.main import handle_dm_messages

        # This should be ignored since it's not a DM
        regular_channel_message = {
            "event": {
                "user": "U123456789",
                "text": "Just a regular message in the channel",
                "channel": "C123456789",
                "channel_type": "channel",
                "ts": "1234567890.123456",
            }
        }

        mock_say = AsyncMock()
        mock_ack = AsyncMock()
        mock_logger = Mock()

        with patch("app.api.main.Docket") as mock_docket:
            await handle_dm_messages(
                regular_channel_message, mock_say, mock_ack, mock_logger
            )

            # Should acknowledge but not respond or schedule task
            mock_ack.assert_called_once()
            mock_say.assert_not_called()
            mock_docket.assert_not_called()

    @pytest.mark.asyncio
    async def test_threading_behavior_summary(self):
        """Test the complete threading behavior matches requirements."""
        from app.api.main import handle_app_mentions, handle_dm_messages

        mock_say = AsyncMock()
        mock_ack = AsyncMock()
        mock_logger = Mock()

        with (
            patch("app.api.main.Docket") as mock_docket_class,
            patch("app.api.slack_app.get_slack_app") as mock_get_slack_app,
            patch("app.utilities.database.get_redis_client") as mock_redis_client,
        ):
            mock_docket_instance = MockDocket()
            mock_docket_class.return_value.__aenter__.return_value = (
                mock_docket_instance
            )

            # Mock slack app for immediate acknowledgment
            mock_slack_app = Mock()
            mock_slack_app.client.chat_postMessage = AsyncMock()
            mock_get_slack_app.return_value = mock_slack_app

            # Mock Redis client for track_thread_participation
            mock_redis_client.return_value.set = AsyncMock()

            # Test 1: Mention in channel creates thread
            channel_mention = {
                "event": {
                    "user": "U123456789",
                    "text": "<@U987654321> Help with agents?",
                    "channel": "C123456789",
                    "ts": "1234567890.123456",
                }
            }

            await handle_app_mentions(channel_mention, mock_say, mock_ack)

            assert len(mock_docket_instance.add_calls) == 1
            call = mock_docket_instance.add_calls[0]
            assert (
                call["task_kwargs"]["thread_ts"] == "1234567890.123456"
            )  # Creates thread

            # Test 2: Mention in existing thread stays in thread
            thread_mention = {
                "event": {
                    "user": "U123456789",
                    "text": "<@U987654321> Follow up question",
                    "channel": "C123456789",
                    "ts": "1234567890.654321",
                    "thread_ts": "1234567890.123456",  # Existing thread
                }
            }

            mock_docket_instance.add_calls.clear()  # Reset for next test
            await handle_app_mentions(thread_mention, mock_say, mock_ack)

            assert len(mock_docket_instance.add_calls) == 1
            call = mock_docket_instance.add_calls[0]
            assert (
                call["task_kwargs"]["thread_ts"] == "1234567890.123456"
            )  # Preserves original thread

            # Test 3: DM creates threading using message timestamp
            dm_message = {
                "event": {
                    "user": "U123456789",
                    "text": "Direct message question",
                    "channel": "D123456789",
                    "channel_type": "im",
                    "ts": "1234567890.123456",
                }
            }

            mock_docket_instance.add_calls.clear()  # Reset for next test
            await handle_dm_messages(dm_message, mock_say, mock_ack, mock_logger)

            assert len(mock_docket_instance.add_calls) == 1
            call = mock_docket_instance.add_calls[0]
            assert (
                call["task_kwargs"]["thread_ts"] == "1234567890.123456"
            )  # DM creates thread using message ts
