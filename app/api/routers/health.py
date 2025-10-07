"""
Health check endpoints.

This module provides health check endpoints for monitoring and load balancer health checks.
"""

from datetime import datetime, timezone

from docket.docket import Docket
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.api.slack_app import get_slack_app
from app.utilities.database import get_document_index, get_vectorizer
from app.utilities.environment import get_env_var

from ..models.health import DetailedHealthResponse


# Get Redis URL dynamically
def get_redis_url() -> str:
    return get_env_var("REDIS_URL", "redis://localhost:6379/0")


router = APIRouter(tags=["health"])


@router.get("/health", response_class=PlainTextResponse)
@router.head("/health")
async def health_check() -> str:
    """
    Simple, fast health check for load balancer - no external dependencies.

    Returns:
        Simple text response indicating the service is running
    """
    return "Advanced Slack RAG Bot is running! 🚀"


@router.get("/health/detailed", response_model=DetailedHealthResponse)
@router.head("/health/detailed")
async def detailed_health_check() -> DetailedHealthResponse:
    """
    Detailed health check with component status information.

    Returns:
        Detailed health status including individual component availability
    """
    try:
        index = get_document_index()
        index_available = await index.exists()
    except Exception:
        index_available = False

    try:
        async with Docket(url=get_redis_url()) as docket:
            workers = await docket.workers()
            task_queue_available = bool(workers)
    except Exception:
        task_queue_available = False

    components = {
        "vector_index": "available" if index_available else "unavailable",
        "vectorizer": "available" if get_vectorizer() is not None else "unavailable",
        "slack_app": "available" if get_slack_app() is not None else "unavailable",
        "task_queue": "available" if task_queue_available else "unavailable",
    }

    # Determine overall status
    all_healthy = all(status == "available" for status in components.values())
    status = "healthy" if all_healthy else "unhealthy"

    return DetailedHealthResponse(
        status=status, components=components, timestamp=datetime.now(timezone.utc)
    )
