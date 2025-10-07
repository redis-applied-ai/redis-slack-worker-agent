"""
Ingestion queries and refresh logic.

This module contains the DRY functions for querying the knowledge tracking index
and determining what content needs to be processed based on refresh policies.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import redis
from redis.commands.search.query import Query

from app.utilities.environment import get_env_var

logger = logging.getLogger(__name__)


def get_redis_url() -> str:
    """Get Redis URL from environment."""
    return get_env_var("REDIS_URL", "redis://localhost:6379/0")


def build_ingestion_query() -> Query:
    """
    Build the Redis search query for content that needs ingestion.

    Returns content that is:
    - Not archived (@archive:{false})
    - Either staged OR stale (older than CONTENT_REFRESH_THRESHOLD_DAYS)

    Returns:
        Redis Query object for content needing ingestion
    """
    # For now, keep the simple query that gets all non-archived content
    # The refresh logic filtering happens in Python
    return Query("@archive:{false}").return_fields(
        "name",
        "content_type",
        "content_url",
        "processing_status",
        "source_date",
        "last_processing_attempt",
        "retry_count",
    )


def should_process_content(content_item: Dict[str, Any]) -> bool:
    """
    Determine if a content item should be processed based on refresh policies.

    Args:
        content_item: Content item from tracking index

    Returns:
        True if content should be processed
    """
    processing_status = content_item.get("processing_status", "pending")

    # Skip if already processing (but not completed - completed content can be refreshed if stale)
    if processing_status in ["processing", "ingest-pending", "vectorize-pending"]:
        return False

    # Always process staged content
    if processing_status == "staged":
        return True

    # Check if content is stale (older than threshold)
    refresh_threshold_days = int(get_env_var("CONTENT_REFRESH_THRESHOLD_DAYS", "7"))

    source_date_str = content_item.get("source_date")
    if not source_date_str:
        # No source date, treat as stale
        return True

    try:
        source_date = datetime.strptime(source_date_str, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
        cutoff_date = datetime.now(timezone.utc) - timedelta(
            days=refresh_threshold_days
        )
        return source_date < cutoff_date
    except (ValueError, TypeError):
        logger.warning(f"Invalid source_date format: {source_date_str}")
        # Invalid date format, treat as stale
        return True


def query_content_for_ingestion() -> List[Dict[str, Any]]:
    """
    Query the knowledge tracking index for content that needs ingestion.

    Returns:
        List of content items that need to be processed
    """
    try:
        # Connect to Redis and query content
        client = redis.Redis.from_url(get_redis_url())
        query = build_ingestion_query()

        search_results = client.ft("knowledge_tracking").search(query)
        logger.info(f"Found {len(search_results.docs)} total content items")

        # Parse results and apply refresh logic
        content_to_process = []

        for doc in search_results.docs:
            content_item = doc.__dict__

            if should_process_content(content_item):
                content_to_process.append(content_item)

        logger.info(
            f"Identified {len(content_to_process)} content items for processing"
        )
        return content_to_process

    except Exception as e:
        logger.error(f"Failed to query content for ingestion: {e}")
        raise


def filter_content_by_type(
    content_items: List[Dict[str, Any]], content_type: str
) -> List[Dict[str, Any]]:
    """
    Filter content items by content type.

    Args:
        content_items: List of content items
        content_type: Type to filter by (e.g. 'blog', 'repo', 'notebook')

    Returns:
        Filtered list of content items
    """
    return [item for item in content_items if item.get("content_type") == content_type]
