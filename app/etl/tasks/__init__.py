"""
ETL tasks package for the applied-ai-agent.

This package contains all ETL task modules organized by functionality.
"""

# Import all task functions for easy access
from .content_tasks import (
    add_content_to_knowledge_base,
    process_content_pipeline,
    remove_content_from_knowledge_base,
    run_artifact_processing_pipeline,
    run_ingestion_pipeline_background,
    trigger_artifact_processing_pipeline,
    trigger_ingestion_pipeline,
    update_content_in_knowledge_base,
)
from .ingestion import (
    process_blog,
    process_notebook,
    process_repository,
    run_ingestion_pipeline,
)
from .vectorization import run_vectorization_pipeline

# Note: Task registration has been moved to app.worker.task_registration
# This module now only contains the task function definitions


__all__ = [
    # Content management tasks
    "add_content_to_knowledge_base",
    "update_content_in_knowledge_base",
    "remove_content_from_knowledge_base",
    "process_content_pipeline",
    "trigger_ingestion_pipeline",
    "run_ingestion_pipeline_background",
    "trigger_artifact_processing_pipeline",
    "run_artifact_processing_pipeline",
    "run_ingestion_pipeline",
    "run_vectorization_pipeline",
    # Individual ingestion tasks
    "process_repository",
    "process_blog",
    "process_notebook",
]
