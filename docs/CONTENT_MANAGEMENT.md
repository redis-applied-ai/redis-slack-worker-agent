# Content Management System

This document describes the content management system for the applied-ai-agent, which uses a Docket-based worker task system and S3 storage for managing knowledge base content.

## Current State vs Future State

### Current Implementation ✅
- **Docket-based task processing** with Redis queues
- **S3 storage** for all content (raw and processed)
- **Redis tracking index** with basic status tracking
- **Auth0 authentication** for API endpoints
- **Basic content management API** with ingest/vectorize endpoints
- **Content status tracking** with limited status types

### Future State (Per ETL Requirements) 🚧
- **Comprehensive status lifecycle** with 6 status types
- **Advanced refresh policies** with configurable thresholds
- **Enhanced tracking index** with complete metadata
- **Archive functionality** for content lifecycle management
- **Advanced failure recovery** with retry mechanisms
- **Direct S3 upload detection** and processing

## Prerequisites

The content management system requires:
- Redis 6.0+ with RedisJSON module enabled
- AWS S3 access and credentials
- Python 3.12+
- Docket task queue system
- Auth0 account and application configured

**Note**: The RedisJSON module is required for storing content metadata as structured JSON documents. This provides better querying capabilities and data structure compared to Redis hashes.

## Auth0 Setup

The content management API endpoints are protected by Auth0 authentication. To set up Auth0:

