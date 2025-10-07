"""
ETL Vectorization Tasks

This module provides Docket tasks for content vectorization, including:
- PDF text extraction and chunking
- Markdown text extraction and chunking
- Vector embedding generation
- RAG index storage
- Knowledge tracking updates

All tasks are designed to be run asynchronously via Docket workers.
"""

import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import boto3
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader

from app.utilities.database import (
    get_document_index,
    get_vectorizer,
)
from app.utilities.s3_utils import S3_REGION, get_s3_bucket_name

logger = logging.getLogger(__name__)

# Text processing configuration
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


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

        # List all date folders for this content type
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


async def list_content_files_in_folder(
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


async def download_pdf_from_s3(bucket_name: str, s3_key: str) -> Path:
    """
    Download a PDF file from S3 to a temporary location.

    Args:
        bucket_name: S3 bucket name
        s3_key: S3 object key

    Returns:
        Path to downloaded PDF file
    """
    try:
        s3_client = boto3.client("s3", region_name=S3_REGION)

        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        temp_path = Path(temp_file.name)
        temp_file.close()

        # Download file
        s3_client.download_file(bucket_name, s3_key, str(temp_path))

        logger.info(f"Downloaded {s3_key} to {temp_path}")
        return temp_path

    except Exception as e:
        logger.error(f"Failed to download {s3_key}: {e}")
        raise


async def download_file_from_s3(bucket_name: str, s3_key: str) -> Path:
    """
    Download a file from S3 to a temporary location.

    Args:
        bucket_name: S3 bucket name
        s3_key: S3 object key

    Returns:
        Path to the downloaded file
    """
    try:
        s3_client = boto3.client("s3", region_name=S3_REGION)

        # Determine file extension from S3 key
        file_extension = Path(s3_key).suffix
        if not file_extension:
            file_extension = ".txt"  # Default fallback

        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
        temp_path = Path(temp_file.name)
        temp_file.close()

        # Download from S3
        s3_client.download_file(bucket_name, s3_key, str(temp_path))

        logger.info(f"Downloaded {s3_key} to {temp_path}")
        return temp_path

    except Exception as e:
        logger.error(f"Failed to download {s3_key}: {e}")
        raise


async def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    Extract text content from a PDF file.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Extracted text content
    """
    try:
        loader = PyPDFLoader(str(pdf_path))
        documents = loader.load()

        # Combine all pages into single text
        text_content = "\n".join([doc.page_content for doc in documents])

        logger.info(f"Extracted {len(text_content)} characters from {pdf_path.name}")
        return text_content

    except Exception as e:
        logger.error(f"Failed to extract text from {pdf_path}: {e}")
        raise


async def extract_text_from_markdown(markdown_path: Path) -> str:
    """
    Extract text content from a markdown file.

    Args:
        markdown_path: Path to the markdown file

    Returns:
        Extracted text content
    """
    try:
        with open(markdown_path, "r", encoding="utf-8") as f:
            text_content = f.read()

        logger.info(
            f"Extracted {len(text_content)} characters from {markdown_path.name}"
        )
        return text_content

    except Exception as e:
        logger.error(f"Failed to extract text from {markdown_path}: {e}")
        raise


async def chunk_text(
    text: str, chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP
) -> List[str]:
    """
    Split text into chunks for vectorization.

    Args:
        text: Text content to chunk
        chunk_size: Size of each chunk
        chunk_overlap: Overlap between chunks

    Returns:
        List of text chunks
    """
    try:
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )

        # Create a simple document for splitting
        from langchain.schema import Document

        document = Document(page_content=text)
        chunks = text_splitter.split_documents([document])

        chunk_texts = [chunk.page_content for chunk in chunks]

        logger.info(f"Created {len(chunk_texts)} chunks from text")
        return chunk_texts

    except Exception as e:
        logger.error(f"Failed to chunk text: {e}")
        raise


async def vectorize_and_store_chunks(
    chunks: List[str], filename: str, content_type: str, date_folder: str
) -> int:
    """
    Vectorize text chunks and store them in the RAG index.

    Args:
        chunks: List of text chunks
        filename: Original filename
        content_type: Type of content (repo, blog, notebook)
        date_folder: Date folder

    Returns:
        Number of chunks stored
    """
    try:
        # Get database components
        vectorizer = get_vectorizer()
        document_index = get_document_index()

        # Map content types to RAG index types
        type_mapping = {
            "repo": "repository_pdf",
            "blog": "blog_post",
            "notebook": "recipe_notebook",
        }

        rag_type = type_mapping.get(content_type, content_type)

        # Get current timestamp for tracking
        current_timestamp = datetime.now(timezone.utc).timestamp()
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Prepare data for Redis
        data_batch = []
        keys_batch = []

        for i, chunk_text in enumerate(chunks):
            try:
                # Generate embedding
                embedding = vectorizer.embed(chunk_text, as_buffer=True)

                # Create unique key for this chunk
                file_stem = Path(filename).stem
                chunk_key = f"rag_doc:{rag_type}:{file_stem}_chunk_{i}"

                # Prepare data for Redis with timestamp fields
                chunk_data = {
                    "name": f"{file_stem}_chunk_{i}",
                    "description": chunk_text,
                    "source_file": filename,
                    "type": rag_type,
                    "vector": embedding,
                    "chunk_index": i,
                    "start_index": i * CHUNK_SIZE,  # Approximate start index
                    "source_date": date_folder,  # Date when content was originally created
                    "update_date": current_date,  # Date when this chunk was processed
                    "updated_at": current_timestamp,  # Timestamp when this chunk was processed
                }

                data_batch.append(chunk_data)
                keys_batch.append(chunk_key)

            except Exception as e:
                logger.error(f"Error processing chunk {i} from {filename}: {e}")
                continue

        # Store all chunks in batch
        if data_batch:
            await document_index.load(data=data_batch, keys=keys_batch)
            logger.info(f"Successfully stored {len(data_batch)} chunks for {filename}")
            return len(data_batch)
        else:
            logger.warning(f"No chunks to store for {filename}")
            return 0

    except Exception as e:
        logger.error(f"Failed to vectorize and store chunks for {filename}: {e}")
        raise


async def update_tracking_index_status(
    content_name: str, status: str, failure_reason: str = None
) -> bool:
    """
    Update the tracking index with processing status.

    Args:
        content_name: Name of the content
        status: New processing status
        failure_reason: Error message if status is "failed"

    Returns:
        True if successful
    """
    try:
        from app.utilities.database import get_redis_client

        redis_client = get_redis_client()
        current_timestamp = int(datetime.now(timezone.utc).timestamp())

        # Get existing record
        key = f"knowledge_tracking:{content_name}"
        existing_record = await redis_client.json().get(key)

        if existing_record:
            # Update existing record
            existing_record["processing_status"] = status
            existing_record["last_processing_attempt"] = current_timestamp
            existing_record["updated_ts"] = current_timestamp

            if status == "failed" and failure_reason:
                existing_record["failure_reason"] = failure_reason
                existing_record["retry_count"] = (
                    existing_record.get("retry_count", 0) + 1
                )
            elif status == "completed":
                existing_record["failure_reason"] = ""
                existing_record["retry_count"] = 0

            await redis_client.json().set(key, "$", existing_record)
            logger.info(f"Updated tracking index for {content_name} - status: {status}")
        else:
            logger.warning(f"No tracking record found for {content_name}")
            return False

        return True

    except Exception as e:
        logger.error(f"Failed to update tracking index for {content_name}: {e}")
        return False


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
        from app.utilities.database import get_redis_client

        redis_client = get_redis_client()
        current_date = datetime.now(timezone.utc)
        current_timestamp = int(current_date.timestamp())

        content_name = Path(filename).stem

        # Create tracking record for direct upload
        tracking_record = {
            "name": content_name,
            "content_type": content_type,
            "content_url": "direct_upload",
            "archive": False,
            "source_date": date_folder,
            "updated_date": current_date.strftime("%Y-%m-%d"),
            "updated_ts": current_timestamp,
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


async def query_content_for_vectorization() -> List[Dict[str, Any]]:
    """
    Query the knowledge tracking index for content that needs vectorization.

    Returns content with status "ingested" that is not archived.

    Returns:
        List of content records ready for vectorization
    """
    try:
        from app.utilities.database import get_redis_client

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
                files_in_folder = await list_content_files_in_folder(
                    bucket_name, content_type, latest_date
                )

                for file_info in files_in_folder:
                    filename = file_info["filename"]
                    content_name = Path(filename).stem

                    # Check if tracking record exists
                    from app.utilities.database import get_redis_client

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


async def process_content_file(
    bucket_name: str, file_info: Dict[str, str]
) -> Dict[str, Any]:
    """
    Process a single content file: download, extract text, chunk, vectorize, and store.
    Handles both PDF and markdown files.

    Args:
        bucket_name: S3 bucket name
        file_info: File information

    Returns:
        Processing results
    """
    temp_path = None
    content_name = None
    try:
        s3_key = file_info["s3_key"]
        filename = file_info["filename"]
        content_type = file_info["content_type"]
        date_folder = file_info["date_folder"]
        content_name = Path(filename).stem

        logger.info(f"Processing {content_type} file: {filename}")

        # Step 1: Update tracking index to vectorize-pending
        await update_tracking_index_status(content_name, "vectorize-pending")

        # Step 2: Download file from S3
        temp_path = await download_file_from_s3(bucket_name, s3_key)

        # Step 3: Extract text based on file type
        if filename.endswith(".md"):
            text_content = await extract_text_from_markdown(temp_path)
        elif filename.endswith(".pdf"):
            text_content = await extract_text_from_pdf(temp_path)
        else:
            raise Exception(f"Unsupported file type: {filename}")

        # Step 4: Chunk the text
        chunks = await chunk_text(text_content)

        # Step 5: Vectorize and store chunks
        chunk_count = await vectorize_and_store_chunks(
            chunks, filename, content_type, date_folder
        )

        # Step 6: Update tracking index based on success/failure
        if chunk_count > 0:
            # Success - update to completed
            tracking_success = await update_tracking_index_status(
                content_name, "completed"
            )
        else:
            # No chunks created - mark as failed
            tracking_success = await update_tracking_index_status(
                content_name, "failed", "No chunks were created from content"
            )

        result = {
            "status": "success" if chunk_count > 0 else "failed",
            "filename": filename,
            "content_type": content_type,
            "chunk_count": chunk_count,
            "tracking_updated": tracking_success,
        }

        logger.info(f"Successfully processed {filename}: {chunk_count} chunks")
        return result

    except Exception as e:
        logger.error(f"Failed to process {file_info.get('filename', 'unknown')}: {e}")
        # Update tracking index to failed status
        if content_name:
            await update_tracking_index_status(content_name, "failed", str(e))

        return {
            "status": "failed",
            "filename": file_info.get("filename", "unknown"),
            "error": str(e),
        }
    finally:
        # Clean up temporary file
        if temp_path and temp_path.exists():
            temp_path.unlink()
            logger.info(f"Cleaned up temporary file: {temp_path}")


async def run_vectorization_pipeline() -> Dict[str, Any]:
    """
    Run the complete vectorization pipeline using knowledge tracking index.

    This pipeline:
    1. Scans S3 bucket for direct uploads and creates tracking records
    2. Queries tracking index for content with status "ingested"
    3. Processes each content item and updates status accordingly

    Returns:
        Pipeline results
    """
    logger.info("Starting ETL vectorization pipeline with knowledge tracking")

    try:
        # Get S3 bucket name
        bucket_name = get_s3_bucket_name()

        results = {
            "status": "success",
            "vectorization_date": datetime.now(timezone.utc).isoformat(),
            "direct_uploads_found": 0,
            "content_items_processed": 0,
            "successful_items": 0,
            "failed_items": 0,
            "details": [],
        }

        # Step 1: Scan S3 for direct uploads and create tracking records
        logger.info("Scanning S3 bucket for direct uploads...")
        direct_uploads = await scan_s3_for_direct_uploads()
        results["direct_uploads_found"] = len(direct_uploads)

        if direct_uploads:
            logger.info(
                f"Found {len(direct_uploads)} direct uploads, created tracking records"
            )

        # Step 2: Query tracking index for content ready for vectorization
        logger.info(
            "Querying knowledge tracking index for content ready for vectorization..."
        )
        content_records = await query_content_for_vectorization()

        if not content_records:
            logger.info("No content found ready for vectorization")
            return results

        # Step 3: Process each content item
        logger.info(
            f"Processing {len(content_records)} content items for vectorization"
        )

        for record in content_records:
            try:
                # Extract file information from tracking record
                bucket_url = record.get("bucket_url", "")
                if not bucket_url.startswith("s3://"):
                    logger.warning(
                        f"Invalid bucket URL for {record.get('name')}: {bucket_url}"
                    )
                    continue

                # Parse S3 URL to get bucket and key
                s3_parts = bucket_url.replace("s3://", "").split("/", 1)
                if len(s3_parts) != 2:
                    logger.warning(f"Invalid S3 URL format: {bucket_url}")
                    continue

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

                # Process the content file
                result = await process_content_file(bucket_name, file_info)
                results["details"].append(result)
                results["content_items_processed"] += 1

                if result.get("status") == "success":
                    results["successful_items"] += 1
                else:
                    results["failed_items"] += 1

            except Exception as e:
                logger.error(
                    f"Failed to process content record {record.get('name')}: {e}"
                )
                results["failed_items"] += 1
                results["details"].append(
                    {
                        "status": "failed",
                        "content_name": record.get("name"),
                        "error": str(e),
                    }
                )

        # Calculate summary
        results["summary"] = {
            "total_items": results["content_items_processed"],
            "successful_items": results["successful_items"],
            "failed_items": results["failed_items"],
            "direct_uploads_found": results["direct_uploads_found"],
        }

        logger.info(
            f"Vectorization pipeline completed: {results['successful_items']}/{results['content_items_processed']} items successful"
        )
        return results

    except Exception as e:
        logger.error(f"Vectorization pipeline failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "vectorization_date": datetime.now(timezone.utc).isoformat(),
        }
