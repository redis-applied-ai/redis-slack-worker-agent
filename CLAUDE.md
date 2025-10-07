# CLAUDE.md

Guidance for Claude Code when working with this codebase.

## Overview
See @./README.md for setup, dev tools, and architecture.

## Redis Version
This project uses Redis 8, which is the redis:8 docker image.
Important: DO NOT USE Redis Stack or other earlier versions of Redis.

## Technical Details

### App Structure (`app/`)
- `app.py`: FastAPI webhook handler
- `worker.py`: Docket background worker
- `tasks.py`: Task definitions with retry logic
- `rag.py`: RedisVL vector search + OpenAI generation
- `web_search.py`: Tavily API integration
- `glean_search.py`: Enterprise knowledge search
- `db.py`: Vector index management

### Pipeline System (`pipelines/`)
- `main.py`: Data pipeline orchestration
- `ingest_raw.py`: Raw data downloads
- `process_artifacts.py`: Data processing for RAG/training

### Development Patterns
- **Async/await** for all I/O
- **Singletons** for shared clients (Slack, Redis, OpenAI)
- **Task deduplication** via content hashes
- **Exponential backoff** retry with Docket
