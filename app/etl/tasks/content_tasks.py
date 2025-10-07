"""
Content management tasks for the applied-ai-agent.

This module contains all tasks related to content management, ingestion, and processing.
"""

import asyncio
import logging
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from docket import Docket, Retry

from app.api.content_ledger import get_content_ledger_manager
from app.api.content_storage import get_content_storage_manager
from app.utilities.environment import get_env_var

logger = logging.getLogger(__name__)


# Get REDIS_URL dynamically
def get_redis_url() -> str:
    return get_env_var("REDIS_URL", "redis://localhost:6379/0")


async def add_content_to_knowledge_base(
    content_type: str,
    content_name: str,
    s3_location: str,
    metadata: Optional[Dict[str, Any]] = None,
    retry: Retry = Retry(attempts=3, delay=timedelta(seconds=5)),
) -> Dict[str, Any]:
    """
    Add new content to the knowledge base.

    Args:
        content_type: Type of content (e.g., 'repo', 'notebook', 'blog')
        content_name: Name of the content
        s3_location: S3 location of the content
        metadata: Optional additional metadata
        retry: Retry configuration

    Returns:
        Dictionary with operation result
    """
    logger.info(f"Adding content to knowledge base: {content_type}/{content_name}")

    try:
        # Get managers
        storage_manager = get_content_storage_manager()
        ledger_manager = get_content_ledger_manager()

        if not storage_manager or not ledger_manager:
            raise RuntimeError("Failed to initialize storage or ledger managers")

        # Verify content exists in S3
        if not await storage_manager.content_exists(content_type, content_name):
            raise FileNotFoundError(f"Content not found in S3: {s3_location}")

        # Add to registry
        await ledger_manager.add_content_to_registry(
            content_type, content_name, s3_location, metadata
        )

        # Add to processing queue
        task_id = await ledger_manager.add_to_processing_queue(
            content_type, content_name, "process", priority=0
        )

        result = {
            "status": "success",
            "task_id": task_id,
            "content_type": content_type,
            "content_name": content_name,
            "s3_location": s3_location,
            "message": f"Content {content_type}/{content_name} added to knowledge base",
        }

        logger.info(f"Successfully added content: {content_type}/{content_name}")
        return result

    except Exception as e:
        logger.error(f"Failed to add content {content_type}/{content_name}: {e}")
        raise


async def update_content_in_knowledge_base(
    content_type: str,
    content_name: str,
    s3_location: str,
    metadata: Optional[Dict[str, Any]] = None,
    retry: Retry = Retry(attempts=3, delay=timedelta(seconds=5)),
) -> Dict[str, Any]:
    """
    Update existing content in the knowledge base.

    Args:
        content_type: Type of content
        content_name: Name of the content
        s3_location: New S3 location of the content
        metadata: Optional additional metadata
        retry: Retry configuration

    Returns:
        Dictionary with operation result
    """
    logger.info(f"Updating content in knowledge base: {content_type}/{content_name}")

    try:
        # Get managers
        storage_manager = get_content_storage_manager()
        ledger_manager = get_content_ledger_manager()

        if not storage_manager or not ledger_manager:
            raise RuntimeError("Failed to initialize storage or ledger managers")

        # Verify content exists in S3
        if not await storage_manager.content_exists(content_type, content_name):
            raise FileNotFoundError(f"Content not found in S3: {s3_location}")

        # Update registry
        updates = {
            "s3_location": s3_location,
            "processing_status": "pending",
        }

        if metadata:
            updates.update(metadata)

        await ledger_manager.update_content_in_registry(
            content_type, content_name, updates
        )

        # Add to processing queue
        task_id = await ledger_manager.add_to_processing_queue(
            content_type, content_name, "process", priority=1
        )

        result = {
            "status": "success",
            "task_id": task_id,
            "content_type": content_type,
            "content_name": content_name,
            "s3_location": s3_location,
            "message": f"Content {content_type}/{content_name} updated in knowledge base",
        }

        logger.info(f"Successfully updated content: {content_type}/{content_name}")
        return result

    except Exception as e:
        logger.error(f"Failed to update content {content_type}/{content_name}: {e}")
        raise


