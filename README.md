# Applied AI Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub stars](https://img.shields.io/github/stars/redis-applied-ai/redis-slack-worker-agent)](https://github.com/redis-applied-ai/redis-slack-worker-agent/stargazers)
![Language](https://img.shields.io/github/languages/top/redis-applied-ai/redis-slack-worker-agent)
![GitHub last commit](https://img.shields.io/github/last-commit/redis-applied-ai/redis-slack-worker-agent)

The code in this repo shows a reference architecture for a Slack-integrated agent application running on ECS. The architecture is designed so that agent workers, API containers, and agent-memory-server can scale in a decoupled way. [The agent memory server](https://github.com/redis/agent-memory-server) itself is implemented as a tool call for storing and automatically summarizing and persisting short and long term memories.

## Business objective

Internally at Redis, this bot extends the Applied AI engineering team by assisting with basic code and answer generation from a curated knowledge base.


## Architecture

![Application Architecture](resources/aws_architecture.png)

**TLDR Flow**: Slack → FastAPI webhook → Redis task queue → Agent workers pick up and execute tasks → Agent workers perform tool calls and ReAct style execution -> invoke Slack callbacks async.

## Core Components

- **FastAPI App**: Webhook handler.
- **Agent Engine**: ReAct methodology runs search tools in an agentic loop.
- **Agent memory**: Remembers past interactions with users via the [Agent Memory Server](https://github.com/redis/agent-memory-server).
- **Docket Workers**: Core task processing utility.
- **Redis**: Vector database + streams-based task queue + memory store.

## Quick Start

### Prerequisites
- Python 3.12+, Redis, UV package manager
- Slack app credentials, OpenAI API key
- Tavily API key for web search

### Development Setup
```bash
# Install dependencies
uv sync

# Environment setup
cp .env.example .env
# Edit .env with your API keys

# Start Redis 8 (no Redis Stack required)
docker run -d -p 6379:6379 redis:8-alpine

# Seed database
uv run python scripts/seed.py

# Start agent worker (Terminal 1)
uv run python -m app.worker

# Start API (Terminal 2)
uv run fastapi dev app/api/main.py

```

### Development with Slack

To test changes in Slack, you can run an ngrok server locally or setup with ALB with terraform (see below) and then connect Slack to the respective endpoint.

For ngrok, run:

```bash
ngrok http 8000
```

Then, in the Slack API console, update "Event Subscriptions -> Request URL" with the proxy URL ngrok gives you. It will look like `https://<ngrok proxy>/slack/events` (e.g.: `https://3cfaf9a1bcff.ngrok-free.app/slack/events`).

![Application Architecture](resources/slack_subscription.png)

Additionally, if persisting answer feedback locally, update "Interactivity & Shortcuts -> Request URL" with the URL `https://<ngrok proxy>/slack/interactive`.

## Usage

**Slack**: Mention `@bot` in any channel. The bot processes questions using ReAct methodology with search tools (curated AI knowledge and web search).

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
TAVILY_API_KEY=your-tavily-key  # Web search tool
REDIS_URL=redis://localhost:6379/0
```


## Amazon Bedrock (LLM provider option)

This repo includes scripts to automate IAM permissions for Bedrock and a local tool-calling test script.

Prerequisites
- AWS CLI v2 configured with credentials
- Region: us-east-1 (default)

1) Grant Bedrock invoke permissions to an IAM user
```bash
chmod +x scripts/bedrock_provision_access.sh
scripts/bedrock_provision_access.sh user <YOUR_IAM_USER_NAME> us-east-1
```
This attaches a minimal policy that allows invoking Bedrock models and listing model info. If you see AccessDenied during inference, enable model access in the console.

2) Enable model access (one-time, per account/region)
Open the Bedrock Model access page and enable the providers/models you plan to use (default used here is Claude 3.5 Sonnet):
- https://us-east-1.console.aws.amazon.com/bedrock/home?region=us-east-1#/model-access

3) Switch provider to Bedrock and run locally
```bash
export AWS_DEFAULT_REGION=us-east-1
export LLM_PROVIDER=bedrock
export BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20240620-v1:0
export LOG_LEVEL=INFO
uv run python -m app.worker &
uv run fastapi dev app/api/main.py
```
You should see logs like: "LLM configured: provider=bedrock model=anthropic.claude-3-5-sonnet-20240620-v1:0"

Optional: add to your .env for convenience
```bash
AWS_DEFAULT_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20240620-v1:0
# Future toggle; default provider may be Bedrock in this repo
LLM_PROVIDER=bedrock
```

## Deployment (AWS, single environment)

This reference deploys a working agent stack on AWS with a single `terraform apply`:
VPC, ALB, ECS Fargate (API, Worker, Memory Server), ECR, S3, IAM, and basic CloudWatch.
No domain or SSL is required; the ALB exposes HTTP for testing.

Development environment requirements
- Terraform v1.10 or later
- AWS CLI configured with credentials
- Docker (to build and push images)
- Agent Memory Server [credentials](https://redis.github.io/agent-memory-server/authentication/?h=secret#token-management-commands)

Prerequisites
- AWS account with permissions for VPC, ECS (Fargate), ECR, ALB, IAM, S3, CloudWatch
- Slack app credentials (bot token, signing secret)
- OpenAI API key
- Cloud-accessible Redis URL (e.g., Upstash or ElastiCache). Localhost will not work from ECS.
- Tavily API key (web search)

Terraform modules
- VPC: networking, subnets, security groups
- ECR: container repositories
- ECS: Fargate cluster, API and worker services, Memory Server sidecar (separate service)
- ALB: public Load Balancer routing to API and Memory Server health
- S3: content bucket for uploads/examples
- IAM: roles and policies for ECS/ECR/S3/SSM
- Monitoring: CloudWatch dashboard and alarms (basic)

Step 1) Configure minimal variables
Create or edit `terraform/terraform.tfvars` (example):
```hcl
aws_region   = "us-east-1"
project_name = "my-ai-agent"           # choose your own unique name
bucket_name  = "my-ai-agent-content-1234"  # must be globally unique
```

Step 2) Seed required secrets into AWS SSM
- Copy the example and fill in values: `cp .env.example .env && edit .env`
- Then run the loader script to write SSM parameters under `/${project_name}/...`
- IMPORTANT: Use a cloud Redis URL for `REDIS_URL` (not localhost)
```bash
set -a; source .env; \
export PROJECT_NAME="my-ai-agent" AWS_REGION="us-east-1"; \
# Required for cloud: set a token and the base URL the app will call
export AGENT_MEMORY_SERVER_API_KEY="generate-a-strong-token"; \
# Get ALB DNS dynamically (ALB routes /v1/* to memory server):
export AGENT_MEMORY_SERVER_URL="http://$(terraform -chdir=terraform output -raw alb_dns_name)"; \
set +a; sh ./scripts/load_secrets.sh
```
See the full list of parameters in `terraform/SSM_PARAMETERS.md`.

Step 3) Deploy the infrastructure
Use the helper script or terraform directly:
```bash
# Using helper script
./terraform/deploy.sh apply

# Or manually
terraform -chdir=terraform init
terraform -chdir=terraform validate
terraform -chdir=terraform plan -out=tfplan
terraform -chdir=terraform apply tfplan
```
After apply, note the `application_url` output (ALB HTTP URL).

Step 4) Build and push images to ECR

**CRITICAL**: ECS Fargate runs on X86_64 (amd64) architecture. Always build with `--platform linux/amd64` to avoid "exec format error" failures.

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=us-east-1
ECR="$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin "$ECR"

# API (build for linux/amd64)
docker build --platform linux/amd64 -f Dockerfile.api -t "$ECR/my-ai-agent-api:latest" .
docker push "$ECR/my-ai-agent-api:latest"

# Worker (build for linux/amd64)
docker build --platform linux/amd64 -f Dockerfile.worker -t "$ECR/my-ai-agent-worker:latest" .
docker push "$ECR/my-ai-agent-worker:latest"
```

**Note**: If you encounter "No space left on device" during `uv sync`, increase Docker Desktop disk allocation (Settings → Resources → Disk image size).

**Optional - Test locally before pushing**:
```bash
# Verify architecture
docker image inspect "$ECR/my-ai-agent-api:latest" --format '{{.Architecture}}'  # should show "amd64"

# Quick smoke test (requires .env file)
docker run --rm --env-file .env -p 3000:3000 "$ECR/my-ai-agent-api:latest" &
sleep 5 && curl -sf http://localhost:3000/health && echo "✓ API health OK"
docker stop $(docker ps -q --filter ancestor="$ECR/my-ai-agent-api:latest")

# Verify git binary is present (prevents GitPython errors)
docker run --rm "$ECR/my-ai-agent-worker:latest" git --version
docker run --rm "$ECR/my-ai-agent-worker:latest" python -c "import git; print('GitPython OK')"
```

Step 5) Force ECS services to deploy latest images
```bash
aws ecs update-service --cluster my-ai-agent-cluster \
  --service my-ai-agent-api-service --force-new-deployment
aws ecs update-service --cluster my-ai-agent-cluster \
  --service my-ai-agent-worker-service --force-new-deployment
```

Step 6) Verify health
```bash
APP_URL=$(terraform -chdir=terraform output -raw application_url)
curl -i "$APP_URL/health"
curl -i "$APP_URL/v1/health"
```

Step 7) Configure Slack and test
- Event Subscriptions → Enable → Request URL: `<application_url>/slack/events`
- Interactivity & Shortcuts → Enable → Request URL: `<application_url>/slack/interactive`
- Subscribe to bot events (at minimum): `app_mention`, `message.channels`, `message.im`
Test by mentioning the bot in a channel or DM.

> See Development with Slack section for visual on how to update this value.

Cleanup
```bash
terraform -chdir=terraform destroy
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

Note: Outside of local development, there is a dependency for Auth0 to protect the endpoints which can be implemented with the following env variables and setting permissions for: `content:read`, `content:manage`, `content:process` in Auth0.

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