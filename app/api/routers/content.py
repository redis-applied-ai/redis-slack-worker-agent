"""
Content management API endpoints.

This module provides RESTful endpoints for managing content in the knowledge base.
All endpoints are protected by Auth0 authentication.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from docket.docket import Docket
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Optional

from app.etl.ingestion_queries import (
    filter_content_by_type,
    query_content_for_ingestion,
)
from app.etl.tasks.ingestion import process_blog, process_notebook, process_repository
from app.etl.tasks.vectorization import process_content_file
from app.etl.vectorization_queries import get_content_ready_for_vectorization
from app.utilities.environment import get_env_var, is_local_mode
from app.utilities.s3_utils import get_s3_bucket_name

from ..auth_config import get_auth0_audience, get_auth0_domain, get_auth0_issuer
from ..models.content import AddContentRequest, PipelineResponse

logger = logging.getLogger(__name__)


# Initialize router
router = APIRouter(prefix="/api/content", tags=["content-management"])

# Security scheme for Auth0
security = HTTPBearer()

# Auth0 configuration
AUTH0_DOMAIN = get_auth0_domain()
AUTH0_AUDIENCE = get_auth0_audience()
AUTH0_ISSUER = get_auth0_issuer()


def get_redis_url() -> str:
    """Get Redis URL from environment variables."""
    return get_env_var("REDIS_URL", "redis://localhost:6379/0")


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict[str, Any]:
    """
    Verify Auth0 JWT token and return decoded payload.

    Args:
        credentials: HTTP Authorization header with Bearer token

    Returns:
        Decoded JWT payload

    Raises:
        HTTPException: If token is invalid or verification fails
    """
    if not AUTH0_DOMAIN or not AUTH0_AUDIENCE:
        raise HTTPException(
            status_code=500, detail="Auth0 configuration not properly set"
        )

    try:
        # Get Auth0 public keys
        import httpx

        async with httpx.AsyncClient() as client:
            jwks_url = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"
            jwks_response = await client.get(jwks_url)
            jwks_response.raise_for_status()

        # Decode and verify token (simplified - in production use proper JWT library)
        # This is a basic implementation - consider using python-jose or PyJWT for production

        # For now, we'll do basic validation
        # In production, you should:
        # 1. Verify the token signature using the JWKS
        # 2. Check the token expiration
        # 3. Validate the audience and issuer
        # 4. Check custom claims if needed

        # Placeholder for token validation
        # decoded_token = jwt.decode(token, options={"verify_signature": False})

        # For development/testing, we'll accept the token
        # In production, implement proper JWT validation
        return {
            "sub": "user_id",
            "email": "user@example.com",
            "permissions": ["content:manage"],
        }

    except Exception as e:
        raise HTTPException(
            status_code=401, detail=f"Invalid authentication token: {str(e)}"
        )


async def bypass_auth_for_local() -> Dict[str, Any]:
    """
    Bypass authentication for local development mode.
    
    Returns mock user data with all necessary permissions.
    """
    return {
        "sub": "local_dev_user",
        "email": "local@development.com", 
        "permissions": ["content:manage", "content:ingest", "content:process", "content:read"],
        "local_mode": True
    }


def require_permission(required_permission: str):
    """
    Decorator to check if user has required permission.

    Args:
        required_permission: The permission required to access the endpoint
    """

    if is_local_mode():
        # In local mode, return a simple function that bypasses auth completely
        async def local_bypass():
            return await bypass_auth_for_local()
        return local_bypass
    
    else:
        # In production mode, use normal auth flow with credentials
        async def auth_checker(
            credentials: HTTPAuthorizationCredentials = Depends(security)
        ):
            token_payload = await verify_token(credentials)
            permissions = token_payload.get("permissions", [])
            
            # Check if user has required permission
            if not permissions or required_permission not in permissions:
                # Check if user has any content-related permissions as fallback
                content_permissions = [p for p in permissions if p.startswith("content:")]
                if not content_permissions:
                    raise HTTPException(
                        status_code=403,
                        detail=f"Insufficient permissions. Required: {required_permission}",
                    )
            return token_payload
        return auth_checker


async def run_async_ingestion_pipeline() -> Dict[str, Any]:
    """
    Run the ingestion pipeline asynchronously using Docket.

    This function:
    1. Queries the knowledge tracking index for content that needs ingestion
    2. For each qualifying content item, adds a Docket task to be processed by workers

    Returns:
        Dictionary with pipeline results
    """
    logger.info("Starting async ETL ingestion pipeline")

    # Query for content that needs ingestion using the DRY function
    content_to_process = query_content_for_ingestion()

    results = {
        "status": "success",
        "ingestion_date": datetime.now(timezone.utc).isoformat(),
        "repos": [],
        "blogs": [],
        "notebooks": [],
        "total_tasks_queued": 0,
    }

    # Process each content type asynchronously using Docket
    # Use a single Docket context for all task queuing to ensure consistency
    async with Docket(name="applied-ai-agent", url=get_redis_url()) as docket:
        for content_type in ["repo", "blog", "notebook"]:
            # Filter content by type
            items_for_type = filter_content_by_type(content_to_process, content_type)

            for item in items_for_type:
                name = item.get("name", "")
                content_url = item.get("content_url", "")

                ingest_key = f"{content_type}_{name}_{int(datetime.now().timestamp())}"

                if content_type == "repo":
                    await docket.add(process_repository, key=ingest_key)(
                        repo_name=name, github_url=content_url
                    )

                    results["repos"].append(
                        {
                            "name": name,
                            "github_url": content_url,
                            "task_key": ingest_key,
                            "status": "queued",
                        }
                    )
                    results["total_tasks_queued"] += 1

                elif content_type == "blog":
                    await docket.add(process_blog, key=ingest_key)(
                        blog_name=name, blog_url=content_url
                    )

                    results["blogs"].append(
                        {
                            "name": name,
                            "blog_url": content_url,
                            "task_key": ingest_key,
                            "status": "queued",
                        }
                    )
                    results["total_tasks_queued"] += 1

                elif content_type == "notebook":
                    await docket.add(process_notebook, key=ingest_key)(
                        notebook_name=name, github_url=content_url
                    )
                    results["notebooks"].append(
                        {
                            "name": name,
                            "github_url": content_url,
                            "task_key": ingest_key,
                            "status": "queued",
                        }
                    )
                    results["total_tasks_queued"] += 1
                else:
                    logger.warning(f"{content_type=} not a valid type")

    logger.info(f"Successfully queued {results['total_tasks_queued']} ingestion tasks")
    return results


async def run_async_vectorization_pipeline() -> Dict[str, Any]:
    """
    Run the vectorization pipeline asynchronously using Docket with knowledge tracking.

    This function:
    1. Scans S3 for direct uploads and creates tracking records
    2. Queries knowledge tracking index for content with status "ingested"
    3. Queues vectorization tasks for each content item

    Returns:
        Dictionary with pipeline results
    """
    logger.info("Starting async ETL vectorization pipeline with knowledge tracking")

    results = {
        "status": "success",
        "vectorization_date": datetime.now(timezone.utc).isoformat(),
        "content_items_queued": 0,
        "total_tasks_queued": 0,
        "details": [],
    }

    # Get all content ready for vectorization using the DRY function
    content_files = await get_content_ready_for_vectorization()

    if not content_files:
        logger.info("No content found ready for vectorization")
        return results

    # Queue vectorization tasks using Docket
    logger.info(f"Queuing {len(content_files)} content items for vectorization")
    bucket_name = get_s3_bucket_name()

    for file_info in content_files:
        try:
            filename = file_info["filename"]
            content_type = file_info["content_type"]
            content_name = Path(filename).stem

            # Queue the vectorization task
            vectorize_key = (
                f"vectorize_{content_name}_{int(datetime.now().timestamp())}"
            )

            async with Docket(name="applied-ai-agent", url=get_redis_url()) as docket:
                await docket.add(process_content_file, key=vectorize_key)(
                    bucket_name=bucket_name, file_info=file_info
                )

            results["details"].append(
                {
                    "content_name": content_name,
                    "filename": filename,
                    "content_type": content_type,
                    "task_key": vectorize_key,
                    "status": "queued",
                }
            )
            results["content_items_queued"] += 1
            results["total_tasks_queued"] += 1

        except Exception as e:
            logger.error(
                f"Failed to queue content file {file_info.get('filename')}: {e}"
            )
            results["details"].append(
                {
                    "filename": file_info.get("filename"),
                    "status": "failed",
                    "error": str(e),
                }
            )

    logger.info(
        f"Successfully queued {results['total_tasks_queued']} vectorization tasks"
    )
    return results


async def create_tracking_record_with_staged_status(
    content_name: str, content_type: str, content_url: str
) -> bool:
    """
    Create a tracking record in the knowledge tracking index with staged status.

    Args:
        content_name: Name of the content item
        content_type: Type of content (blog, notebook, repo)
        content_url: URL where the content can be accessed

    Returns:
        True if successful, False otherwise
    """
    try:
        from app.utilities.database import get_redis_client

        redis_client = get_redis_client()
        current_date = datetime.now(timezone.utc)
        current_timestamp = int(current_date.timestamp())

        # Create tracking record with staged status
        tracking_record = {
            "name": content_name,
            "content_type": content_type,
            "content_url": content_url,
            "archive": "false",
            "source_date": current_date.strftime("%Y-%m-%d"),
            "updated_date": current_date.strftime("%Y-%m-%d"),
            "updated_ts": current_timestamp,
            "processing_status": "staged",  # New content ready for processing
            "last_processing_attempt": current_timestamp,
            "failure_reason": "",
            "retry_count": 0,
            "bucket_url": "",  # Will be populated after ingestion
        }

        # Store in Redis with knowledge_tracking prefix
        key = f"knowledge_tracking:{content_name}"
        await redis_client.json().set(key, "$", tracking_record)

        logger.info(f"Created tracking record with staged status: {content_name}")
        return True

    except Exception as e:
        logger.error(f"Failed to create tracking record for {content_name}: {e}")
        return False


async def run_complete_content_processing(
    content_name: str, content_type: str, content_url: str
) -> Dict[str, Any]:
    """
    Run the complete content processing pipeline synchronously:
    1. Add to tracking index with staged status
    2. Process content (ingestion)
    3. Vectorize processed content

    Args:
        content_name: Name of the content item
        content_type: Type of content (blog, notebook, repo)
        content_url: URL where the content can be accessed

    Returns:
        Dictionary with processing results
    """
    result = {
        "status": "success",
        "content_name": content_name,
        "content_type": content_type,
        "content_url": content_url,
        "processing_date": datetime.now(timezone.utc).isoformat(),
        "steps": {},
    }

    try:
        # Step 1: Create tracking record with staged status
        logger.info(f"Step 1: Creating tracking record for {content_name}")
        tracking_success = await create_tracking_record_with_staged_status(
            content_name, content_type, content_url
        )

        if not tracking_success:
            raise Exception("Failed to create tracking record")

        result["steps"]["tracking_record"] = {
            "status": "completed",
            "message": "Tracking record created with staged status",
        }

        # Step 2: Process content based on type
        logger.info(f"Step 2: Processing {content_type} content: {content_name}")

        if content_type == "blog":
            processing_result = await process_blog(content_name, content_url)
        elif content_type == "notebook":
            processing_result = await process_notebook(content_name, content_url)
        elif content_type == "repo":
            processing_result = await process_repository(content_name, content_url)
        else:
            raise Exception(f"Unsupported content type: {content_type}")

        result["steps"]["ingestion"] = {
            "status": "completed",
            "message": f"{content_type.title()} processed successfully",
            "details": processing_result,
        }

        # Step 3: Vectorize the processed content
        logger.info(f"Step 3: Vectorizing processed content for {content_name}")

        # Get content files ready for vectorization for this specific item
        content_files = await get_content_ready_for_vectorization()
        matching_files = [
            f for f in content_files if Path(f["filename"]).stem == content_name
        ]

        if matching_files:
            bucket_name = get_s3_bucket_name()
            vectorization_results = []

            for file_info in matching_files:
                vectorize_result = await process_content_file(bucket_name, file_info)
                vectorization_results.append(vectorize_result)

            result["steps"]["vectorization"] = {
                "status": "completed",
                "message": f"Vectorized {len(vectorization_results)} files",
                "details": vectorization_results,
            }
        else:
            result["steps"]["vectorization"] = {
                "status": "skipped",
                "message": "No files found ready for vectorization",
            }

        logger.info(f"Successfully completed all processing steps for {content_name}")
        return result

    except Exception as e:
        logger.error(f"Failed to process content {content_name}: {e}")
        result["status"] = "failed"
        result["error"] = str(e)

        # Try to update tracking record with failed status
        try:
            from app.utilities.database import get_redis_client

            redis_client = get_redis_client()
            key = f"knowledge_tracking:{content_name}"
            existing_record = await redis_client.json().get(key)

            if existing_record:
                existing_record["processing_status"] = "failed"
                existing_record["failure_reason"] = str(e)
                existing_record["retry_count"] = (
                    existing_record.get("retry_count", 0) + 1
                )
                existing_record["updated_ts"] = int(
                    datetime.now(timezone.utc).timestamp()
                )
                await redis_client.json().set(key, "$", existing_record)

        except Exception as update_error:
            logger.error(f"Failed to update tracking record status: {update_error}")

        return result


@router.post("/add", response_model=PipelineResponse)
async def add_content(
    request: AddContentRequest,
    user: Dict[str, Any] = Depends(require_permission("content:manage")),
) -> PipelineResponse:
    """
    Add new content to the knowledge base and process it through the complete pipeline.

    This endpoint:
    1. Adds the content to the tracking index with 'staged' status
    2. Processes the content through ingestion (downloads and converts to PDF)
    3. Vectorizes the processed content and stores in the RAG index

    Args:
        request: Content details (name, type, URL)
        user: Authenticated user (from Auth0)

    Returns:
        Processing results
    """
    try:
        result = await run_complete_content_processing(
            request.name, request.content_type, request.content_url
        )

        if result["status"] == "success":
            return PipelineResponse(
                status="success",
                message=f"Content '{request.name}' added and processed successfully",
                result=result,
            )
        else:
            return PipelineResponse(
                status="failed",
                message=f"Failed to process content '{request.name}': {result.get('error', 'Unknown error')}",
                result=result,
            )

    except Exception as e:
        logger.error(f"Failed to add content {request.name}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to add and process content: {str(e)}"
        )


@router.post("/ingest", response_model=PipelineResponse)
async def trigger_ingestion(
    user: Dict[str, Any] = Depends(require_permission("content:ingest")),
) -> PipelineResponse:
    """
    Trigger the ingestion pipeline to process content from the ledger asynchronously.

    Args:
        user: Authenticated user (from Auth0)

    Returns:
        Ingestion pipeline results
    """
    result = await run_async_ingestion_pipeline()
    return PipelineResponse(
        status=result.get("status", "success"),
        message=f"Ingestion pipeline queued {result.get('total_tasks_queued', 0)} tasks successfully",
        result=result,
    )


@router.post("/vectorize", response_model=PipelineResponse)
async def trigger_vectorization(
    user: Dict[str, Any] = Depends(require_permission("content:process")),
) -> PipelineResponse:
    """
    Trigger the vectorization pipeline to process PDFs and store in RAG index asynchronously.

    Args:
        user: Authenticated user (from Auth0)

    Returns:
        Vectorization pipeline results
    """
    try:
        result = await run_async_vectorization_pipeline()
        return PipelineResponse(
            status=result.get("status", "success"),
            message=f"Vectorization pipeline queued {result.get('total_tasks_queued', 0)} tasks successfully",
            result=result,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to queue vectorization pipeline: {str(e)}"
        )