async def remove_content_from_knowledge_base(
    content_type: str,
    content_name: str,
    retry: Retry = Retry(attempts=3, delay=timedelta(seconds=5)),
) -> Dict[str, Any]:
    """
    Remove content from the knowledge base.

    Args:
        content_type: Type of content
        content_name: Name of the content
        retry: Retry configuration

    Returns:
        Dictionary with operation result
    """
    logger.info(f"Removing content from knowledge base: {content_type}/{content_name}")

    try:
        # Get managers
        ledger_manager = get_content_ledger_manager()

        if not ledger_manager:
            raise RuntimeError("Failed to initialize ledger manager")

        # Remove from registry
        await ledger_manager.remove_content_from_registry(content_type, content_name)

        # NOTE: Vector removal from Redis index is handled by the
        # vector database cleanup pipeline in a separate process

        result = {
            "status": "success",
            "content_type": content_type,
            "content_name": content_name,
            "message": f"Content {content_type}/{content_name} removed from knowledge base",
        }

        logger.info(f"Successfully removed content: {content_type}/{content_name}")
        return result

    except Exception as e:
        logger.error(f"Failed to remove content {content_type}/{content_name}: {e}")
        raise


async def process_content_pipeline(
    content_type: str,
    content_name: str,
    s3_location: str,
    retry: Retry = Retry(attempts=3, delay=timedelta(seconds=10)),
) -> Dict[str, Any]:
    """
    Process content through the complete pipeline.

    Args:
        content_type: Type of content
        content_name: Name of the content
        s3_location: S3 location of the content
        retry: Retry configuration

    Returns:
        Dictionary with operation result
    """
    logger.info(f"Processing content pipeline: {content_type}/{content_name}")

    try:
        # Get managers
        storage_manager = get_content_storage_manager()
        ledger_manager = get_content_ledger_manager()

        if not storage_manager or not ledger_manager:
            raise RuntimeError("Failed to initialize storage or ledger managers")

        # Update status to processing
        await ledger_manager.update_content_in_registry(
            content_type, content_name, {"processing_status": "processing"}
        )

        # Download content from S3
        local_path = await storage_manager.download_content(content_type, content_name)

        try:
            # NOTE: Content processing logic will be integrated with the existing
            # process_artifacts pipeline in a future iteration.
            # For now, we mark content as completed after download.

            # Update status to completed
            await ledger_manager.update_content_in_registry(
                content_type,
                content_name,
                {
                    "processing_status": "completed",
                    "vector_count": 0,  # NOTE: Vector count will be populated by vectorization pipeline
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                },
            )

            result = {
                "status": "success",
                "content_type": content_type,
                "content_name": content_name,
                "s3_location": s3_location,
                "message": f"Content {content_type}/{content_name} processed successfully",
            }

            logger.info(
                f"Successfully processed content: {content_type}/{content_name}"
            )
            return result

        finally:
            # Clean up local file
            try:
                local_path.unlink()
                local_path.parent.rmdir()
            except Exception as e:
                logger.warning(f"Failed to clean up local file {local_path}: {e}")

    except Exception as e:
        logger.error(f"Failed to process content {content_type}/{content_name}: {e}")

        # Update status to failed
        try:
            await ledger_manager.update_content_in_registry(
                content_type,
                content_name,
                {"processing_status": "failed", "error": str(e)},
            )
        except Exception as update_error:
            logger.error(f"Failed to update status to failed: {update_error}")

        raise


async def trigger_ingestion_pipeline(
    content_types: Optional[List[str]] = None,
    force_refresh: bool = False,
    max_concurrent: int = 5,
) -> Dict[str, Any]:
    """
    Trigger the ingestion pipeline to download and upload content.
    Returns immediately with task ID and processes in background.

    Args:
        content_types: List of content types to process (None for all)
        force_refresh: Whether to force refresh existing content
        max_concurrent: Maximum concurrent processing tasks

    Returns:
        Dictionary with task ID and immediate acknowledgment
    """
    import uuid
    from datetime import datetime, timezone

    # Generate a unique task ID
    task_id = str(uuid.uuid4())
    ingestion_date = datetime.now(timezone.utc).isoformat()

    logger.info(f"Triggering ingestion pipeline with task ID: {task_id}")

    # Return immediate acknowledgment
    acknowledgment = {
        "task_id": task_id,
        "status": "accepted",
        "ingestion_date": ingestion_date,
        "content_types": content_types or ["repos", "notebooks", "blog"],
        "message": "Ingestion pipeline queued for background processing",
    }

    # Queue the actual work for background processing
    # This will be handled by Docket workers - don't await it!
    import threading

    def run_background_task():
        """Run the background task in a separate thread to avoid blocking"""
        loop = None
        try:
            # Import here to avoid circular imports

            from app.etl.tasks.ingestion import run_ingestion_pipeline

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(run_ingestion_pipeline())
        except Exception as e:
            logger.error(f"Background ingestion task failed: {e}")
        finally:
            if loop:
                loop.close()

    # Start background task in a separate thread
    thread = threading.Thread(target=run_background_task, daemon=True)
    thread.start()

    return acknowledgment


