"""
Health check response models.
"""

from datetime import datetime
from typing import Dict, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Simple health check response."""

    status: Literal["healthy"] = "healthy"
    message: str = "Advanced Slack RAG Bot is running! 🚀"


class DetailedHealthResponse(BaseModel):
    """Detailed health check response with component status."""

    status: Literal["healthy", "unhealthy"]
    components: Dict[str, Literal["available", "unavailable"]]
    timestamp: datetime = Field(default_factory=lambda: datetime.utcnow())
