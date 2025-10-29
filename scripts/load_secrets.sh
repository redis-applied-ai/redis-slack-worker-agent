#!/usr/bin/env sh
# Seed AWS Systems Manager Parameter Store (SSM) with required/optional secrets
# Usage:
#   set -a; source .env; set +a
#   sh ./scripts/load_secrets.sh
#
# Notes:
# - This simplified repo uses a single project, not multiple environments.
# - Secrets are stored under the path: /${PROJECT_NAME}/...

set -eu

# Defaults (override by exporting PROJECT_NAME/AWS_REGION before running)
PROJECT_NAME="${PROJECT_NAME:-applied-ai-agent-worker}"
AWS_REGION="${AWS_REGION:-us-east-1}"

info()  { echo "[INFO]  $*"; }
error() { echo "[ERROR] $*" 1>&2; }

require() {
  var_name="$1"
  eval "val=\${$var_name-}"
  if [ -z "$val" ]; then
    error "Missing required env var: $var_name (set it in .env before running)"
    exit 1
  fi
}

info "Using PROJECT_NAME=$PROJECT_NAME, AWS_REGION=$AWS_REGION"

# Required secrets
require SLACK_BOT_TOKEN
require SLACK_SIGNING_SECRET
require OPENAI_API_KEY
require TAVILY_API_KEY
require REDIS_URL

info "Seeding required secrets to SSM..."
aws ssm put-parameter --region "$AWS_REGION" --name "/$PROJECT_NAME/slack/bot_token"       --value "$SLACK_BOT_TOKEN"       --type SecureString --overwrite
aws ssm put-parameter --region "$AWS_REGION" --name "/$PROJECT_NAME/slack/signing_secret"  --value "$SLACK_SIGNING_SECRET"  --type SecureString --overwrite
aws ssm put-parameter --region "$AWS_REGION" --name "/$PROJECT_NAME/openai/api_key"        --value "$OPENAI_API_KEY"        --type SecureString --overwrite
aws ssm put-parameter --region "$AWS_REGION" --name "/$PROJECT_NAME/tavily/api_key"        --value "$TAVILY_API_KEY"        --type SecureString --overwrite
aws ssm put-parameter --region "$AWS_REGION" --name "/$PROJECT_NAME/redis/url"             --value "$REDIS_URL"             --type SecureString --overwrite

# Optional secrets (only set if present)
info "Seeding optional secrets if present..."
[ -n "${AUTH0_DOMAIN:-}" ]                 && aws ssm put-parameter --region "$AWS_REGION" --name "/$PROJECT_NAME/auth0/domain"                 --value "$AUTH0_DOMAIN"                 --type SecureString --overwrite || true
[ -n "${AUTH0_AUDIENCE:-}" ]               && aws ssm put-parameter --region "$AWS_REGION" --name "/$PROJECT_NAME/auth0/audience"               --value "$AUTH0_AUDIENCE"               --type SecureString --overwrite || true
[ -n "${AUTH0_CLIENT_ID:-}" ]              && aws ssm put-parameter --region "$AWS_REGION" --name "/$PROJECT_NAME/auth0/client_id"              --value "$AUTH0_CLIENT_ID"              --type SecureString --overwrite || true
[ -n "${AUTH0_CLIENT_SECRET:-}" ]          && aws ssm put-parameter --region "$AWS_REGION" --name "/$PROJECT_NAME/auth0/client_secret"          --value "$AUTH0_CLIENT_SECRET"          --type SecureString --overwrite || true
[ -n "${AGENT_MEMORY_SERVER_URL:-}" ]      && aws ssm put-parameter --region "$AWS_REGION" --name "/$PROJECT_NAME/agent-memory-server/url"      --value "$AGENT_MEMORY_SERVER_URL"      --type SecureString --overwrite || true
[ -n "${AGENT_MEMORY_SERVER_API_KEY:-}" ]  && aws ssm put-parameter --region "$AWS_REGION" --name "/$PROJECT_NAME/agent-memory-server/api-key"  --value "$AGENT_MEMORY_SERVER_API_KEY"  --type SecureString --overwrite || true

info "Done."