async def run_ingestion_pipeline_background(
    task_id: str,
    content_types: Optional[List[str]] = None,
    force_refresh: bool = False,
    max_concurrent: int = 5,
) -> Dict[str, Any]:
    """
    Background task to run the ingestion pipeline.

    Args:
        task_id: Unique task identifier
        content_types: List of content types to process (None for all)
        force_refresh: Whether to force refresh existing content
        max_concurrent: Maximum concurrent processing tasks

    Returns:
        Dictionary with pipeline results
    """
    logger.info(f"Starting background ingestion pipeline for task ID: {task_id}")

    try:
        from app.etl.tasks.ingestion import run_ingestion_pipeline

        result = await run_ingestion_pipeline()

        # Add task ID to result
        result["task_id"] = task_id
        result["status"] = "completed"

        logger.info(
            f"Ingestion pipeline completed for task {task_id} with status: {result.get('status')}"
        )

        # Store the result in Redis for later retrieval
        ledger_manager = get_content_ledger_manager()
        await ledger_manager.record_ingestion(
            content_type="pipeline_result",
            content_name=f"task_{task_id}",
            s3_location="",  # No S3 location for task results
            metadata=result,
        )

        return result

    except Exception as e:
        logger.error(f"Ingestion pipeline failed for task {task_id}: {e}")

        # Store error result
        error_result = {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
            "content_types": content_types or ["repos", "notebooks", "blog"],
        }

        ledger_manager = get_content_ledger_manager()
        await ledger_manager.record_ingestion(
            content_type="pipeline_result",
            content_name=f"task_{task_id}",
            s3_location="",
            metadata=error_result,
        )

        raise


async def trigger_artifact_processing_pipeline(
    content_types: Optional[List[str]] = None,
    max_concurrent: int = 5,
) -> Dict[str, Any]:
    """
    Trigger the artifact processing pipeline to transform raw S3 content to processed content.
    Returns immediately with task ID and processes in background.

    Args:
        content_types: List of content types to process (None for all)
        max_concurrent: Maximum concurrent processing tasks

    Returns:
        Dictionary with task ID and immediate acknowledgment
    """
    import uuid
    from datetime import datetime, timezone

    # Generate a unique task ID
    task_id = str(uuid.uuid4())
    processing_date = datetime.now(timezone.utc).isoformat()

    logger.info(f"Triggering artifact processing pipeline with task ID: {task_id}")

    # Return immediate acknowledgment
    acknowledgment = {
        "task_id": task_id,
        "status": "accepted",
        "processing_date": processing_date,
        "content_types": content_types
        or ["repos", "notebooks", "blog", "slides", "redis_docs"],
        "message": "Artifact processing pipeline queued for background processing",
    }

    # Use Docket to queue the processing task
    async with Docket(url=get_redis_url()) as docket:
        await docket.add(
            run_artifact_processing_pipeline, key=f"artifact_processing_{task_id}"
        )(
            content_types=content_types,
            max_concurrent=max_concurrent,
        )

    return acknowledgment


