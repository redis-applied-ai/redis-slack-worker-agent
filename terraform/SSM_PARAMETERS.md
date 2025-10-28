# AWS SSM Parameters (single‑project)

These are the required SSM Parameter Store entries expected by the Terraform ECS tasks after simplifying to a single project (no environments). Replace <project_name> if you changed the default; otherwise it is applied-ai-agent-worker.

Parameter names (Strings, stored as SecureString):

- /<project_name>/redis/url
- /<project_name>/openai/api_key
- /<project_name>/tavily/api_key
- /<project_name>/slack/bot_token
- /<project_name>/slack/signing_secret
- /<project_name>/agent-memory-server/url
- /<project_name>/agent-memory-server/api-key

Optional (only if you enabled Auth0 in your app):
- /<project_name>/auth0/domain
- /<project_name>/auth0/audience
- /<project_name>/auth0/client_id
- /<project_name>/auth0/client_secret

Notes:
- The ECS task IAM policy allows read access to arn:aws:ssm:<region>:<account_id>:parameter/<project_name>/*
- You can set these via AWS Console or the CLI. Example:
  aws ssm put-parameter --name "/applied-ai-agent-worker/slack/bot_token" --type SecureString --value "xoxb-..." --overwrite