### 1. Create Auth0 Application
1. Go to [Auth0 Dashboard](https://manage.auth0.com/)
2. Create a new application or use an existing one
3. Set application type to "Machine to Machine" or "Regular Web Application"

### 2. Configure API
1. Go to "APIs" section
2. Create a new API or use existing one
3. Set the identifier (this will be your `AUTH0_AUDIENCE`)
4. Enable RBAC (Role-Based Access Control)

### 3. Set Environment Variables
Create a `.env` file with the following variables:

```bash
# Auth0 Configuration
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_AUDIENCE=your-api-identifier
AUTH0_ISSUER=https://your-tenant.auth0.com/

# Other required variables...
REDIS_URL=redis://localhost:6379/0
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
```

### 4. Permission Structure
The system uses the following permissions:
- `content:read` - Read content status and ledger information
- `content:manage` - Add, update, and remove content
- `content:process` - Trigger content processing pipelines

### 5. Testing Authentication
You can test the authentication using curl:

```bash
# Get an access token from Auth0
curl -X POST https://your-tenant.auth0.com/oauth/token \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "your-client-id",
    "client_secret": "your-client-secret",
    "audience": "your-api-identifier",
    "grant_type": "client_credentials"
  }'

# Use the token to access protected endpoints
curl -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  http://localhost:3000/api/content/status
```

## Overview

The content management system enables maintainers to easily add, update, and delete context from the knowledge base (Redis vector database) without storing content in the repository itself. All intermediary data is stored in S3, and processing is handled by Docket worker tasks.

## Architecture

### Components

1. **ContentStorageManager** (`app/content_storage.py`)
   - Handles S3 operations (upload, download, list, delete)
   - Manages content metadata and file organization
   - Provides async interface for all operations

2. **ContentLedgerManager** (`app/content_ledger.py`)
   - Tracks content state in Redis
   - Manages processing queue
   - Maintains content registry and status

3. **Docket Tasks** (`app/tasks.py`)
   - `add_content_to_knowledge_base`: Add new content
   - `update_content_in_knowledge_base`: Update existing content
   - `remove_content_from_knowledge_base`: Remove content
   - `process_content_pipeline`: Process content through pipeline

4. **API Endpoints** (`app/api/routers/content.py`)
   - `POST /api/content/ingest`: Trigger ingestion pipeline (✅ **Current**)
   - `POST /api/content/vectorize`: Trigger vectorization pipeline (✅ **Current**)
   - `POST /api/content/add`: Add new content (🚧 **Future**)
   - `PUT /api/content/update`: Update existing content (🚧 **Future**)
   - `DELETE /api/content/remove`: Remove content (🚧 **Future**)
   - `GET /api/content/status`: Get content status (🚧 **Future**)
   - `GET /api/content/ledger/summary`: Get ledger summary (🚧 **Future**)

5. **Docket Task Workers** (`app/worker/`)
   - Background task processing with Redis queues
   - Runs ingestion and vectorization tasks
   - Manages task concurrency and error handling

## S3 Storage Structure

```
S3 Bucket: applied-ai-agent
├── raw/
│   ├── repos/           # GitHub repositories
│   ├── notebooks/       # Jupyter notebooks
│   ├── blog/           # Blog posts
│   ├── slides/         # Presentation slides
│   └── slack/          # Slack conversations
├── processed/
│   ├── blog_text/      # Processed blog content
│   ├── recipes/        # Processed notebook content
│   ├── repo_pdfs/      # Generated PDFs from repos
│   ├── slide_text/     # Extracted slide text
│   └── slack/          # Processed Slack conversations
└── metadata/
    ├── ingestion_logs/ # Pipeline execution logs
    ├── processing_logs/ # Content processing logs
    └── content_registry.json # Content registry
```

## Redis Tracking Index Structure

### Current Implementation
The system uses a Redis search index called `knowledge_tracking` with the following schema:

```json
{
  "name": "content_name",
  "content_type": "repo_pdf|blog|notebook", 
  "content_url": "https://github.com/...",
  "source_date": "YYYY-MM-DD",
  "update_date": "YYYY-MM-DD", 
  "updated_at": "epoch_timestamp",
  "bucket_url": "s3://bucket/path/to/content",
  "processing_status": "staged|ingest-pending|ingested|vectorize-pending|completed|failed",
  "last_processing_attempt": "epoch_timestamp",
  "failure_reason": "error_message_if_failed",
  "retry_count": 0,
  "archive": "false|true"
}
```

### Current Status Types
- **`staged`**: Content added to tracking index but not yet ingested
- **`ingest-pending`**: Ingestion task started but content not yet uploaded to S3
- **`ingested`**: Content successfully ingested and uploaded to S3
- **`vectorize-pending`**: Vectorization task started but records not yet in vector DB
- **`completed`**: Content fully processed and available for search
- **`failed`**: Processing failed at any stage

### Future Enhancements (Per ETL Requirements)
- **Enhanced refresh policies** with `CONTENT_REFRESH_THRESHOLD_DAYS` configuration
- **Archive functionality** to exclude content from processing
- **Advanced failure recovery** with retry limits and exponential backoff
- **Direct S3 upload detection** and automatic processing

## Refresh Policies

### Current Implementation ✅
The system currently has basic refresh logic implemented in `app/etl/ingestion_queries.py`:

- **Staged Content**: Always processed immediately
- **Stale Content**: Content older than `CONTENT_REFRESH_THRESHOLD_DAYS` (default: 7 days)
- **Status-based Processing**: Skips content already in processing states

### Future Implementation 🚧 (Per ETL Requirements)
- **Environment Configuration**: `CONTENT_REFRESH_THRESHOLD_DAYS` environment variable
- **Ingest Button Logic**: 
  - Query for content older than threshold OR staged content
  - Update status to `ingest-pending` for selected items
  - Launch ingestion tasks for qualifying content
- **Archive Behavior**: Content with `archive: true` excluded from all processing
- **Recovery Operations**: Advanced querying for failed items and retry mechanisms

## Admin Operations

This section describes how administrators and maintainers can manage content in the knowledge base using the provided tools and APIs.

**Note**: All content management API endpoints require Auth0 authentication. You must include a valid Bearer token in the Authorization header for all requests.

### Current Capabilities ✅
- **Trigger Ingestion Pipeline**: Process content through ingestion pipeline
- **Trigger Vectorization Pipeline**: Process content through vectorization pipeline
- **Monitor Processing Status**: View content processing status and logs
- **Basic Content Management**: Add/update/remove content via Docket tasks

### Future Capabilities 🚧 (Per ETL Requirements)
- **Advanced Content Management API**: Full CRUD operations via REST API
- **Archive Management**: Archive/unarchive content for lifecycle management
- **Bulk Operations**: Batch content operations and status updates
- **Advanced Monitoring**: Detailed status tracking and failure recovery
- **Direct S3 Integration**: Automatic detection and processing of direct uploads

### Prerequisites for Admin Operations

Before performing content management operations, ensure you have:

1. **Access to the system**:
   - API access to the content management endpoints
   - Proper authentication and authorization
   - Network access to both the API and S3

2. **Content preparation**:
   - Content files uploaded to S3 in the correct location
   - Proper S3 path format: `s3://applied-ai-agent/<content_type>/<content_name>`
   - Content metadata prepared (description, tags, etc.)

3. **System verification**:
   - Redis is running and accessible
   - Docket workers are running and processing tasks
   - S3 bucket is accessible and properly configured

### Adding New Content

#### Step 1: Upload Content to S3
First, upload your content files to the appropriate S3 location:

```bash
# Example: Upload a new repository
aws s3 sync ./new-repo s3://applied-ai-agent/raw/repos/new-repo-name

# Example: Upload a new notebook
aws s3 cp ./new-notebook.ipynb s3://applied-ai-agent/raw/notebooks/new-notebook.ipynb

# Example: Upload a new blog post
aws s3 cp ./new-blog-post.html s3://applied-ai-agent/raw/blog/new-blog-post.html
```

#### Step 2: Add Content to Knowledge Base
Use the API to register the content:

```bash
# Add new repository
curl -X POST "http://localhost:3000/api/content/add" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{
    "content_type": "repo",
    "content_name": "new-repo-name",
    "s3_location": "s3://applied-ai-agent/raw/repos/new-repo-name",
    "metadata": {
      "description": "New repository for testing",
      "tags": ["test", "example"],
      "source": "github",
      "maintainer": "admin@company.com"
    }
  }'

# Add new notebook
curl -X POST "http://localhost:3000/api/content/add" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{
    "content_type": "notebook",
    "content_name": "new-notebook.ipynb",
    "s3_location": "s3://applied-ai-agent/raw/notebooks/new-notebook.ipynb",
    "metadata": {
      "description": "New Jupyter notebook for testing",
      "category": "tutorial",
      "difficulty": "beginner"
    }
  }'
```

#### Step 3: Monitor Processing Status
Check the processing status:

```bash
# Check specific content status
curl -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  "http://localhost:3000/api/content/status?content_type=repo&content_name=new-repo-name"

# Check all content of a type
curl -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  "http://localhost:3000/api/content/status?content_type=repo"

# Check overall ledger status
curl -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  "http://localhost:3000/api/content/ledger/summary"
```

### Updating Existing Content

#### Step 1: Update Content in S3
Upload the updated content to S3 (can be same or different location):

```bash
# Update existing repository
aws s3 sync ./updated-repo s3://applied-ai-agent/raw/repos/existing-repo-name

# Or upload to a new location with versioning
aws s3 sync ./updated-repo s3://applied-ai-agent/raw/repos/existing-repo-name-v2
```

#### Step 2: Update Content in Knowledge Base
Use the API to update the content registration:

```bash
# Update existing content
curl -X PUT "http://localhost:3000/api/content/update" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{
    "content_type": "repo",
    "content_name": "existing-repo-name",
    "s3_location": "s3://applied-ai-agent/raw/repos/existing-repo-name-v2",
    "metadata": {
      "description": "Updated description",
      "version": "2.0",
      "last_updated_by": "admin@company.com"
    }
  }'
```

#### Step 3: Verify Update
Check that the content has been updated:

```bash
# Verify the update
curl "http://localhost:3000/api/content/status?content_type=repo&content_name=existing-repo-name"
```

### Removing Content

#### Step 1: Remove from Knowledge Base
Remove the content registration (this will queue it for removal from the vector database):

```bash
# Remove content
curl -X DELETE "http://localhost:3000/api/content/remove?content_type=repo&content_name=repo-to-remove" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

#### Step 2: Clean Up S3 (Optional)
Optionally remove the content files from S3:

```bash
# Remove from S3
aws s3 rm s3://applied-ai-agent/raw/repos/repo-to-remove --recursive

# Or move to archive
aws s3 mv s3://applied-ai-agent/raw/repos/repo-to-remove s3://applied-ai-agent/archive/repos/repo-to-remove
```

#### Step 3: Verify Removal
Check that the content has been removed:

```bash
# Verify removal
curl "http://localhost:3000/api/content/status?content_type=repo&content_name=repo-to-remove"
# Should return 404 Not Found
```

### Bulk Operations

#### Batch Content Addition
For adding multiple content items, you can use a script:

```python
import asyncio
import aiohttp
import json

async def add_multiple_content():
    content_items = [
        {
            "content_type": "repo",
            "content_name": "repo-1",
            "s3_location": "s3://applied-ai-agent/raw/repos/repo-1",
            "metadata": {"description": "First repo"}
        },
        {
            "content_type": "notebook",
            "content_name": "notebook-1.ipynb",
            "s3_location": "s3://applied-ai-agent/raw/notebooks/notebook-1.ipynb",
            "metadata": {"description": "First notebook"}
        }
    ]
    
    async with aiohttp.ClientSession() as session:
        for item in content_items:
            async with session.post(
                "http://localhost:3000/api/content/add",
                json=item
            ) as response:
                result = await response.json()
                print(f"Added {item['content_name']}: {result}")

# Run the bulk operation
asyncio.run(add_multiple_content())
```

#### Bulk Status Check
Check the status of multiple content items:

```bash
# Get all content status
curl "http://localhost:3000/api/content/status" | jq '.'

# Get specific content type status
curl "http://localhost:3000/api/content/status?content_type=repo" | jq '.'
```

### Monitoring and Troubleshooting

#### Check System Health
Monitor the overall system status:

```bash
# Check ledger summary
curl "http://localhost:3000/api/content/ledger/summary" | jq '.'

# Check processing queue
curl "http://localhost:3000/api/content/status" | jq '.processing_queue_length'
```

#### Common Issues and Solutions

1. **Content not processing**:
   ```bash
   # Check if Docket workers are running
   curl "http://localhost:3000/health"
   
   # Check processing queue
   curl "http://localhost:3000/api/content/ledger/summary"
   ```

2. **S3 access issues**:
   ```bash
   # Verify S3 bucket access
   aws s3 ls s3://applied-ai-agent/
   
   # Check AWS credentials
   aws sts get-caller-identity
   ```

3. **Redis connection issues**:
   ```bash
   # Test Redis connection
   redis-cli ping
   
   # Check Redis memory
   redis-cli info memory
   ```

#### Log Analysis
Monitor logs for errors and processing status:

```bash
# Check application logs
docker logs <container-name> | grep "content"

# Check worker logs
docker logs <worker-container> | grep "processing"
```

### Best Practices

1. **Content Naming**:
   - Use consistent, descriptive names
   - Avoid special characters in content names
   - Use version numbers for updated content

2. **Metadata Management**:
   - Always include descriptive metadata
   - Use consistent tag structures
   - Include source and maintainer information

3. **S3 Organization**:
   - Maintain consistent folder structure
   - Use appropriate content types
   - Consider versioning strategy

4. **Monitoring**:
   - Regularly check processing status
   - Monitor queue lengths
   - Set up alerts for failures

5. **Backup and Recovery**:
   - Keep S3 content backed up
   - Document content relationships
   - Have rollback procedures ready

## Usage

### Current API Usage ✅

#### Trigger Ingestion Pipeline
```bash
# Via API
curl -X POST "http://localhost:8000/api/content/ingest" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

#### Trigger Vectorization Pipeline
```bash
# Via API
curl -X POST "http://localhost:8000/api/content/vectorize" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

#### Python Task Usage
```python
# Via Python Docket tasks
from app.etl.tasks.content_tasks import add_content_to_knowledge_base

result = await add_content_to_knowledge_base(
    content_type="repo",
    content_name="new-repo-name",
    s3_location="s3://applied-ai-agent/raw/repos/new-repo-name",
    metadata={"description": "New repository for testing"}
)
```

### Future API Usage 🚧 (Per ETL Requirements)

#### Adding Content
```python
# Via API (Future)
POST /api/content/add
{
    "content_type": "repo",
    "content_name": "new-repo-name",
    "s3_location": "s3://applied-ai-agent/raw/repos/new-repo-name",
    "metadata": {
        "description": "New repository for testing",
        "tags": ["test", "example"]
    }
}
```

### Updating Content

```python
# Via API
PUT /api/content/update
{
    "content_type": "repo",
    "content_name": "existing-repo-name",
    "s3_location": "s3://applied-ai-agent/raw/repos/updated-repo-name",
    "metadata": {
        "description": "Updated description"
    }
}
```

### Removing Content

```python
# Via API
DELETE /api/content/remove?content_type=repo&content_name=repo-to-remove

# Via Python
from app.tasks import remove_content_from_knowledge_base

result = await remove_content_from_knowledge_base(
    content_type="repo",
    content_name="repo-to-remove"
)
```

### Running Pipelines

```python
# Via Python API
import httpx

# Run ingestion pipeline
async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://localhost:8000/api/content/ingest",
        headers={"Authorization": "Bearer YOUR_TOKEN"}
    )