async def run_artifact_processing_pipeline_background(
    task_id: str,
    content_types: Optional[List[str]] = None,
    max_concurrent: int = 5,
) -> Dict[str, Any]:
    """
    Background task to run the artifact processing pipeline.

    Args:
        task_id: Unique task identifier
        content_types: List of content types to process (None for all)
        max_concurrent: Maximum concurrent processing tasks

    Returns:
        Dictionary with pipeline results
    """
    logger.info(
        f"Starting background artifact processing pipeline for task ID: {task_id}"
    )

    try:
        result = await run_artifact_processing_pipeline(
            content_types=content_types,
            max_concurrent=max_concurrent,
        )

        # Add task ID to result
        result["task_id"] = task_id
        result["status"] = "completed"

        logger.info(
            f"Artifact processing pipeline completed for task {task_id} with status: {result.get('status')}"
        )

        # Store the result in Redis for later retrieval
        ledger_manager = get_content_ledger_manager()
        await ledger_manager.record_ingestion(
            content_type="pipeline_result",
            content_name=f"processing_task_{task_id}",
            s3_location="",  # No S3 location for task results
            metadata=result,
        )

        return result

    except Exception as e:
        logger.error(f"Artifact processing pipeline failed for task {task_id}: {e}")

        # Store error result
        error_result = {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
            "content_types": content_types
            or ["repos", "notebooks", "blog", "slides", "redis_docs"],
        }

        ledger_manager = get_content_ledger_manager()
        await ledger_manager.record_ingestion(
            content_type="pipeline_result",
            content_name=f"processing_task_{task_id}",
            s3_location="",
            metadata=error_result,
        )

        raise


async def run_artifact_processing_pipeline(
    content_types: Optional[List[str]] = None,
    max_concurrent: int = 5,
) -> Dict[str, Any]:
    """
    Run the artifact processing pipeline using S3-aware processing logic.
    Downloads raw content from S3, processes it, and uploads to processed folder.

    Args:
        content_types: List of content types to process (None for all)
        max_concurrent: Maximum concurrent processing tasks

    Returns:
        Dictionary with pipeline results
    """
    logger.info("Starting S3-aware artifact processing pipeline")

    if content_types is None:
        content_types = ["repos", "notebooks", "blog", "slides", "redis_docs"]

    results = {
        "status": "success",
        "content_types": content_types,
        "processing_date": datetime.now(timezone.utc).isoformat(),
        "results": {},
        "total_files_processed": 0,
    }

    try:
        # Get storage manager
        storage_manager = get_content_storage_manager()
        if not storage_manager:
            raise RuntimeError("Failed to initialize storage manager")

        # Debug: List all content to see what's actually in S3
        all_content = await storage_manager.list_content()
        logger.info(f"Found {len(all_content)} total content items in S3")

        # Log the actual content types and names for debugging
        content_by_type = {}
        for item in all_content:
            content_type = item.get("content_type", "unknown")
            if content_type not in content_by_type:
                content_by_type[content_type] = []
            content_by_type[content_type].append(item.get("content_name", "unknown"))

        for ctype, names in content_by_type.items():
            logger.info(
                f"Content type '{ctype}': {len(names)} items - {names[:5]}{'...' if len(names) > 5 else ''}"
            )

        # Process each content type
        for content_type in content_types:
            logger.info(f"Processing content type: {content_type}")

            try:
                if content_type == "blog":
                    processed_count = await process_blog_posts_s3(
                        storage_manager, all_content
                    )
                elif content_type == "notebooks":
                    processed_count = await process_notebooks_s3(
                        storage_manager, all_content
                    )
                elif content_type == "slides":
                    processed_count = await process_slides_s3(
                        storage_manager, all_content
                    )
                elif content_type == "repos":
                    processed_count = await process_repos_s3(
                        storage_manager, all_content
                    )
                elif content_type == "redis_docs":
                    processed_count = await process_redis_docs_s3(
                        storage_manager, all_content
                    )
                else:
                    logger.warning(f"Unknown content type: {content_type}")
                    continue

                results["results"][content_type] = processed_count
                results["total_files_processed"] += processed_count
                logger.info(f"Processed {processed_count} {content_type} files")

            except Exception as e:
                logger.error(f"Failed to process {content_type}: {e}")
                results["results"][content_type] = {"error": str(e)}

        logger.info(
            f"Artifact processing completed: {results['total_files_processed']} files processed"
        )
        return results

    except Exception as e:
        logger.error(f"Artifact processing pipeline failed: {e}")
        results["status"] = "failed"
        results["error"] = str(e)
        raise


# Content processing functions for different types


