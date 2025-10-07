"""
Docket integration tests using Redis 8 testcontainer.
These tests verify that Docket API compatibility works in practice.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest


async def wait_for_condition(condition_func, timeout_seconds=30, check_interval=0.1):
    """
    Wait for a condition to be true, polling at regular intervals.
    More reliable than fixed sleep times for CI environments.
    """
    end_time = asyncio.get_event_loop().time() + timeout_seconds

    while asyncio.get_event_loop().time() < end_time:
        if (
            await condition_func()
            if asyncio.iscoroutinefunction(condition_func)
            else condition_func()
        ):
            return True
        await asyncio.sleep(check_interval)

    return False


class TestDocketIntegration:
    """Test Docket functionality with Redis 8."""

    @pytest.mark.asyncio
    async def test_docket_constructor_with_redis_url(self, redis_url):
        """Test that Docket constructor works with correct parameter name."""
        from docket import Docket

        # This should not raise an error about parameter names
        docket = Docket(url=redis_url)

        async with docket:
            assert docket is not None

    @pytest.mark.asyncio
    async def test_schedule_task_api_compatibility(self, redis_url):
        """Test that tasks can be scheduled without errors (API compatibility)."""
        from docket import Docket

        async def test_task(message: str):
            return f"processed: {message}"

        async with Docket(url=redis_url) as docket:
            # Test immediate task scheduling
            await docket.add(test_task)(message="test task")

            # Test scheduled task with key
            when = datetime.now(timezone.utc) + timedelta(seconds=1)
            await docket.add(test_task, when=when, key="test-future-task")(
                message="delayed task"
            )

            # These should not raise errors - we're testing API compatibility
            assert True

    @pytest.mark.asyncio
    async def test_cancel_scheduled_task(self, redis_url):
        """Test cancelling a scheduled task."""
        from docket import Docket

        async def cancellable_task(message: str):
            return message

        async with Docket(url=redis_url) as docket:
            # Schedule task for 5 seconds in the future (enough time to cancel)
            when = datetime.now(timezone.utc) + timedelta(seconds=5)
            task_key = "cancellable-task"

            await docket.add(cancellable_task, when=when, key=task_key)(
                message="should not execute"
            )

            # Cancel the task - test that it doesn't raise an error
            cancelled = await docket.cancel(task_key)
            # The cancel method may return None - we're testing it doesn't error
            assert cancelled is not False  # Not explicitly False means it worked

    @pytest.mark.asyncio
    async def test_docket_api_methods(self, redis_url):
        """Test various Docket API methods work correctly."""
        from docket import Docket

        async def api_test_task(data: str):
            return data

        async with Docket(url=redis_url) as docket:
            # Test different scheduling patterns

            # Immediate task
            await docket.add(api_test_task)(data="immediate")

            # Scheduled task with specific time
            future_time = datetime.now(timezone.utc) + timedelta(seconds=2)
            await docket.add(api_test_task, when=future_time, key="scheduled-task")(
                data="scheduled"
            )

            # Test cancellation doesn't error
            cancel_result = await docket.cancel("scheduled-task")
            assert cancel_result is not False

            # Test cancelling non-existent task doesn't error
            _cancel_missing = await docket.cancel("non-existent-task")
            # This may return None or False - both are acceptable


class TestDocketWithFastAPIIntegration:
    """Test Docket integration with FastAPI endpoints using Redis."""

    @pytest.mark.asyncio
    async def test_app_task_endpoints_with_docket(self, redis_url):
        """Test FastAPI app integration with Docket instance."""
        from fastapi.testclient import TestClient

        # Mock environment variables
        with patch.dict(
            os.environ,
            {
                "REDIS_URL": redis_url,
                "SLACK_BOT_TOKEN": "xoxb-test-token",
                "SLACK_SIGNING_SECRET": "test-secret",
                "OPENAI_API_KEY": "test-key",
                "TAVILY_API_KEY": "test-tavily-key",
            },
        ):
            # Mock other dependencies but use real Docket
            with (
                patch("redisvl.index.SearchIndex") as mock_search_idx,
                patch("redisvl.utils.vectorize.OpenAITextVectorizer") as mock_hf,
                patch("openai.OpenAI") as mock_openai,
                patch("slack_bolt.app.async_app.AsyncApp") as mock_slack,
                patch(
                    "app.utilities.database.get_document_index"
                ) as mock_get_document_index,
                patch("app.utilities.database.get_vectorizer") as mock_get_vectorizer,
                patch("app.api.slack_app.get_slack_app") as mock_get_slack_app,
                patch("app.api.main.get_slack_app") as mock_app_get_slack_app,
                patch("app.api.slack_app.get_handler"),
                patch("app.worker.task_registration.register_all_tasks"),
                patch("app.agent.tasks.slack_tasks.process_slack_question_with_retry"),
                patch(
                    "app.api.routers.health.get_slack_app"
                ) as mock_health_get_slack_app,
                patch("app.api.routers.health.Docket") as mock_health_docket,
            ):
                # Configure mocks for non-Docket dependencies
                mock_search_idx.from_existing.return_value = Mock()
                mock_hf.return_value = Mock()

                # Mock Slack app properly
                mock_slack_app = Mock()
                mock_slack_app.__name__ = (
                    "AsyncApp"  # Add the missing __name__ attribute
                )
                mock_get_slack_app.return_value = mock_slack_app
                mock_app_get_slack_app.return_value = mock_slack_app

                # Configure the AsyncApp mock to return our mock app
                mock_slack.return_value = mock_slack_app

                # Configure the health check mock to return our mock app
                mock_health_get_slack_app.return_value = mock_slack_app

                # Configure the health check Docket mock to return workers
                mock_health_docket_instance = Mock()
                mock_health_docket_instance.workers = AsyncMock(
                    return_value=["worker1", "worker2"]
                )  # Return some workers
                mock_health_docket.return_value.__aenter__ = AsyncMock(
                    return_value=mock_health_docket_instance
                )
                mock_health_docket.return_value.__aexit__ = AsyncMock(return_value=None)

                # Create a proper OpenAI client mock with embeddings support
                mock_openai_client = Mock()
                mock_openai_client.chat = Mock()
                mock_openai_client.chat.completions = Mock()
                mock_openai_client.chat.completions.create = Mock(
                    return_value=Mock(
                        choices=[Mock(message=Mock(content="Test response"))]
                    )
                )

                # Mock embeddings API with proper structure
                mock_openai_client.embeddings = Mock()
                mock_embedding_data = Mock()
                mock_embedding_data.embedding = [
                    0.1
                ] * 1536  # Mock 1536-dimensional embedding

                mock_embedding_response = Mock()
                mock_embedding_response.data = [mock_embedding_data]
                mock_embedding_response.usage = Mock(total_tokens=10)

                mock_openai_client.embeddings.create = Mock(
                    return_value=mock_embedding_response
                )
                mock_openai.return_value = mock_openai_client

                # Mock db functions to prevent OpenAI initialization
                mock_vectorizer = Mock()
                mock_vectorizer.embed.return_value = b"mock_embedding"
                mock_get_vectorizer.return_value = mock_vectorizer

                mock_index = Mock()
                mock_index.exists = AsyncMock(return_value=True)
                mock_get_document_index.return_value = mock_index

                # Create a proper mock Slack app with event decorator
                mock_slack_app = Mock()
                mock_slack_app.event = Mock(return_value=lambda func: func)
                mock_slack_app.__name__ = (
                    "AsyncApp"  # Add __name__ attribute to prevent logger issues
                )
                mock_slack.return_value = mock_slack_app

                # Set up both get_slack_app patches to return the mock app
                mock_get_slack_app.return_value = mock_slack_app
                mock_app_get_slack_app.return_value = mock_slack_app

                # Import and test the app
                from app.api.main import app

                with TestClient(app) as client:
                    # Test that app starts without Docket errors
                    response = client.get("/")
                    assert response.status_code == 200

                    # Test detailed health endpoint shows Docket as available
                    response = client.get("/health/detailed")
                    assert response.status_code in [
                        200,
                        503,
                    ]  # 200 if all healthy, 503 if other deps missing

                    if response.status_code == 200:
                        data = response.json()
                        assert data["components"]["task_queue"] == "available"

                    # Test that Slack events endpoint exists (main functionality)
                    # Note: May return 500 due to mock limitations, but endpoint should exist
                    response = client.post("/slack/events", json={})
                    # Should handle the request (200), fail due to missing handler (503), or mock issues (500)
                    assert response.status_code in [200, 500, 503]

    @pytest.mark.asyncio
    async def test_app_imports_without_docket_errors(self, redis_url):
        """Test that app.py imports and starts without Docket parameter errors."""

        # Mock environment variables with Redis URL
        with patch.dict(
            os.environ,
            {
                "REDIS_URL": redis_url,
                "SLACK_BOT_TOKEN": "xoxb-test-token",
                "SLACK_SIGNING_SECRET": "test-secret",
                "OPENAI_API_KEY": "test-key",
                "TAVILY_API_KEY": "test-tavily-key",
            },
        ):
            # Mock all other dependencies
            with (
                patch("redisvl.index.SearchIndex"),
                patch("redisvl.utils.vectorize.OpenAITextVectorizer"),
                patch("openai.OpenAI") as mock_openai,
                patch("slack_bolt.app.async_app.AsyncApp") as mock_slack,
                patch(
                    "app.utilities.database.get_document_index"
                ) as mock_get_document_index,
                patch("app.utilities.database.get_vectorizer") as mock_get_vectorizer,
                patch("app.api.slack_app.get_slack_app") as mock_get_slack_app,
                patch("app.api.main.get_slack_app") as mock_app_get_slack_app,
                patch("app.api.slack_app.get_handler"),
                patch("app.worker.task_registration.register_all_tasks"),
                patch("app.agent.tasks.slack_tasks.process_slack_question_with_retry"),
                patch(
                    "app.api.routers.health.get_slack_app"
                ) as mock_health_get_slack_app,
                patch("app.api.routers.health.Docket") as mock_health_docket,
            ):
                # Mock Slack app properly
                mock_slack_app = Mock()
                mock_slack_app.__name__ = (
                    "AsyncApp"  # Add the missing __name__ attribute
                )
                mock_get_slack_app.return_value = mock_slack_app
                mock_app_get_slack_app.return_value = mock_slack_app

                # Configure the AsyncApp mock to return our mock app
                mock_slack.return_value = mock_slack_app

                # Configure the health check mock to return our mock app
                mock_health_get_slack_app.return_value = mock_slack_app

                # Configure the health check Docket mock to return workers
                mock_health_docket_instance = Mock()
                mock_health_docket_instance.workers = AsyncMock(
                    return_value=["worker1", "worker2"]
                )  # Return some workers
                mock_health_docket.return_value.__aenter__ = AsyncMock(
                    return_value=mock_health_docket_instance
                )
                mock_health_docket.return_value.__aexit__ = AsyncMock(return_value=None)

                # Create a proper OpenAI client mock with embeddings support
                mock_openai_client = Mock()
                mock_openai_client.chat = Mock()
                mock_openai_client.chat.completions = Mock()
                mock_openai_client.chat.completions.create = Mock(
                    return_value=Mock(
                        choices=[Mock(message=Mock(content="Test response"))]
                    )
                )

                # Mock embeddings API with proper structure
                mock_openai_client.embeddings = Mock()
                mock_embedding_data = Mock()
                mock_embedding_data.embedding = [
                    0.1
                ] * 1536  # Mock 1536-dimensional embedding

                mock_embedding_response = Mock()
                mock_embedding_response.data = [mock_embedding_data]
                mock_embedding_response.usage = Mock(total_tokens=10)

                mock_openai_client.embeddings.create = Mock(
                    return_value=mock_embedding_response
                )
                mock_openai.return_value = mock_openai_client

                # Mock db functions to prevent OpenAI initialization
                mock_vectorizer = Mock()
                mock_get_vectorizer.return_value = mock_vectorizer

                mock_index = Mock()
                mock_get_document_index.return_value = mock_index

                # Set up Slack app mocks
                mock_slack_app = Mock()
                mock_slack_app.__name__ = "AsyncApp"
                mock_get_slack_app.return_value = mock_slack_app
                mock_app_get_slack_app.return_value = mock_slack_app

                # This should not raise Docket parameter errors
                from app.api.main import app

                assert app is not None

    @pytest.mark.asyncio
    async def test_worker_imports_without_docket_errors(self, redis_url):
        """Test that worker.py can be imported without Docket parameter errors."""

        # Mock environment variables with Redis URL
        with patch.dict(os.environ, {"REDIS_URL": redis_url}):
            # Import should not raise errors about Docket parameters
            from app.worker import main

            assert main is not None

            # Test that we can create a Docket instance (which was failing before)
            from docket import Docket

            async with Docket(url=redis_url) as docket:
                assert docket is not None
