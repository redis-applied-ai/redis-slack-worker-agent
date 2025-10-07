"""
Main agent module for the applied-ai-agent.

This module provides the main agent interface and re-exports all functionality
from the organized modules for backward compatibility.
"""

# Re-export all core functionality
from .core import (
    answer_question,
    create_initial_message_without_search,
    get_client,
    get_memory_client,
    is_brief_satisfied_response,
    retrieve_context,
)

# Re-export all tasks
from .tasks import *

# Re-export all tools
from .tools import get_glean_search_tool, get_search_tool, get_web_search_tool

# For backward compatibility, also export the main functions directly
__all__ = [
    # Core functions
    "answer_question",
    "create_initial_message_without_search",
    "get_client",
    "get_memory_client",
    "is_brief_satisfied_response",
    "retrieve_context",
    # Tool functions
    "get_search_tool",
    "get_web_search_tool",
    "get_glean_search_tool",
    # All task functions are available via the wildcard import
]
