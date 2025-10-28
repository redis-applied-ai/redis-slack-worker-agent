"""
Agent package for the applied-ai-agent.

This package contains all agent functionality organized into focused modules.
"""

# Re-export all core functionality
from .core import (
    SYSTEM_PROMPT,
    answer_question,
    create_initial_message_without_search,
    get_client,
    get_memory_client,
    is_brief_satisfied_response,
)

# Re-export all agent tasks
from .tasks import *

# Re-export all tools
from .tools import (
    get_search_tool_config,
    perform_web_search,
    search_knowledge_base,
    search_knowledge_base_with_metadata,
)

# For backward compatibility, also export the main functions directly
__all__ = [
    # Core functions
    "answer_question",
    "create_initial_message_without_search",
    "get_client",
    "get_memory_client",
    "is_brief_satisfied_response",
    "SYSTEM_PROMPT",
    # Tool functions
    "get_search_tool_config",
    "perform_web_search",
    "search_knowledge_base",
    "search_knowledge_base_with_metadata",
    # All task functions are available via the wildcard import
]
