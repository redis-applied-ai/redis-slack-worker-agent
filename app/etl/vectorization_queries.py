"""
Vectorization queries and logic.

This module contains the DRY functions for querying the knowledge tracking index
and S3 to determine what content needs vectorization.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

import boto3

from app.utilities.database import get_redis_client
from app.utilities.s3_utils import S3_REGION, get_s3_bucket_name

logger = logging.getLogger(__name__)


async def query_content_for_vectorization() -> List[Dict[str, Any]]:
    """
    Query the knowledge tracking index for content that needs vectorization.

    Returns content with status "ingested" that is not archived.

    Returns:
        List of content records ready for vectorization
    """
    try:
        redis_client = get_redis_client()

        # Query for content with status "ingested" and not archived
        query = "@processing_status:{ingested} @archive:{false}"

        # Use Redis search to find matching records
        results = await redis_client.ft("knowledge_tracking").search(query)

        content_records = [json.loads(doc.__dict__["json"]) for doc in results.docs]

        logger.info(
            f"Found {len(content_records)} content items ready for vectorization"
        )
        return content_records

    except Exception as e:
        logger.error(f"Failed to query content for vectorization: {e}")
        return []


async def get_latest_date_folder(bucket_name: str, content_type: str) -> str:
    """
    Get the latest date folder for a given content type in S3.

    Args:
        bucket_name: S3 bucket name
        content_type: Type of content (repo, blog, notebook)

    Returns:
        Latest date folder (YYYY-MM-DD format)
    """
    try:
        s3_client = boto3.client("s3", region_name=S3_REGION)

        # Map content types to their correct S3 paths
        if content_type == "blog":
            prefix = "processed/blog_text/"
        elif content_type == "notebook":
            prefix = "processed/notebook_text/"
        else:
            prefix = f"processed/{content_type}/"

        response = s3_client.list_objects_v2(
            Bucket=bucket_name, Prefix=prefix, Delimiter="/"
        )

        # Extract date folders
        date_folders = []
        if "CommonPrefixes" in response:
            for obj in response["CommonPrefixes"]:
                folder_path = obj["Prefix"]
                # Extract date from path like "processed/repo/2025-09-05/"
                date_part = folder_path.split("/")[-2]
                if date_part and len(date_part) == 10:  # YYYY-MM-DD format
                    date_folders.append(date_part)

        if not date_folders:
            raise ValueError(f"No date folders found for {content_type}")

        # Sort dates and return the latest
        date_folders.sort(reverse=True)
        latest_date = date_folders[0]

        logger.info(f"Latest date folder for {content_type}: {latest_date}")
        return latest_date

    except Exception as e:
        logger.error(f"Failed to get latest date folder for {content_type}: {e}")
        raise


async def list_content_files_in_s3_folder(
    bucket_name: str, content_type: str, date_folder: str
) -> List[Dict[str, str]]:
    """
    List all content files in a specific S3 folder.
    For blogs, looks for .md files. For repos and notebooks, looks for .pdf files.

    Args:
        bucket_name: S3 bucket name
        content_type: Type of content (repo, blog, notebook)
        date_folder: Date folder (YYYY-MM-DD)

    Returns:
        List of content file information
    """
    try:
        s3_client = boto3.client("s3", region_name=S3_REGION)

        # Determine the correct prefix and file extension based on content type
        if content_type == "blog":
            prefix = f"processed/blog_text/{date_folder}/"
            file_extension = ".md"
        elif content_type == "notebook":
            prefix = f"processed/notebook_text/{date_folder}/"
            file_extension = ".md"
        else:
            prefix = f"processed/{content_type}/{date_folder}/"
            file_extension = ".pdf"

        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)

        content_files = []
        if "Contents" in response:
            for obj in response["Contents"]:
                key = obj["Key"]
                if key.endswith(file_extension):
                    # Extract filename from path
                    filename = Path(key).name
                    content_files.append(
                        {
                            "s3_key": key,
                            "filename": filename,
                            "content_type": content_type,
                            "date_folder": date_folder,
                        }
                    )

        logger.info(f"Found {len(content_files)} {file_extension} files in {prefix}")
        return content_files

    except Exception as e:
        logger.error(f"Failed to list files in {prefix}: {e}")
        raise


async def create_tracking_record_for_direct_upload(
    filename: str, content_type: str, s3_key: str, date_folder: str
) -> bool:
    """
    Create a tracking record for content that was directly uploaded to S3.

    Args:
        filename: Name of the file
        content_type: Type of content
        s3_key: S3 key where content is stored
        date_folder: Date folder from S3 path

    Returns:
        True if successful
    """
    try:
        from datetime import datetime, timezone

        redis_client = get_redis_client()
        current_date = datetime.now(timezone.utc)
        current_timestamp = int(current_date.timestamp())

        content_name = Path(filename).stem

        # Create tracking record for direct upload
        tracking_record = {
            "name": content_name,
            "content_type": content_type,
            "content_url": "direct_upload",
            "archive": "false",
            "source_date": date_folder,
            "update_date": current_date.strftime("%Y-%m-%d"),
            "updated_at": current_timestamp,
            "bucket_url": f"s3://{get_s3_bucket_name()}/{s3_key}",
            "processing_status": "ingested",  # Already in S3, ready for vectorization
            "last_processing_attempt": current_timestamp,
            "failure_reason": "",
            "retry_count": 0,
        }

        # Store in Redis
        key = f"knowledge_tracking:{content_name}"
        await redis_client.json().set(key, "$", tracking_record)

        logger.info(f"Created tracking record for direct upload: {filename}")
        return True

    except Exception as e:
        logger.error(f"Failed to create tracking record for {filename}: {e}")
        return False


async def scan_s3_for_direct_uploads() -> List[Dict[str, str]]:
    """
    Scan S3 bucket for content that doesn't have tracking records.
    Creates tracking records for direct uploads.

    Returns:
        List of file information for direct uploads
    """
    try:
        bucket_name = get_s3_bucket_name()
        content_files = []

        # Process each content type
        content_types = ["repo", "blog", "notebook"]

        for content_type in content_types:
            try:
                # Get latest date folder
                latest_date = await get_latest_date_folder(bucket_name, content_type)

                # List content files in the latest date folder
                files_in_folder = await list_content_files_in_s3_folder(
                    bucket_name, content_type, latest_date
                )

                for file_info in files_in_folder:
                    filename = file_info["filename"]
                    content_name = Path(filename).stem

                    # Check if tracking record exists
                    redis_client = get_redis_client()
                    key = f"knowledge_tracking:{content_name}"
                    existing_record = await redis_client.json().get(key)

                    if not existing_record:
                        # Create tracking record for direct upload
                        await create_tracking_record_for_direct_upload(
                            filename, content_type, file_info["s3_key"], latest_date
                        )
                        content_files.append(file_info)
                        logger.info(
                            f"Created tracking record for direct upload: {filename}"
                        )
                    else:
                        # Record exists, add to processing list if status is "ingested"
                        if existing_record.get("processing_status") == "ingested":
                            content_files.append(file_info)

            except Exception as e:
                logger.error(f"Failed to scan {content_type} for direct uploads: {e}")
                continue

        logger.info(f"Found {len(content_files)} files ready for vectorization")
        return content_files

    except Exception as e:
        logger.error(f"Failed to scan S3 for direct uploads: {e}")
        return []


def build_file_info_from_tracking_record(record: Dict[str, Any]) -> Dict[str, str]:
    """
    Build file information dictionary from tracking record.

    Args:
        record: Tracking record from Redis

    Returns:
        File information dictionary for vectorization processing
    """
    try:
        # Extract file information from tracking record
        bucket_url = record.get("bucket_url", "")
        if not bucket_url.startswith("s3://"):
            raise ValueError(f"Invalid bucket URL: {bucket_url}")

        # Parse S3 URL to get bucket and key
        s3_parts = bucket_url.replace("s3://", "").split("/", 1)
        if len(s3_parts) != 2:
            raise ValueError(f"Invalid S3 URL format: {bucket_url}")

        s3_bucket, s3_key = s3_parts
        filename = Path(s3_key).name
        content_type = record.get("content_type", "")

        # Create file info for processing
        file_info = {
            "s3_key": s3_key,
            "filename": filename,
            "content_type": content_type,
            "date_folder": record.get("source_date", ""),
        }

        return file_info

    except Exception as e:
        logger.error(f"Failed to build file info from record: {e}")
        raise


async def get_content_ready_for_vectorization() -> List[Dict[str, str]]:
    """
    Get all content ready for vectorization by combining tracking index query and S3 scan.

    This function:
    1. Scans S3 for direct uploads and creates tracking records
    2. Queries tracking index for content with status "ingested"
    3. Returns file information for all content ready for vectorization

    Returns:
        List of file information for content ready for vectorization
    """
    try:
        # Step 1: Scan S3 for direct uploads and create tracking records
        logger.info("Scanning S3 bucket for direct uploads...")
        direct_uploads = await scan_s3_for_direct_uploads()
        logger.info(f"Found {len(direct_uploads)} direct uploads")

        # Step 2: Query tracking index for content ready for vectorization
        logger.info(
            "Querying knowledge tracking index for content ready for vectorization..."
        )
        content_records = await query_content_for_vectorization()

        if not content_records:
            logger.info("No content found ready for vectorization")
            return []

        # Step 3: Convert tracking records to file information
        content_files = []
        for record in content_records:
            try:
                file_info = build_file_info_from_tracking_record(record)
                content_files.append(file_info)
            except Exception as e:
                logger.error(
                    f"Failed to process content record {record.get('name')}: {e}"
                )
                continue

        logger.info(f"Found {len(content_files)} content items ready for vectorization")
        return content_files

    except Exception as e:
        logger.error(f"Failed to get content ready for vectorization: {e}")
        return []
