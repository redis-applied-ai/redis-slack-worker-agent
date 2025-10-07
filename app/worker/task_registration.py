"""
Task registration module for Docket.

This module centralizes all Docket task registration for the worker.
It imports and registers tasks from both agent and ETL modules.
"""

import logging
from typing import Callable, List

from app.agent.tasks.slack_tasks import (
    process_slack_question_with_retry,
    send_delayed_reminder,
    update_answer_feedback,
)
from app.etl.tasks import (
    add_content_to_knowledge_base,
    process_blog,
    process_content_pipeline,
    process_notebook,
    process_repository,
    remove_content_from_knowledge_base,
    run_artifact_processing_pipeline,
    run_ingestion_pipeline,
    run_ingestion_pipeline_background,
    run_vectorization_pipeline,
    trigger_artifact_processing_pipeline,
    trigger_ingestion_pipeline,
    update_content_in_knowledge_base,
)
from app.etl.tasks.ingestion import extend_documentation
from app.etl.tasks.vectorization import process_content_file

logger = logging.getLogger(__name__)

# Agent tasks
agent_tasks: List[Callable] = [
    process_slack_question_with_retry,
    send_delayed_reminder,
    update_answer_feedback,
]

# ETL tasks
etl_tasks: List[Callable] = [
    # Content management tasks
    add_content_to_knowledge_base,
    update_content_in_knowledge_base,
    remove_content_from_knowledge_base,
    process_content_pipeline,
    trigger_ingestion_pipeline,
    run_ingestion_pipeline_background,
    trigger_artifact_processing_pipeline,
    run_artifact_processing_pipeline,
    run_ingestion_pipeline,
    run_vectorization_pipeline,
    # Individual ingestion tasks
    process_repository,
    process_blog,
    process_notebook,
    extend_documentation,
    # Individual vectorization tasks
    process_content_file,
]

# All tasks combined
all_tasks: List[Callable] = agent_tasks + etl_tasks


async def register_all_tasks() -> None:
    """
    Register all Docket task functions.

    This function registers both agent and ETL tasks with Docket.
    """
    from docket import Docket

    from app.utilities.environment import get_env_var

    redis_url = get_env_var("REDIS_URL", "redis://localhost:6379/0")
    logger.debug("Task registration Redis connection configured")

    # Use async context manager with docket name as shown in working API code
    async with Docket(name="applied-ai-agent", url=redis_url) as docket:
        # Register all tasks
        logger.info(f"Registering {len(all_tasks)} tasks with Docket")
        for i, task in enumerate(all_tasks):
            try:
                # Use synchronous register (not await)
                docket.register(task)
                logger.debug(f"Registered task {i+1}/{len(all_tasks)}: {task.__name__}")
            except Exception as e:
                print(f"❌ Failed to register task {task.__name__}: {e}")
                raise

    logger.info(f"Registered {len(all_tasks)} total tasks with Docket")
    logger.info(f"  - Agent tasks: {len(agent_tasks)}")
    logger.info(f"  - ETL tasks: {len(etl_tasks)}")
    print(f"✅ Successfully registered all {len(all_tasks)} tasks")


async def register_agent_tasks() -> None:
    """Register only agent tasks with Docket."""
    from docket import Docket

    from app.utilities.environment import get_env_var

    redis_url = get_env_var("REDIS_URL", "redis://localhost:6379/0")

    async with Docket(url=redis_url) as docket:
        for task in agent_tasks:
            docket.register(task)

        logger.info(f"Registered {len(agent_tasks)} agent tasks with Docket")


async def register_etl_tasks() -> None:
    """Register only ETL tasks with Docket."""
    from docket import Docket

    from app.utilities.environment import get_env_var

    redis_url = get_env_var("REDIS_URL", "redis://localhost:6379/0")

    async with Docket(url=redis_url) as docket:
        for task in etl_tasks:
            docket.register(task)

        logger.info(f"Registered {len(etl_tasks)} ETL tasks with Docket")
