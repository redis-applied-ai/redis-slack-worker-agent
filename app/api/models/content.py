"""
Content management API request and response models.
"""

from typing import Any, Dict, Literal

from pydantic import BaseModel, Field


class AddContentRequest(BaseModel):
    """Request model for adding new content."""

    name: str = Field(..., description="Name of the content item")
    content_type: Literal["blog", "notebook", "repo"] = Field(
        ..., description="Type of content"
    )
    content_url: str = Field(..., description="URL where the content can be accessed")


class PipelineResponse(BaseModel):
    """Response model for pipeline operations."""

    status: Literal["success", "failed"] = "success"
    message: str
    result: Dict[str, Any]