async def process_blog_posts_s3(
    storage_manager, all_content: List[Dict[str, Any]]
) -> int:
    """Process blog posts from S3 raw to processed format."""
    logger.info("Processing blog posts from S3")

    try:
        # List files directly from S3 raw/blogs/ folder
        response = await asyncio.to_thread(
            storage_manager.s3_client.list_objects_v2,
            Bucket=storage_manager.bucket_name,
            Prefix="raw/blogs/",
        )

        raw_blog_files = [
            obj for obj in response.get("Contents", []) if obj["Key"].endswith(".html")
        ]

        logger.info(f"Found {len(raw_blog_files)} blog files to process")

        processed_count = 0

        for obj in raw_blog_files:
            try:
                s3_key = obj["Key"]  # e.g., "raw/blogs/filename.html"
                filename = Path(s3_key).name  # e.g., "filename.html"

                # Download from raw/
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
                temp_path = Path(temp_file.name)
                temp_file.close()

                await asyncio.to_thread(
                    storage_manager.s3_client.download_file,
                    storage_manager.bucket_name,
                    s3_key,
                    str(temp_path),
                )

                # Process HTML to Markdown
                processed_content = await convert_html_to_markdown(temp_path)

                # Upload to processed/ with .md extension
                processed_filename = filename.replace(".html", ".md")
                processed_s3_key = f"processed/blog/{processed_filename}"

                # Write processed content to temp file
                processed_temp = tempfile.NamedTemporaryFile(
                    delete=False, suffix=".md", mode="w", encoding="utf-8"
                )
                processed_temp.write(processed_content)
                processed_temp.close()

                await asyncio.to_thread(
                    storage_manager.s3_client.upload_file,
                    processed_temp.name,
                    storage_manager.bucket_name,
                    processed_s3_key,
                )

                processed_count += 1
                logger.info(f"Processed blog post: {filename} -> {processed_filename}")

                # Clean up
                temp_path.unlink()
                Path(processed_temp.name).unlink()

            except Exception as e:
                logger.error(f"Failed to process blog post {filename}: {e}")
                continue

        return processed_count

    except Exception as e:
        logger.error(f"Failed to process blog posts: {e}")
        return 0


async def process_notebooks_s3(
    storage_manager, all_content: List[Dict[str, Any]]
) -> int:
    """Process notebooks from S3 raw to processed format."""
    logger.info("Processing notebooks from S3")

    try:
        # List files directly from S3 raw/notebooks/ folder
        response = await asyncio.to_thread(
            storage_manager.s3_client.list_objects_v2,
            Bucket=storage_manager.bucket_name,
            Prefix="raw/notebooks/",
        )

        raw_notebook_files = [
            obj for obj in response.get("Contents", []) if obj["Key"].endswith(".ipynb")
        ]

        logger.info(f"Found {len(raw_notebook_files)} notebook files to process")

        processed_count = 0

        for obj in raw_notebook_files:
            try:
                s3_key = obj["Key"]  # e.g., "raw/notebooks/filename.ipynb"
                filename = Path(s3_key).name  # e.g., "filename.ipynb"

                # Download from raw/
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".ipynb")
                temp_path = Path(temp_file.name)
                temp_file.close()

                await asyncio.to_thread(
                    storage_manager.s3_client.download_file,
                    storage_manager.bucket_name,
                    s3_key,
                    str(temp_path),
                )

                # Process (just copy for now)
                with open(temp_path, "rb") as f:
                    f.read()  # Read but don't store since we're just copying

                # Upload to processed/ with same filename
                processed_s3_key = f"processed/notebooks/{filename}"
                await asyncio.to_thread(
                    storage_manager.s3_client.upload_file,
                    str(temp_path),
                    storage_manager.bucket_name,
                    processed_s3_key,
                )

                processed_count += 1
                logger.info(f"Processed notebook: {filename}")

                # Clean up
                temp_path.unlink()

            except Exception as e:
                logger.error(f"Failed to process notebook {filename}: {e}")
                continue

        logger.info(
            f"Processed {processed_count}/{len(raw_notebook_files)} notebook files"
        )
        return processed_count

    except Exception as e:
        logger.error(f"Failed to process notebooks: {e}")
        return 0


