# Environment Configuration Guide

This guide explains how to manage environment variables and configuration across dev/stage/prod environments.

## 📁 Configuration Files

Each environment has its own `terraform.tfvars` file:

- `environments/dev/terraform.tfvars` - Development environment
- `environments/stage/terraform.tfvars` - Staging environment  
- `environments/prod/terraform.tfvars` - Production environment

## 🔧 Non-Secret Variables

All non-secret environment variables are defined in the `terraform.tfvars` files under the `environment_variables` section:

```hcl
environment_variables = {
  # Slack Configuration
  SLACK_BOT_TOKEN = "xoxb-your-slack-bot-token"
  
  # Application URLs
  BASE_URL = "https://dev-applied-ai-agent.redisvl.com"
  FORCE_HTTPS = "true"
  
  # Agent Memory Server
  AGENT_MEMORY_SERVER_URL = "http://dev-agent-memory-server-service:8000"
  
  # OpenTelemetry Configuration
  OTLP_ENDPOINT = "http://localhost:4318"
  OTEL_SERVICE_NAME = "dev-slack-rag-bot"
  
  # Add more variables as needed
  LOG_LEVEL = "INFO"
  DEBUG_MODE = "false"
}
```

## 🔐 Secret Variables

Secret variables are stored in AWS Systems Manager Parameter Store and referenced in the ECS task definitions:

- `/dev/auth0/domain`
- `/dev/auth0/audience`
- `/dev/auth0/client_id`
- `/dev/auth0/client_secret`
- `/dev/redis/url`
- `/dev/slack/signing_secret`
- `/dev/tavily/api_key`

## 🚀 How to Update Variables

### Non-Secret Variables
1. Edit the appropriate `terraform.tfvars` file
2. Run `terraform plan` to see changes
3. Run `terraform apply` to apply changes

### Secret Variables
1. Update the SSM parameter:
   ```bash
   aws ssm put-parameter --name '/dev/slack/signing_secret' --value 'new-secret' --overwrite
   ```
2. Restart the ECS service to pick up new secrets:
   ```bash
   aws ecs update-service --cluster dev-applied-ai-agent-cluster --service dev-applied-ai-agent-service --force-new-deployment
   ```

## 📋 Environment-Specific Settings

### Development
- **Domain**: `dev-applied-ai-agent.redisvl.com`
- **Scaling**: 1-2 tasks
- **Cost Optimization**: Single AZ, minimal monitoring

### Staging  
- **Domain**: `stage-applied-ai-agent.redisvl.com`
- **Scaling**: 1-3 tasks
- **Cost Optimization**: Multi-AZ, standard monitoring

### Production
- **Domain**: `applied-ai-agent.redisvl.com`
- **Scaling**: 2-5 tasks
- **Cost Optimization**: Multi-AZ, standard monitoring

## 🔄 Adding New Variables

1. **Non-Secret Variables**:
   - Add to `environment_variables` in `terraform.tfvars`
   - Update all environments (dev/stage/prod)

2. **Secret Variables**:
   - Add to ECS task definition secrets section
   - Create SSM parameter for each environment
   - Update IAM policies if needed

## 📝 Best Practices

- Keep all non-secret variables in `terraform.tfvars` files
- Use descriptive names for environment variables
- Document new variables in this README
- Test changes in dev before applying to stage/prod
- Use consistent naming across all environments
