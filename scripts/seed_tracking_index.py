#!/usr/bin/env python3
"""
Seed script for populating the knowledge tracking index with initial content.
"""

import logging
from datetime import datetime, timezone

import redis
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Simple content data
CONTENT_ITEMS = [
    {
        "name": "hybrid-search-notebook",
        "content_type": "notebook",
        "content_url": "https://github.com/redis-developer/redis-ai-resources/blob/main/python-recipes/vector-search/02_hybrid_search.ipynb",
    },
    {
        "name": "redis-retrieval-optimizer",
        "content_type": "repo",
        "content_url": "https://github.com/redis-applied-ai/redis-retrieval-optimizer",
    },
    {
        "name": "building-feature-stores-with-redis",
        "content_type": "blog",
        "content_url": "https://redis.io/blog/building-feature-stores-with-redis-introduction-to-feast-with-redis/",
    },
]


def create_tracking_record(name: str, content_type: str, content_url: str) -> dict:
    """Create a tracking record with default values."""
    current_time = datetime.now(timezone.utc)
    current_timestamp = int(current_time.timestamp())

    return {
        "name": name,
        "content_type": content_type,
        "content_url": content_url,
        "archive": False,
        "source_date": "",
        "updated_date": "",
        "updated_ts": current_timestamp,
        "bucket_url": "",
        "processing_status": "pending",
        "last_processing_attempt": 0,
        "failure_reason": "",
        "retry_count": 0,
    }


def seed_tracking_index():
    """Seed the knowledge tracking index with initial content."""
    logger.info("Starting to seed knowledge tracking index...")

    try:
        # Connect to Redis
        client = redis.Redis.from_url("redis://localhost:6379/0")

        total_added = 0

        for item in CONTENT_ITEMS:
            # Create tracking record
            record = create_tracking_record(
                name=item["name"],
                content_type=item["content_type"],
                content_url=item["content_url"],
            )

            # Store in Redis using JSON
            doc_id = f"knowledge_tracking:{item['name']}"
            client.json().set(doc_id, "$", record)
            total_added += 1

            logger.info(f"Added {item['content_type']}: {item['name']}")

        logger.info(
            f"Successfully seeded {total_added} items to knowledge tracking index"
        )

    except Exception as e:
        logger.error(f"Failed to seed tracking index: {e}")
        raise


def main():
    """Main function to run the seeding process."""
    logging.basicConfig(level=logging.INFO)
    seed_tracking_index()


if __name__ == "__main__":
    main()