results = await run_docket_pipeline(
    ingestion=True,
    processing=True,
    content_types=["repos", "notebooks"],
    force_refresh=False,
    max_concurrent=5
)

# Run only ingestion
results = await run_docket_pipeline(
    ingestion=True,
    processing=False
)

# Run only processing
results = await run_docket_pipeline(
    ingestion=False,
    processing=True
)
```

## Configuration

### Environment Variables

```bash
# S3 Configuration
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_DEFAULT_REGION=us-east-1

# Content Management Configuration
CONTENT_MANAGEMENT_S3_BUCKET_NAME=applied-ai-agent
CONTENT_MANAGEMENT_MAX_CONCURRENT_TASKS=5
CONTENT_MANAGEMENT_TASK_RETRY_ATTEMPTS=3
CONTENT_MANAGEMENT_ENABLE_AUTO_PROCESSING=true
```

### Configuration File

The system uses `app/content_config.py` for configuration management. Settings can be overridden via environment variables with the `CONTENT_MANAGEMENT_` prefix.

## Migration from Prefect

### Current State
- Uses Docket for task management
- Stores data in S3
- Async task processing with Redis queue

### Migration Completed
- ✅ Migrated from Prefect 3 to Docket
- ✅ Migrated from local `data/` directory to S3 storage
- ✅ Implemented async task processing with Redis queue

### Migration Steps

1. **Infrastructure Setup**
   - Create S3 bucket and configure IAM roles
   - Verify Redis connectivity
   - Set up environment variables

2. **Data Migration**
   - Upload existing data to S3
   - Update pipeline references
   - Remove local data directories

3. **Pipeline Migration**
   - Convert Prefect flows to Docket tasks
   - Test new task system
   - Deploy and monitor

4. **Content Management**
   - Deploy management API
   - Train team on new tools
   - Monitor system performance

## Testing

### Unit Tests

```bash
# Run content management tests
uv run pytest tests/unit/test_content_management.py -v

