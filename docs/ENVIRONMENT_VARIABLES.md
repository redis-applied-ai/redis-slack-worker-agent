# Environment Variables Reference

This document lists all environment variables used by the application, with focus on SSL and Auth0 configuration.

## SSL and Auth0 Configuration

### Required for Production

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `BASE_URL` | Base URL for the application (must use HTTPS in production) | `https://your-domain.com` | Yes |
| `FORCE_HTTPS` | Force secure cookies even if not detected | `true` | Yes |
| `AUTH0_DOMAIN` | Auth0 tenant domain | `your-tenant.auth0.com` | Yes |
| `AUTH0_AUDIENCE` | Auth0 API audience identifier | `https://your-domain.com/api` | Yes |
| `AUTH0_CLIENT_ID` | Auth0 application client ID | `abc123def456` | Yes |
| `AUTH0_CLIENT_SECRET` | Auth0 application client secret | `secret123` | Yes |

### Optional Auth0 Configuration

| Variable | Description | Example | Default |
|----------|-------------|---------|---------|
| `AUTH0_ISSUER` | Auth0 issuer URL (auto-generated if not set) | `https://your-tenant.auth0.com/` | Auto-generated |

## Application Configuration

### Core Application

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` | Yes |
| `OPENAI_API_KEY` | OpenAI API key | `sk-...` | Yes |
| `SLACK_BOT_TOKEN` | Slack bot token | `xoxb-...` | Yes |
| `SLACK_SIGNING_SECRET` | Slack signing secret | `secret` | Yes |

### Optional Features

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `TAVILY_API_KEY` | Tavily API key for web search | `tvly-...` | No |
| `AGENT_MEMORY_SERVER_URL` | Agent Memory Server base URL (Cloud Map or ALB) | `http://agent-memory-server.local:8000` or `http://<alb-dns>` | Yes (in cloud) |
| `AGENT_MEMORY_SERVER_API_KEY` | Token for Memory Server when auth is enabled | `your-strong-token` | Yes (in cloud) |


## Environment-Specific Examples

### Development
```bash
BASE_URL=http://localhost:3000
FORCE_HTTPS=false
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_AUDIENCE=https://your-domain.com/api
AUTH0_CLIENT_ID=your-dev-client-id
AUTH0_CLIENT_SECRET=your-dev-client-secret
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=sk-your-key
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_SIGNING_SECRET=your-secret
```

### Staging
```bash
BASE_URL=https://staging.your-domain.com
FORCE_HTTPS=true
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_AUDIENCE=https://your-domain.com/api
AUTH0_CLIENT_ID=your-staging-client-id
AUTH0_CLIENT_SECRET=your-staging-client-secret
REDIS_URL=redis://your-staging-redis:6379/0
OPENAI_API_KEY=sk-your-key
SLACK_BOT_TOKEN=xoxb-your-staging-token
SLACK_SIGNING_SECRET=your-staging-secret
```

### Production
```bash
BASE_URL=https://your-domain.com
FORCE_HTTPS=true
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_AUDIENCE=https://your-domain.com/api
AUTH0_CLIENT_ID=your-production-client-id
AUTH0_CLIENT_SECRET=your-production-client-secret
REDIS_URL=redis://your-production-redis:6379/0
OPENAI_API_KEY=sk-your-key
SLACK_BOT_TOKEN=xoxb-your-production-token
SLACK_SIGNING_SECRET=your-production-secret
```

## Security Notes

1. **Never commit secrets to version control**
2. **Use AWS Secrets Manager or Parameter Store for production secrets**
3. **Rotate secrets regularly**
4. **Use different Auth0 applications for different environments**
5. **Ensure BASE_URL uses HTTPS in production**

## Validation

You can validate your configuration using the debug endpoints:

```bash
# Check callback URL configuration
curl https://your-domain.com/debug/callback-url

# Check session state
curl https://your-domain.com/debug/session
```
