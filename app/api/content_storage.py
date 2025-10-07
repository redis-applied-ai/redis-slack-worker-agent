"""
Content storage manager for S3-based content operations.
Handles upload, download, listing, and deletion of content from S3.
"""

import asyncio
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)


class ContentStorageManager:
    """Manages content storage operations in S3 for the knowledge base."""

    def __init__(self, bucket_name: str = "applied-ai-agent"):
        self.bucket_name = bucket_name
        try:
            self.s3_client = boto3.client("s3")
            # Test connection by checking if bucket exists
            self.s3_client.head_bucket(Bucket=bucket_name)
            logger.info(f"Successfully connected to S3 bucket: {bucket_name}")
        except (ClientError, NoCredentialsError) as e:
            logger.error(f"Failed to connect to S3: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to S3: {e}")
            raise

    async def upload_content(
        self,
        content_type: str,
        content_name: str,
        file_path: Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Upload content to S3 with metadata.

        Args:
            content_type: Type of content (e.g., 'repo', 'notebook', 'blog')
            content_name: Name of the content
            file_path: Local path to the file to upload
            metadata: Optional metadata to store with the content

        Returns:
            S3 key where content was stored
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Generate S3 key
        s3_key = f"{content_type}/{content_name}"

        # Prepare metadata
        upload_metadata = {
            "content_type": content_type,
            "content_name": content_name,
            "uploaded_at": datetime.utcnow().isoformat(),
            "file_size": file_path.stat().st_size,
            "original_path": str(file_path),
        }

        if metadata:
            upload_metadata.update(metadata)

        try:
            # Upload file
            await asyncio.to_thread(
                self.s3_client.upload_file,
                str(file_path),
                self.bucket_name,
                s3_key,
                ExtraArgs={
                    "Metadata": {k: str(v) for k, v in upload_metadata.items()},
                    "ContentType": self._get_content_type(file_path),
                },
            )

            logger.info(f"Successfully uploaded {content_type}/{content_name} to S3")
            return f"s3://{self.bucket_name}/{s3_key}"

        except Exception as e:
            logger.error(f"Failed to upload {content_type}/{content_name}: {e}")
            raise

    async def download_content(self, content_type: str, content_name: str) -> Path:
        """
        Download content from S3 to local temp directory.

        Args:
            content_type: Type of content
            content_name: Name of the content

        Returns:
            Path to downloaded file in temp directory
        """
        s3_key = f"{content_type}/{content_name}"

        try:
            # Create temp directory
            temp_dir = Path(tempfile.mkdtemp(prefix=f"{content_type}_{content_name}_"))
            local_path = temp_dir / content_name

            # Download file
            await asyncio.to_thread(
                self.s3_client.download_file, self.bucket_name, s3_key, str(local_path)
            )

            logger.info(f"Successfully downloaded {s3_key} to {local_path}")
            return local_path

        except Exception as e:
            logger.error(f"Failed to download {s3_key}: {e}")
            raise

    async def list_content(
        self, content_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List all content of a specific type or all content.

        Args:
            content_type: Optional content type filter

        Returns:
            List of content metadata dictionaries
        """
        try:
            if content_type:
                prefix = f"{content_type}/"
            else:
                prefix = ""

            response = await asyncio.to_thread(
                self.s3_client.list_objects_v2, Bucket=self.bucket_name, Prefix=prefix
            )

            content_list = []
            for obj in response.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):  # Skip directories
                    continue

                # Extract metadata
                try:
                    head_response = await asyncio.to_thread(
                        self.s3_client.head_object, Bucket=self.bucket_name, Key=key
                    )
                    metadata = head_response.get("Metadata", {})
                except Exception:
                    metadata = {}

                content_info = {
                    "s3_key": key,
                    "s3_location": f"s3://{self.bucket_name}/{key}",
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                    "metadata": metadata,
                }

                # Parse key to extract content type and name
                if "/" in key:
                    parts = key.split("/", 1)
                    content_info["content_type"] = parts[0]
                    content_info["content_name"] = parts[1]

                content_list.append(content_info)

            logger.info(f"Listed {len(content_list)} content items")
            return content_list

        except Exception as e:
            logger.error(f"Failed to list content: {e}")
            raise

    async def delete_content(self, content_type: str, content_name: str) -> bool:
        """
        Delete content from S3.

        Args:
            content_type: Type of content
            content_name: Name of the content

        Returns:
            True if deletion was successful
        """
        s3_key = f"{content_type}/{content_name}"

        try:
            await asyncio.to_thread(
                self.s3_client.delete_object, Bucket=self.bucket_name, Key=s3_key
            )

            logger.info(f"Successfully deleted {s3_key} from S3")
            return True

        except Exception as e:
            logger.error(f"Failed to delete {s3_key}: {e}")
            raise

    async def content_exists(self, content_type: str, content_name: str) -> bool:
        """
        Check if content exists in S3.

        Args:
            content_type: Type of content
            content_name: Name of the content

        Returns:
            True if content exists
        """
        s3_key = f"{content_type}/{content_name}"

        try:
            await asyncio.to_thread(
                self.s3_client.head_object, Bucket=self.bucket_name, Key=s3_key
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise
        except Exception as e:
            logger.error(f"Error checking if {s3_key} exists: {e}")
            raise

    async def upload_file(
        self,
        local_path: Path,
        s3_key: str,
        bucket: Optional[str] = None,
        region: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Upload a single file to S3.

        Args:
            local_path: Local path to the file
            s3_key: S3 key where to store the file
            bucket: Optional bucket name (defaults to instance bucket)
            region: Optional region (for cross-region uploads)
            metadata: Optional metadata to store with the file

        Returns:
            S3 location of uploaded file
        """
        if not local_path.exists():
            raise FileNotFoundError(f"File not found: {local_path}")

        target_bucket = bucket or self.bucket_name

        # Prepare metadata
        upload_metadata = {
            "uploaded_at": datetime.utcnow().isoformat(),
            "file_size": local_path.stat().st_size,
            "original_path": str(local_path),
        }

        if metadata:
            upload_metadata.update(metadata)

        try:
            # Use different client if different region
            if region and region != "us-east-1":  # Default region
                s3_client = boto3.client("s3", region_name=region)
            else:
                s3_client = self.s3_client

            # Upload file
            await asyncio.to_thread(
                s3_client.upload_file,
                str(local_path),
                target_bucket,
                s3_key,
                ExtraArgs={
                    "Metadata": {k: str(v) for k, v in upload_metadata.items()},
                    "ContentType": self._get_content_type(local_path),
                },
            )

            logger.info(
                f"Successfully uploaded {local_path} to s3://{target_bucket}/{s3_key}"
            )
            return f"s3://{target_bucket}/{s3_key}"

        except Exception as e:
            logger.error(
                f"Failed to upload {local_path} to s3://{target_bucket}/{s3_key}: {e}"
            )
            raise

    async def upload_directory(
        self,
        local_path: Path,
        s3_key: str,
        bucket: Optional[str] = None,
        region: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Upload an entire directory to S3.

        Args:
            local_path: Local path to the directory
            s3_key: S3 key prefix where to store the directory
            bucket: Optional bucket name (defaults to instance bucket)
            region: Optional region (for cross-region uploads)
            metadata: Optional metadata to store with files

        Returns:
            S3 location of uploaded directory
        """
        if not local_path.exists() or not local_path.is_dir():
            raise FileNotFoundError(f"Directory not found: {local_path}")

        target_bucket = bucket or self.bucket_name

        # Prepare metadata
        upload_metadata = {
            "uploaded_at": datetime.utcnow().isoformat(),
            "original_path": str(local_path),
        }

        if metadata:
            upload_metadata.update(metadata)

        try:
            # Use different client if different region
            if region and region != "us-east-1":  # Default region
                s3_client = boto3.client("s3", region_name=region)
            else:
                s3_client = self.s3_client

            uploaded_files = []

            # Walk through directory and upload files
            for file_path in local_path.rglob("*"):
                if file_path.is_file():
                    # Calculate relative path from local_path
                    relative_path = file_path.relative_to(local_path)
                    file_s3_key = f"{s3_key}/{relative_path}".replace("\\", "/")

                    # Upload individual file
                    await asyncio.to_thread(
                        s3_client.upload_file,
                        str(file_path),
                        target_bucket,
                        file_s3_key,
                        ExtraArgs={
                            "Metadata": {k: str(v) for k, v in upload_metadata.items()},
                            "ContentType": self._get_content_type(file_path),
                        },
                    )

                    uploaded_files.append(file_s3_key)

            logger.info(
                f"Successfully uploaded directory {local_path} to s3://{target_bucket}/{s3_key} ({len(uploaded_files)} files)"
            )
            return f"s3://{target_bucket}/{s3_key}"

        except Exception as e:
            logger.error(
                f"Failed to upload directory {local_path} to s3://{target_bucket}/{s3_key}: {e}"
            )
            raise

    def _get_content_type(self, file_path: Path) -> str:
        """Determine content type based on file extension."""
        suffix = file_path.suffix.lower()

        content_types = {
            ".html": "text/html",
            ".md": "text/markdown",
            ".txt": "text/plain",
            ".ipynb": "application/x-ipynb+json",
            ".py": "text/x-python",
            ".pdf": "application/pdf",
            ".json": "application/json",
            ".jsonl": "application/jsonl",
        }

        return content_types.get(suffix, "application/octet-stream")


def get_content_storage_manager(
    bucket_name: Optional[str] = None,
) -> Optional[ContentStorageManager]:
    """
    Get content storage manager if configured.

    Args:
        bucket_name: Optional custom bucket name

    Returns:
        ContentStorageManager instance or None if not configured
    """
    try:
        # Import here to avoid circular imports
        from app.api.content_config import content_settings

        bucket = bucket_name or content_settings.s3_bucket_name
        return ContentStorageManager(bucket)
    except Exception as e:
        logger.error(f"Failed to initialize ContentStorageManager: {e}")
        return None
