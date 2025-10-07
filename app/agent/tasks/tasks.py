"""
Main task registration and management for the applied-ai-agent.

This module provides the main task registration functionality and re-exports
all agent tasks for backward compatibility.
"""

import logging

from docket import Docket

from app.utilities.environment import get_env_var

from . import task_collection

logger = logging.getLogger(__name__)


# Get REDIS_URL dynamically
def get_redis_url() -> str:
    return get_env_var("REDIS_URL", "redis://localhost:6379/0")


async def register_tasks() -> None:
    """Register all agent task functions with Docket."""
    async with Docket(url=get_redis_url()) as docket:
        # Register all tasks
        for task in task_collection:
            docket.register(task)

        logger.info(f"Registered {len(task_collection)} agent tasks with Docket")


# Re-export all agent tasks for backward compatibility
from .slack_tasks import *