async def process_slides_s3(storage_manager, all_content: List[Dict[str, Any]]) -> int:
    """Process slides/PDFs from S3 raw to processed format."""
    logger.info("Processing slides from S3")

    try:
        # List files directly from S3 raw/slides/ folder
        response = await asyncio.to_thread(
            storage_manager.s3_client.list_objects_v2,
            Bucket=storage_manager.bucket_name,
            Prefix="raw/slides/",
        )

        raw_slide_files = [
            obj
            for obj in response.get("Contents", [])
            if obj["Key"].endswith(".pdf") or obj["Key"].endswith(".pptx")
        ]

        logger.info(f"Found {len(raw_slide_files)} slide files to process")

        processed_count = 0

        for obj in raw_slide_files:
            try:
                s3_key = obj["Key"]  # e.g., "raw/slides/filename.pdf"
                filename = Path(s3_key).name  # e.g., "filename.pdf"

                # Download from raw/
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                temp_path = Path(temp_file.name)
                temp_file.close()

                await asyncio.to_thread(
                    storage_manager.s3_client.download_file,
                    storage_manager.bucket_name,
                    s3_key,
                    str(temp_path),
                )

                # Extract text from PDF
                processed_content = await extract_pdf_text(temp_path)

                # Upload to processed/ with .txt extension
                processed_filename = filename.replace(".pdf", ".txt").replace(
                    ".pptx", ".txt"
                )
                processed_s3_key = f"processed/slides/{processed_filename}"

                # Write processed content to temp file
                processed_temp = tempfile.NamedTemporaryFile(
                    delete=False, suffix=".txt", mode="w", encoding="utf-8"
                )
                processed_temp.write(processed_content)
                processed_temp.close()

                await asyncio.to_thread(
                    storage_manager.s3_client.upload_file,
                    processed_temp.name,
                    storage_manager.bucket_name,
                    processed_s3_key,
                )

                processed_count += 1
                logger.info(f"Processed slide: {filename} -> {processed_filename}")

                # Clean up
                temp_path.unlink()
                Path(processed_temp.name).unlink()

            except Exception as e:
                logger.error(f"Failed to process slide {filename}: {e}")
                continue

        return processed_count

    except Exception as e:
        logger.error(f"Failed to process slides: {e}")
        return 0


async def process_repos_s3(storage_manager, all_content: List[Dict[str, Any]]) -> int:
    """Process repositories from S3 raw to processed format."""
    logger.info("Processing repositories from S3")

    try:
        # Filter for raw repo files (content_type is "raw" and path contains "repos/")
        raw_repo_files = [
            item
            for item in all_content
            if item.get("content_type") == "raw"
            and "repos/" in item.get("content_name", "")
            and item.get("content_name", "").endswith(".zip")
        ]

        logger.info(f"Found {len(raw_repo_files)} repo files to process")

        processed_count = 0

        for file_info in raw_repo_files:
            try:
                content_name = file_info["content_name"]

                # Download raw repo (zip file)
                # Download raw repo file (content is stored as "raw/repos/filename.zip")
                local_path = await storage_manager.download_content("raw", content_name)

                # Convert repo to PDF (simplified - just copy for now)
                with open(local_path, "rb") as f:
                    processed_content = f.read()

                # Upload processed content to S3
                # Extract just the filename from the path (e.g., "repos/filename.zip" -> "filename.pdf")
                filename = Path(content_name).name
                processed_filename = filename.replace(".zip", ".pdf")
                processed_path = local_path.parent / processed_filename

                # Write processed content to temp file
                with open(processed_path, "wb") as f:
                    f.write(processed_content)

                # Upload to processed folder
                s3_key = f"processed/repos/{processed_filename}"
                await asyncio.to_thread(
                    storage_manager.s3_client.upload_file,
                    str(processed_path),
                    storage_manager.bucket_name,
                    s3_key,
                )

                processed_count += 1
                logger.info(f"Processed repo: {content_name} -> {processed_filename}")

                # Clean up local files
                local_path.unlink()
                processed_path.unlink()

            except Exception as e:
                logger.error(
                    f"Failed to process repo {file_info.get('content_name', 'unknown')}: {e}"
                )
                continue

        return processed_count

    except Exception as e:
        logger.error(f"Failed to process repositories: {e}")
        return 0


