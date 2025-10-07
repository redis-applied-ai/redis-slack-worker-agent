"""
Content management configuration.

This module provides configuration settings for content management operations.
"""

from pydantic_settings import BaseSettings


class ContentSettings(BaseSettings):
    """Content management configuration settings."""

    s3_bucket_name: str = "applied-ai-agent-content"

    class Config:
        env_prefix = "CONTENT_MANAGEMENT_"
        env_file = ".env"
        extra = "ignore"


# Global settings instance
content_settings = ContentSettings()
