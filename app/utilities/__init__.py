"""
Utilities package for the applied-ai-agent.

This package contains shared utilities and common functionality used across
API, Agent, and ETL modules.
"""

# Note: Individual modules are imported directly by consumers,
# so we only re-export specific commonly used functions

# Re-export commonly used functions for easy access
from .database import (
    get_answer_index,
    get_document_index,
    get_redis_client,
    get_vectorizer,
)
from .environment import get_env_var
from .keys import (
    answer_key,
    debounced_reminder_key,
    intent_classification_cache_key,
    thread_activity_key,
    thread_participation_key,
    thread_rate_limit_key,
)
from .metrics import get_token_metrics
from .openai_client import get_instrumented_client
from .s3_utils import get_s3_manager
from .telemetry import setup_telemetry

__all__ = [
    # Database utilities
    "get_answer_index",
    "get_document_index",
    "get_redis_client",
    "get_vectorizer",
    # Environment utilities
    "get_env_var",
    # Key utilities
    "answer_key",
    "debounced_reminder_key",
    "intent_classification_cache_key",
    "thread_activity_key",
    "thread_participation_key",
    "thread_rate_limit_key",
    # Metrics utilities
    "get_token_metrics",
    # OpenAI utilities
    "get_instrumented_client",
    # S3 utilities
    "get_s3_manager",
    # Telemetry utilities
    "setup_telemetry",
]
