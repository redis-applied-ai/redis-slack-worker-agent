# Haink: An Applied AI Agent

A language agent that incorporates the knowledge of the Applied AI team at Redis.

## Architecture

![Application Architecture](resources/haink_application_architecture.png)

**Flow**: Slack → FastAPI webhook → Redis task queue → Docket workers → Agent engine → OpenAI → Response

## Core Components

- **FastAPI App**: Webhook handler with health checks
- **Agent Engine**: ReAct methodology that runs search tools (curated AI team knowledge, internal Glean search, and web search via Tavily) in an agentic loop
- **Agent memory**: Remembers past interactions with users via the [Agent Memory Server](https://github.com/redis/agent-memory-server). and personalizes responses
- **Docket Workers**: Background task processing with retry logic
- **Redis**: Vector database (RedisVL) + streams-based task queue + caching

## Quick Start

### Prerequisites
- Python 3.12+, Redis, UV package manager
- Slack app credentials, OpenAI API key
- Optional: Tavily API key for web search

### Development Setup
```bash
# Install dependencies
uv sync

# Environment setup
cp .env.example .env
# Edit .env with your API keys

# Start Redis (with RedisJSON module for content management)
docker run -d -p 6379:6379 redis/redis-stack:latest

# Seed database
uv run python scripts/seed.py

# Start agent worker (Terminal 1)
uv run python -m app.worker

# Start API (Terminal 2)
uv run fastapi dev app/api/main.py

# Local otel collector (Optional Terminal 3)
docker compose -f docker-compose.collector.yml up
```

### Local development with Slack

To test local changes in Slack, you can run an ngrok server locally and then connect Slack to the ngrok endpoint that proxies to your local machine.

First, run ngrok:

```bash
ngrok http 8000
```

Then, in the Slack API console, update "Event Subscriptions -> Request URL" with the proxy URL ngrok gives you. It will look like `https://<ngrok proxy>/slack/events` (e.g.: `https://3cfaf9a1bcff.ngrok-free.app/slack/events`).

Additionally, if persisting answer feedback locally, update "Interactivity & Shortcuts -> Request URL" with the URL `https://<ngrok proxy>/slack/interactive`.

## Usage

**Slack**: Mention `@bot` in any channel. The bot processes questions using ReAct methodology with search tools (curated AI knowledge, internal docs with Glean, and web search).

**API**:
- Health: `GET /health`
- Docs: `GET /docs`
- Webhook: `POST /slack/events`

## Configuration

Essential environment variables:
```bash
# Required
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_SIGNING_SECRET=your-signing-secret
OPENAI_API_KEY=your-openai-key

# Optional
TAVILY_API_KEY=your-tavily-key  # Web search tool
REDIS_URL=redis://localhost:6379/0
```

## Testing

```bash
# Run tests
uv run pytest tests/unit/ -v

# With coverage
uv run pytest tests/unit/ --cov=. --cov-report=html

# Evaluation
uv run python scripts/evaluate_agent.py
```

## ETL & Content Management

**ETL Overview**: Streamlined content lifecycle management with automated ingestion and vectorization. Content moves through tracked stages: `staged` → `ingest-pending` → `ingested` → `vectorize-pending` → `completed`. The system automatically refreshes stale content based on configurable thresholds and processes new content immediately.

Comprehensive data ingestion and processing to support RAG and fine-tuning workflows.

**Quickstart**:
Use the content management UI at the root of the app to login and add/ingest/vectorize into the knowledge base.

```bash
uv run python scripts/seed_tracking_index.py
```

![UI](resources/content_mgmt.png)
![UI2](resources/content_mgmt_ingest.png)

Note: there is a dependency on auth0 for the UI login. For reference dev this is less essential but if you would like to configure with full login ability you will need to set the following env variables.

```
# Auth0 Configuration
# Get these values from your Auth0 dashboard
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_AUDIENCE=your-api-identifier
AUTH0_ISSUER=https://your-tenant.auth0.com/
AUTH0_CLIENT_ID=your-client-id
AUTH0_CLIENT_SECRET=your-client-secret
```

📖 **[Full Content Management Documentation](docs/CONTENT_MANAGEMENT.md)**

## Content Management

Content management system using Docket workers and S3 storage for easy content addition/update/deletion. **All content management endpoints are protected by Auth0 authentication.**

**API Endpoints**:
```bash
# Content management API endpoints available at /api/content/*
# Requires Auth0 authentication - see docs/CONTENT_MANAGEMENT.md
```

📖 **[Content Management Documentation](docs/CONTENT_MANAGEMENT.md)**

### Auth0 Setup

1. Create an Auth0 account and application
2. Configure environment variables (see `env.example`)
3. Set up permissions: `content:read`, `content:manage`, `content:process`