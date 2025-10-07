"""Unified application settings."""

from typing import Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings


class SideEffectSettings(BaseSettings):
    """Configuration for side effect behavior."""

    # Default TTL for side effects (None = persist until manually cleared)
    default_ttl_hours: Optional[float] = 1.0

    # Environment variable to trigger clearing of side effects
    # Examples: "all", "my_function", "my_function:*", "pattern:*"
    clear_side_effects: Optional[str] = None

    # Redis key prefix for side effects
    side_effect_prefix: str = "side_effect"

    class Config:
        env_prefix = "SIDE_EFFECT_"


class AppSettings(BaseSettings):
    """Main application settings that contains all sub-settings."""

    # Sub-settings - using Field(default_factory=...) to ensure fresh instances
    side_effects: SideEffectSettings = Field(default_factory=SideEffectSettings)
    # NOTE: PipelineSettings removed as pipelines module was deleted

    class Config:
        env_prefix = ""


load_dotenv()

# Global settings instance
settings = AppSettings()

# Convenience exports
side_effect_settings = settings.side_effects
# NOTE: pipeline_settings removed as pipelines module was deleted