# Run with coverage
uv run pytest tests/unit/test_content_management.py --cov=app.content_management --cov-report=html
```

### Integration Tests

The system includes integration tests that verify:
- S3 operations with mocked client
- Redis operations with mocked client
- Task execution and error handling
- API endpoint functionality

## Monitoring and Observability

### Metrics

- S3 storage usage and costs
- Task queue performance and throughput
- Content processing success rates
- API response times and error rates

### Logging

- Structured logging for all operations
- Audit trail for content changes
- Error tracking and alerting

### Health Checks

- S3 connectivity and permissions
- Redis ledger system health
- Task queue worker status

## Troubleshooting

### Common Issues

1. **S3 Connection Errors**
   - Verify AWS credentials and permissions
   - Check bucket name and region
   - Ensure bucket exists and is accessible

2. **Redis Connection Errors**
   - Verify Redis URL and connectivity
   - Check Redis memory and connection limits
   - Ensure Redis is running and healthy

3. **Task Processing Failures**
   - Check task queue status
   - Review error logs and task results
   - Verify content exists in S3

### Debug Commands

```python
# Check ledger status
from app.content_ledger import get_content_ledger_manager
ledger = get_content_ledger_manager()
summary = await ledger.get_ledger_summary()
print(summary)

# Check storage status
from app.content_storage import get_content_storage_manager
storage = get_content_storage_manager()
content = await storage.list_content("repos")
print(content)

