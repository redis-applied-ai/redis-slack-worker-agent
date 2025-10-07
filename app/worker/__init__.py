"""
Worker module for the applied-ai-agent.

This module contains the worker functionality for executing docket tasks
that are at the core of the agent application for async execution.
"""

from .task_registration import (
    register_agent_tasks,
    register_all_tasks,
    register_etl_tasks,
)
from .worker import main

__all__ = ["main", "register_all_tasks", "register_agent_tasks", "register_etl_tasks"]
