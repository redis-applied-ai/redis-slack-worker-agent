# Docket-Based Ingestion Pipeline

This document describes the new Docket-based ingestion pipeline that replaces the Prefect-based system for Goal 1 of the content management requirements.

## Overview

The ingestion pipeline downloads content from various sources (repositories, notebooks, blog posts) and uploads them to the `dev-applied-ai-agent` S3 bucket in `us-east-2`. It uses simple Docket workers instead of Prefect and includes date tracking for all ingest operations.

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌──────────────────┐
│  Content Sources│───▶│  Docket Workers │───▶│  S3 Storage      │
│                 │    │                 │    │                  │
│ • GitHub Repos  │    │ ┌─────────────┐ │    │ • dev-applied-   │
│ • Jupyter NB    │    │ │ download_   │ │    │   ai-agent       │
│ • Blog Posts    │    │ │ repository  │ │    │ • us-east-2      │
│                 │    │ └─────────────┘ │    │ • Date tracked   │
└─────────────────┘    │ ┌─────────────┐ │    └──────────────────┘
                       │ │ download_   │ │
                       │ │ notebook    │ │
                       │ └─────────────┘ │
                       │ ┌─────────────┐ │
                       │ │ download_   │ │
                       │ │ blog_post   │ │
                       │ └─────────────┘ │
                       └─────────────────┘
```

## Components

### 1. Ingestion Tasks (`app/ingestion_tasks.py`)

Core Docket tasks for downloading and uploading content:

- `download_repository()` - Downloads GitHub repositories
- `download_notebook()` - Downloads Jupyter notebooks
- `download_blog_post()` - Downloads blog posts
- `get_github_repositories()` - Fetches repository list from GitHub API
- `get_notebook_urls()` - Gets list of notebook URLs to download
- `get_blog_urls()` - Gets list of blog post URLs to download
- `run_ingestion_pipeline()` - Main orchestration function

### 2. Storage Manager (`app/content_storage.py`)

Extended S3 operations:

- `upload_file()` - Upload single file to S3
- `upload_directory()` - Upload entire directory to S3
- Cross-region support for `us-east-2`

### 3. Ledger Manager (`app/content_ledger.py`)

Content tracking and metadata:

- `record_ingestion()` - Records successful ingestion operations
- Date tracking for all ingest operations
- Integration with processing queue

### 4. API Endpoints (`app/content_api.py`)

REST API for triggering ingestion:

- `POST /api/content/ingest` - Trigger ingestion pipeline
- Support for content type filtering
- Force refresh option
- Concurrent task control

### 5. Web UI (`templates/content.html`)

User interface for content management:

- "Trigger Content Ingestion" section
- Form for configuring ingestion parameters
- Real-time status display

## Configuration

### Environment Variables

```bash
# GitHub API (optional, for higher rate limits)
GITHUB_TOKEN=your_github_token

# S3 Configuration
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_DEFAULT_REGION=us-east-2

# Redis Configuration
REDIS_URL=redis://localhost:6379/0
```

### S3 Bucket Structure

```
dev-applied-ai-agent/
├── raw/
│   ├── repos/
│   │   ├── repo-name-1/
│   │   └── repo-name-2/
│   ├── notebooks/
│   │   ├── notebook-1.ipynb
│   │   └── notebook-2.ipynb
│   └── blog/
│       ├── blog-post-1.html
│       └── blog-post-2.html
```

## Usage

### 1. Via Web UI

1. Navigate to the Content Management page
2. Scroll to "Trigger Content Ingestion" section
3. Configure parameters:
   - Content Types: `repos,notebooks,blog` (or leave empty for all)
   - Force Refresh: Check to re-download existing content
   - Max Concurrent Tasks: Number of parallel downloads (default: 5)
4. Click "Start Ingestion"

### 2. Via API

```bash
curl -X POST "http://localhost:3000/api/content/ingest" \
  -H "Authorization: Bearer YOUR_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content_types": "repos,notebooks,blog",
    "force_refresh": false,
    "max_concurrent": 5
  }'
```

### 3. Via Python Script

```python
from app.ingestion_tasks import run_ingestion_pipeline

# Run ingestion for all content types
result = await run_ingestion_pipeline()

# Run ingestion for specific content types
result = await run_ingestion_pipeline(
    content_types=["repos", "notebooks"],
    force_refresh=True,
    max_concurrent=3
)
```

## Content Sources

### Repositories

- **Source**: GitHub organization `RedisVentures`
- **Excluded**: `RedisVentures.github.io`, `embedchain`, `langchain`, `llama_index`
- **Storage**: `s3://dev-applied-ai-agent/raw/repos/{repo-name}/`

### Notebooks

- **Source**: Hardcoded list of notebook URLs
- **Format**: Jupyter notebooks (`.ipynb`)
- **Storage**: `s3://dev-applied-ai-agent/raw/notebooks/{notebook-name}.ipynb`

### Blog Posts

- **Source**: Hardcoded list of blog post URLs
- **Format**: HTML files
- **Storage**: `s3://dev-applied-ai-agent/raw/blog/{blog-title}.html`

## Date Tracking

All ingestion operations include comprehensive date tracking:

- **Ingestion Date**: When content was downloaded and uploaded
- **Commit Date**: For repositories, the latest commit date
- **Last Updated**: When the ledger entry was last modified
- **Created At**: When the content was first registered

## Error Handling

The pipeline includes robust error handling:

- **Retry Logic**: 3 attempts with exponential backoff
- **Concurrent Control**: Configurable max concurrent tasks
- **Partial Success**: Continues processing even if some items fail
- **Detailed Logging**: Comprehensive logging for debugging

## Monitoring

### Ledger Summary

Check ingestion status via the ledger summary:

```bash
curl -X GET "http://localhost:3000/api/content/ledger/summary" \
  -H "Authorization: Bearer YOUR_AUTH_TOKEN"
```

### Content Status

View specific content information:

```bash
curl -X GET "http://localhost:3000/api/content/status?content_type=repos" \
  -H "Authorization: Bearer YOUR_AUTH_TOKEN"
```

## Testing

Run the test script to verify the pipeline:

```bash
python test_ingestion.py
```

This will test the ingestion pipeline with a small subset of content (notebooks only) to verify everything is working correctly.

## Differences from Prefect System

| Feature | Prefect System | Docket System |
|---------|---------------|---------------|
| **Orchestration** | Prefect flows | Docket tasks |
| **Scheduling** | Cron-based | On-demand |
| **Storage** | Local files | S3 with cleanup |
| **Tracking** | Prefect UI | Redis ledger |
| **UI** | Prefect dashboard | Custom web UI |
| **Retries** | Prefect retry | Docket retry |
| **Concurrency** | Prefect limits | Configurable |

## Next Steps

This implementation fulfills Goal 1 of the content management requirements:

✅ **Goal 1**: Be able to click a button on the content management screen that runs the tasks to download repos, notebooks, and blog posts and uploads them to an `<env>-applied-ai-agent` bucket and then deletes the content locally. It should accomplish this with simple docket workers and not use prefect. Make sure that the date is tracked for the data ingest.

The system is ready for:
- **Goal 2**: Processing raw files and uploading to processed folder
- **Goal 3**: Vectorization and Redis database loading
- **Goal 4**: One-off content management operations