# Check pipeline status via API
async with httpx.AsyncClient() as client:
    response = await client.get(
        "http://localhost:8000/api/content/status",
        headers={"Authorization": "Bearer YOUR_TOKEN"}
    )
    status = response.json()
print(status)
```

## Implementation Status Summary

### ✅ Currently Implemented
- **Docket-based task processing** with Redis queues
- **S3 storage** for all content (raw and processed)
- **Redis tracking index** with basic status tracking
- **Auth0 authentication** for API endpoints
- **Basic content management API** with ingest/vectorize endpoints
- **Content status tracking** with 6 status types
- **Basic refresh policies** with configurable thresholds
- **Content processing pipeline** (ingestion and vectorization)

### 🚧 Planned Implementation (Per ETL Requirements)
- **Enhanced refresh policies** with full ETL requirements compliance
- **Archive functionality** for content lifecycle management
- **Advanced failure recovery** with retry mechanisms
- **Direct S3 upload detection** and automatic processing
- **Full CRUD API** for content management
- **Advanced monitoring and querying** capabilities
- **Bulk operations** and batch processing

### 🔄 Migration Status
- ✅ **Completed**: Migrated from Prefect 3 to Docket
- ✅ **Completed**: Migrated from local `data/` directory to S3 storage
- ✅ **Completed**: Implemented async task processing with Redis queue
- 🚧 **In Progress**: Enhanced tracking index and refresh policies
- 🚧 **Planned**: Full ETL requirements compliance

## Future Enhancements

1. **Content Processing Integration**
   - Integrate with existing `process_artifacts.py` pipeline
   - Implement vector generation and storage
   - Add content validation and quality checks

2. **Advanced Features**
   - Content versioning and rollback
   - Automated content discovery
   - Content dependency management
   - Performance optimization and caching

3. **Monitoring and Alerting**
   - Prometheus metrics integration
   - Automated alerting for failures
   - Performance dashboards
   - Cost optimization recommendations
