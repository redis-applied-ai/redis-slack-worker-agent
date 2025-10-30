"""
Test configuration and fixtures for the Slack RAG bot.
"""

import os
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis as AsyncRedis
from testcontainers.compose import DockerCompose

# Patch Prefect's RichConsoleHandler to a no-op to avoid ValueError on closed file in CI/CD
try:
    import prefect.logging.handlers

    class NoOpConsoleHandler:
        def emit(self, record):
            pass

        def handleError(self, record):
            pass  # Suppress all error output

    prefect.logging.handlers.RichConsoleHandler = NoOpConsoleHandler
except Exception:
    pass


# Test environment variables
os.environ.update(
    {
        "REDIS_URL": "redis://localhost:6379/0",
        "SLACK_BOT_TOKEN": "xoxb-test-token",
        "SLACK_SIGNING_SECRET": "test-signing-secret",
        "OPENAI_API_KEY": "test-openai-key",
        "TAVILY_API_KEY": "test-tavily-key",
        "LOCAL": "false",  # Disable local mode for tests
        "LLM_PROVIDER": "openai",  # Ensure legacy tests exercise the OpenAI path
    }
)
# Prevent .env from overriding test environment variables during test session
try:
    from dotenv import load_dotenv

    import app.utilities.environment as _env_mod

    # Load .env without overriding explicitly-set environment variables
    load_dotenv(override=False)
    # Mark as loaded to skip future override=True reloads inside get_env_var()
    if hasattr(_env_mod, "_env_loaded"):
        _env_mod._env_loaded = True  # type: ignore[attr-defined]
except Exception:
    pass


@pytest.fixture
def sample_team_data() -> List[Dict[str, Any]]:
    """Sample team data for testing."""
    return [
        {
            "name": "Robert",
            "description": "Personality hire with a Python background. Strong focus on evaluation and metric-driven development.",
            "day_off": "Monday",
        },
        {
            "name": "Justin",
            "description": "Research background. Co-authored LangCache research. Wrote RedisVL implementations with hybrid search. Python expertise.",
            "day_off": "Tuesday",
        },
        {
            "name": "Andrew",
            "description": "Agent memory specialist. Python developer. Passionate about LangGraph and author of the agent memory repository.",
            "day_off": "Wednesday",
        },
    ]


@pytest.fixture
def mock_redis_search_results():
    """Mock Redis search results."""
    return [
        {
            "name": "Andrew",
            "description": "Agent memory specialist. Python developer. Passionate about LangGraph and author of the agent memory repository.",
            "day_off": "Wednesday",
        }
    ]


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response."""
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = (
        "Andrew would be the best choice for this meeting about agents, but note that he's off on Wednesday."
    )
    return mock_response


@pytest.fixture
def mock_search_index():
    """Mock RedisVL SearchIndex."""
    with patch("redisvl.index.SearchIndex") as mock_class:
        mock_instance = Mock()
        mock_instance.query.return_value = [
            {
                "name": "Andrew",
                "description": "Agent memory specialist. Python developer. Passionate about LangGraph and author of the agent memory repository.",
                "day_off": "Wednesday",
            }
        ]
        mock_class.from_existing.return_value = mock_instance
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_hf_vectorizer():
    """Mock HuggingFace text vectorizer."""
    with patch("redisvl.utils.vectorize.OpenAITextVectorizer") as mock_class:
        mock_instance = Mock()
        mock_instance.embed.return_value = b"fake_vector_data"
        mock_instance.embed_many.return_value = [
            b"fake_vector_1",
            b"fake_vector_2",
            b"fake_vector_3",
        ]
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client."""
    with patch("openai.OpenAI") as mock_class:
        mock_instance = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = (
            "Andrew would be the best choice for this meeting about agents, but note that he's off on Wednesday."
        )
        mock_instance.chat.completions.create.return_value = mock_response
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_slack_app():
    """Mock Slack AsyncApp."""
    with patch("slack_bolt.app.async_app.AsyncApp") as mock_class:
        mock_instance = AsyncMock()
        mock_instance.client.chat_postMessage = AsyncMock()
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_docket():
    """Mock Docket task queue."""
    with patch("docket.Docket") as mock_class:
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_instance.add = AsyncMock()
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def app_with_mocks():
    """FastAPI app with all dependencies mocked."""
    # Set up environment variables first
    os.environ.update(
        {
            "REDIS_URL": "redis://localhost:6379/0",
            "SLACK_BOT_TOKEN": "xoxb-test-token",
            "SLACK_SIGNING_SECRET": "test-signing-secret",
            "OPENAI_API_KEY": "test-openai-key",
            "TAVILY_API_KEY": "test-tavily-key",
        }
    )

    mock_index = Mock()
    mock_hf = Mock()
    mock_slack_app = Mock()
    mock_slack_app.event = Mock(
        return_value=lambda func: func
    )  # Mock the event decorator
    mock_docket = Mock()
    mock_handler = Mock()
    mock_handler.handle = Mock()

    with (
        patch("app.api.main.REDIS_URL", "redis://localhost:6379/0"),
        patch("app.utilities.database.get_document_index", return_value=mock_index),
        patch("app.utilities.database.get_vectorizer", return_value=mock_hf),
        patch("app.api.slack_app.get_slack_app", return_value=mock_slack_app),
        patch("app.api.slack_app.get_handler", return_value=mock_handler),
        patch("app.api.main.get_docket", return_value=mock_docket),
    ):
        from app.api.main import app

        yield app


@pytest.fixture
def test_client(app_with_mocks):
    """Test client for the FastAPI app."""
    return TestClient(app_with_mocks)


@pytest_asyncio.fixture
async def async_test_client(app_with_mocks):
    """Async test client for the FastAPI app."""

    async with AsyncClient(
        transport=ASGITransport(app=app_with_mocks), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
def sample_slack_event():
    """Sample Slack app mention event."""
    return {
        "event": {
            "user": "U123456789",
            "text": "<@U987654321> Which team member would be best for a meeting about agents on Tuesday?",
            "channel": "C123456789",
            "thread_ts": "1234567890.123456",
        }
    }


@pytest.fixture(scope="session", autouse=True)
def redis_container(request):
    """
    If using xdist, create a unique Compose project for each xdist worker by
    setting COMPOSE_PROJECT_NAME. That prevents collisions on container/volume
    names.
    """
    # In xdist, the config has "workerid" in workerinput
    workerinput = getattr(request.config, "workerinput", {})
    worker_id = workerinput.get("workerid", "master")

    # Set the Compose project name so containers do not clash across workers
    os.environ["COMPOSE_PROJECT_NAME"] = f"redis_test_{worker_id}"
    os.environ.setdefault("REDIS_IMAGE", "redis:8-alpine")

    compose = DockerCompose(
        context="tests",
        compose_file_name="docker-compose.yml",
        pull=True,
    )
    compose.start()

    yield compose

    compose.stop()


@pytest.fixture(scope="session")
def redis_url(redis_container):
    """
    Use the `DockerCompose` fixture to get host/port of the 'redis' service
    on container port 6379 (mapped to an ephemeral port on the host).
    """
    host, port = redis_container.get_service_host_and_port("redis", 6379)
    return f"redis://{host}:{port}"


@pytest_asyncio.fixture()
async def async_redis_client(redis_url):
    """
    An async Redis client that uses the dynamic `redis_url`.
    """
    client = AsyncRedis.from_url(redis_url)
    yield client
    await client.aclose()