async def process_redis_docs_s3(
    storage_manager, all_content: List[Dict[str, Any]]
) -> int:
    """Process Redis docs from S3 raw to processed format."""
    logger.info("Processing Redis docs from S3")

    try:
        # Filter for raw Redis doc files (content_type is "raw" and path contains "redis_docs/")
        raw_redis_doc_files = [
            item
            for item in all_content
            if item.get("content_type") == "raw"
            and "redis_docs/" in item.get("content_name", "")
            and item.get("content_name", "").endswith(".html")
        ]

        logger.info(f"Found {len(raw_redis_doc_files)} Redis doc files to process")

        processed_count = 0

        for file_info in raw_redis_doc_files:
            try:
                content_name = file_info["content_name"]

                # Download raw HTML file (content is stored as "raw/redis_docs/filename.html")
                local_path = await storage_manager.download_content("raw", content_name)

                # Convert HTML to text
                processed_content = await convert_html_to_text(local_path)

                # Upload processed content to S3
                # Extract just the filename from the path (e.g., "redis_docs/filename.html" -> "filename.txt")
                filename = Path(content_name).name
                processed_filename = filename.replace(".html", ".txt")
                processed_path = local_path.parent / processed_filename

                # Write processed content to temp file
                with open(processed_path, "w", encoding="utf-8") as f:
                    f.write(processed_content)

                # Upload to processed folder
                s3_key = f"processed/redis_docs/{processed_filename}"
                await asyncio.to_thread(
                    storage_manager.s3_client.upload_file,
                    str(processed_path),
                    storage_manager.bucket_name,
                    s3_key,
                )

                processed_count += 1
                logger.info(
                    f"Processed Redis doc: {content_name} -> {processed_filename}"
                )

                # Clean up local files
                local_path.unlink()
                processed_path.unlink()

            except Exception as e:
                logger.error(
                    f"Failed to process Redis doc {file_info.get('content_name', 'unknown')}: {e}"
                )
                continue

        return processed_count

    except Exception as e:
        logger.error(f"Failed to process Redis docs: {e}")
        return 0


# Helper functions for content processing


async def convert_html_to_markdown(html_path: Path) -> str:
    """Convert HTML file to Markdown format."""
    try:
        from bs4 import BeautifulSoup
        from markdownify import markdownify

        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Parse HTML
        soup = BeautifulSoup(html_content, "html.parser")

        # Extract main content
        content_selectors = [
            "article",
            ".post-content",
            ".entry-content",
            ".content",
            "main",
            ".blog-post",
        ]

        main_content = None
        for selector in content_selectors:
            main_content = soup.select_one(selector)
            if main_content:
                break

        if not main_content:
            main_content = soup.find("body")

        if main_content:
            # Convert to markdown
            markdown_content = markdownify(
                str(main_content), heading_style="ATX", bullets="-"
            )

            # Clean up the markdown
            lines = [line.strip() for line in markdown_content.split("\n")]
            cleaned_lines = []

            for line in lines:
                if line or (cleaned_lines and cleaned_lines[-1]):
                    cleaned_lines.append(line)

            return "\n".join(cleaned_lines)

        return ""

    except Exception as e:
        logger.error(f"Failed to convert HTML to Markdown: {e}")
        return ""


async def extract_pdf_text(pdf_path: Path) -> str:
    """Extract text from PDF file."""
    try:
        from PyPDF2 import PdfReader

        with open(pdf_path, "rb") as f:
            reader = PdfReader(f)
            text_content = []

            for page_num, page in enumerate(reader.pages):
                try:
                    text = page.extract_text()
                    if text.strip():
                        text_content.append(f"Page {page_num + 1}:\n{text}\n")
                except Exception as e:
                    logger.warning(f"Error extracting page {page_num + 1}: {e}")
                    continue

            return "\n".join(text_content)

    except Exception as e:
        logger.error(f"Failed to extract PDF text: {e}")
        return ""


async def convert_html_to_text(html_path: Path) -> str:
    """Convert HTML file to plain text."""
    try:
        from bs4 import BeautifulSoup

        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        soup = BeautifulSoup(html_content, "html.parser")

        # Remove script/style tags
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator="\n")
        # Collapse multiple blank lines
        lines = [line.strip() for line in text.splitlines()]
        text_clean = "\n".join([line for line in lines if line])

        return text_clean

    except Exception as e:
        logger.error(f"Failed to convert HTML to text: {e}")
        return ""
