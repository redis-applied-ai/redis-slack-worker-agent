"""
Content ledger manager for tracking content state in Redis.
Manages content registry and processing queue for the knowledge base.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.utilities.database import get_redis_client

logger = logging.getLogger(__name__)

# Redis keys for ledger system
LEDGER_KEY = "ledger"
CONTENT_REGISTRY_KEY = "ledger:content_registry"
PROCESSING_QUEUE_KEY = "ledger:processing_queue"
CONTENT_STATUS_KEY = "ledger:content_status"


class ContentLedgerManager:
    """Manages content ledger and processing queue in Redis."""

    def __init__(self):
        self.redis_client = None

    async def _get_redis_client(self):
        """Get Redis client, initializing if needed."""
        if self.redis_client is None:
            self.redis_client = get_redis_client()
        return self.redis_client

    async def add_content_to_registry(
        self,
        content_type: str,
        content_name: str,
        s3_location: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Add content to the registry.

        Args:
            content_type: Type of content
            content_name: Name of the content
            s3_location: S3 location of the content
            metadata: Optional additional metadata

        Returns:
            True if successful
        """
        client = await self._get_redis_client()

        content_key = f"{content_type}:{content_name}"
        registry_key = f"{CONTENT_REGISTRY_KEY}:{content_key}"

        content_info = {
            "status": "active",
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "s3_location": s3_location,
            "vector_count": 0,
            "processing_status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        if metadata:
            content_info.update(metadata)

        try:
            # Use Redis JSON to store content info
            await client.json().set(registry_key, "$", content_info)
            await client.expire(registry_key, 0)  # No expiration

            # Add to content type index
            type_index_key = f"{CONTENT_REGISTRY_KEY}:types:{content_type}"
            await client.sadd(type_index_key, content_name)
            await client.expire(type_index_key, 0)

            logger.info(f"Added {content_key} to registry")
            return True

        except Exception as e:
            logger.error(f"Failed to add {content_key} to registry: {e}")
            raise

    async def update_content_in_registry(
        self, content_type: str, content_name: str, updates: Dict[str, Any]
    ) -> bool:
        """
        Update content in the registry.

        Args:
            content_type: Type of content
            content_name: Name of the content
            updates: Dictionary of fields to update

        Returns:
            True if successful
        """
        client = await self._get_redis_client()

        content_key = f"{content_type}:{content_name}"
        registry_key = f"{CONTENT_REGISTRY_KEY}:{content_key}"

        # Add timestamp
        updates["last_updated"] = datetime.now(timezone.utc).isoformat()

        try:
            # Use Redis JSON to update specific fields
            for field, value in updates.items():
                await client.json().set(registry_key, f"$.{field}", value)
            logger.info(f"Updated {content_key} in registry")
            return True

        except Exception as e:
            logger.error(f"Failed to update {content_key} in registry: {e}")
            raise

    async def remove_content_from_registry(
        self, content_type: str, content_name: str
    ) -> bool:
        """
        Remove content from the registry.

        Args:
            content_type: Type of content
            content_name: Name of the content

        Returns:
            True if successful
        """
        client = await self._get_redis_client()

        content_key = f"{content_type}:{content_name}"
        registry_key = f"{CONTENT_REGISTRY_KEY}:{content_key}"

        try:
            # Remove from registry
            await client.delete(registry_key)

            # Remove from type index
            type_index_key = f"{CONTENT_REGISTRY_KEY}:types:{content_type}"
            await client.srem(type_index_key, content_name)

            logger.info(f"Removed {content_key} from registry")
            return True

        except Exception as e:
            logger.error(f"Failed to remove {content_key} from registry: {e}")
            raise

    async def get_content_info(
        self, content_type: str, content_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get content information from registry.

        Args:
            content_type: Type of content
            content_name: Name of the content

        Returns:
            Content information dictionary or None if not found
        """
        client = await self._get_redis_client()

        content_key = f"{content_type}:{content_name}"
        registry_key = f"{CONTENT_REGISTRY_KEY}:{content_key}"

        try:
            content_info = await client.json().get(registry_key, "$")
            if content_info and content_info[0]:
                return content_info[0]
            return None

        except Exception as e:
            logger.error(f"Failed to get {content_key} info: {e}")
            raise

    async def list_content_by_type(self, content_type: str) -> List[Dict[str, Any]]:
        """
        List all content of a specific type.

        Args:
            content_type: Type of content to list

        Returns:
            List of content information dictionaries
        """
        client = await self._get_redis_client()

        type_index_key = f"{CONTENT_REGISTRY_KEY}:types:{content_type}"

        try:
            content_names = await client.smembers(type_index_key)
            content_list = []

            for content_name in content_names:
                content_info = await self.get_content_info(
                    content_type, content_name.decode()
                )
                if content_info:
                    content_list.append(content_info)

            logger.info(f"Listed {len(content_list)} {content_type} items")
            return content_list

        except Exception as e:
            logger.error(f"Failed to list {content_type} content: {e}")
            raise

    async def list_all_content(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        List all content organized by type.

        Returns:
            Dictionary mapping content types to lists of content
        """
        client = await self._get_redis_client()

        try:
            # Get all registry keys
            pattern = f"{CONTENT_REGISTRY_KEY}:*"
            keys = await client.keys(pattern)

            content_by_type = {}

            for key in keys:
                key_str = key.decode()
                if key_str.startswith(f"{CONTENT_REGISTRY_KEY}:types:"):
                    continue  # Skip type index keys

                # Extract content type and name
                parts = key_str.replace(f"{CONTENT_REGISTRY_KEY}:", "").split(":", 1)
                if len(parts) == 2:
                    content_type, content_name = parts
                    content_info = await client.json().get(key, "$")
                    if content_info and content_info[0]:
                        if content_type not in content_by_type:
                            content_by_type[content_type] = []
                        content_by_type[content_type].append(content_info[0])

            logger.info(f"Listed content from {len(content_by_type)} types")
            return content_by_type

        except Exception as e:
            logger.error(f"Failed to list all content: {e}")
            raise

    async def add_to_processing_queue(
        self, content_type: str, content_name: str, action: str, priority: int = 0
    ) -> str:
        """
        Add content to the processing queue.

        Args:
            content_type: Type of content
            content_name: Name of the content
            action: Action to perform (add, update, remove, process)
            priority: Processing priority (lower = higher priority)

        Returns:
            Task ID
        """
        client = await self._get_redis_client()

        task_id = str(uuid4())
        task_info = {
            "task_id": task_id,
            "content_type": content_type,
            "content_name": content_name,
            "action": action,
            "status": "pending",
            "priority": priority,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "attempts": 0,
            "max_attempts": 3,
        }

        try:
            # Add to processing queue (sorted by priority and creation time)
            score = priority * 1000000 + datetime.now(timezone.utc).timestamp()
            await client.zadd(PROCESSING_QUEUE_KEY, {json.dumps(task_info): score})

            logger.info(
                f"Added task {task_id} to processing queue: {action} {content_type}/{content_name}"
            )
            return task_id

        except Exception as e:
            logger.error(f"Failed to add task to processing queue: {e}")
            raise

    async def get_next_processing_task(self) -> Optional[Dict[str, Any]]:
        """
        Get the next task from the processing queue.

        Returns:
            Task information dictionary or None if queue is empty
        """
        client = await self._get_redis_client()

        try:
            # Get task with highest priority (lowest score)
            tasks = await client.zrange(PROCESSING_QUEUE_KEY, 0, 0, withscores=True)

            if not tasks:
                return None

            task_json, score = tasks[0]
            task_info = json.loads(task_json)

            # Remove from queue
            await client.zrem(PROCESSING_QUEUE_KEY, task_json)

            logger.info(f"Retrieved task {task_info['task_id']} from processing queue")
            return task_info

        except Exception as e:
            logger.error(f"Failed to get next processing task: {e}")
            raise

    async def update_task_status(
        self, task_id: str, status: str, result: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update task status and store result.

        Args:
            task_id: ID of the task
            status: New status (processing, completed, failed)
            result: Optional result data

        Returns:
            True if successful
        """
        client = await self._get_redis_client()

        status_key = f"{CONTENT_STATUS_KEY}:{task_id}"

        status_info = {
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        if result:
            status_info["result"] = json.dumps(result)

        try:
            await client.json().set(status_key, "$", status_info)
            await client.expire(status_key, 86400)  # Expire after 24 hours

            logger.info(f"Updated task {task_id} status to {status}")
            return True

        except Exception as e:
            logger.error(f"Failed to update task {task_id} status: {e}")
            raise

    async def record_ingestion(
        self,
        content_type: str,
        content_name: str,
        s3_location: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Record a successful ingestion operation.

        Args:
            content_type: Type of content that was ingested
            content_name: Name of the content that was ingested
            s3_location: S3 location where content was stored
            metadata: Optional additional metadata about the ingestion

        Returns:
            True if successful
        """
        try:
            # Add to registry with ingestion metadata
            ingestion_metadata = {
                "ingestion_date": datetime.now(timezone.utc).isoformat(),
                "processing_status": "ingested",
                "vector_count": 0,  # Will be updated during processing
            }

            if metadata:
                ingestion_metadata.update(metadata)

            # Add to registry
            await self.add_content_to_registry(
                content_type=content_type,
                content_name=content_name,
                s3_location=s3_location,
                metadata=ingestion_metadata,
            )

            # Add to processing queue for further processing
            await self.add_to_processing_queue(
                content_type=content_type,
                content_name=content_name,
                action="process",
                priority=1,  # Normal priority for ingested content
            )

            logger.info(f"Recorded ingestion: {content_type}/{content_name}")
            return True

        except Exception as e:
            logger.error(
                f"Failed to record ingestion for {content_type}/{content_name}: {e}"
            )
            raise

    async def get_ledger_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the ledger state.

        Returns:
            Dictionary with ledger summary information
        """
        try:
            # Get content counts by type
            content_by_type = await self.list_all_content()
            type_counts = {
                content_type: len(content)
                for content_type, content in content_by_type.items()
            }

            # Get queue length
            client = await self._get_redis_client()
            queue_length = await client.zcard(PROCESSING_QUEUE_KEY)

            summary = {
                "total_content_items": sum(type_counts.values()),
                "content_by_type": type_counts,
                "processing_queue_length": queue_length,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

            return summary

        except Exception as e:
            logger.error(f"Failed to get ledger summary: {e}")
            raise


def get_content_ledger_manager() -> ContentLedgerManager:
    """Get content ledger manager instance."""
    return ContentLedgerManager()
