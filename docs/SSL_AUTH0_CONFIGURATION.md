# SSL and Auth0 Configuration for Production

This document outlines the SSL/TLS and Auth0 configuration required for deploying the content management API to production.

## Overview

The content management API requires HTTPS for production deployment due to:
- Auth0 security requirements for callback URLs
- JWT token transmission security
- Secure cookie handling
- Content management API security

## SSL Configuration

### 1. AWS Application Load Balancer (ALB) Setup

#### Prerequisites
- AWS Certificate Manager (ACM) certificate for your domain
- Application Load Balancer configured
- ECS service with target group

#### ALB Configuration Steps

1. **Create/Update ALB Listener Rules:**
   ```bash
   # Port 80 (HTTP) - Redirect to HTTPS
   aws elbv2 create-rule \
     --listener-arn arn:aws:elasticloadbalancing:region:account:listener/app/your-alb/xxx/xxx \
     --priority 1 \
     --conditions Field=path-pattern,Values='*' \
     --actions Type=redirect,RedirectConfig='{Protocol=HTTPS,Port=443,StatusCode=HTTP_301}'

   # Port 443 (HTTPS) - Forward to ECS
   aws elbv2 create-rule \
     --listener-arn arn:aws:elasticloadbalancing:region:account:listener/app/your-alb/xxx/xxx \
     --priority 2 \
     --conditions Field=path-pattern,Values='*' \
     --actions Type=forward,TargetGroupArn=arn:aws:elasticloadbalancing:region:account:targetgroup/your-tg/xxx
   ```

2. **Security Group Configuration:**
   - Allow inbound traffic on port 443 (HTTPS) from 0.0.0.0/0
   - Allow inbound traffic on port 80 (HTTP) from 0.0.0.0/0 (for redirects)
   - Allow outbound traffic to ECS service on port 3000

### 2. Environment Variables

The following environment variables must be configured in your ECS task definitions:

#### Required Variables
```bash
# Base URL for your application (must use HTTPS in production)
BASE_URL=https://your-domain.com

# Force HTTPS for cookie security
FORCE_HTTPS=true

# Auth0 Configuration
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_AUDIENCE=your-api-audience
AUTH0_CLIENT_ID=your-client-id
AUTH0_CLIENT_SECRET=your-client-secret
```

#### Optional Variables
```bash
# Override Auth0 issuer if different from domain
AUTH0_ISSUER=https://your-tenant.auth0.com/
```

## Auth0 Configuration

### 1. Application Settings

In your Auth0 Dashboard, update the following settings:

#### Allowed Callback URLs
```
https://your-domain.com/callback
https://your-staging-domain.com/callback
```

#### Allowed Logout URLs
```
https://your-domain.com/logout
https://your-staging-domain.com/logout
```

#### Allowed Web Origins
```
https://your-domain.com
https://your-staging-domain.com
```

#### Allowed Origins (CORS)
```
https://your-domain.com
https://your-staging-domain.com
```

### 2. API Configuration

#### Machine to Machine Application
1. Create a Machine to Machine application in Auth0
2. Authorize it for your API
3. Grant the following scopes:
   - `read:content` - Read content management data
   - `write:content` - Write content management data
   - `admin:content` - Full content management access

#### API Settings
- **Identifier**: `https://your-domain.com/api`
- **Signing Algorithm**: `RS256`
- **Token Expiration**: `24 hours` (recommended)

### 3. User Permissions

Configure the following permissions in Auth0:

```json
{
  "permissions": [
    "content:ingest",
    "content:process", 
    "content:manage",
    "content:read"
  ]
}
```

## Deployment Steps

### 1. Pre-Deployment Checklist

- [ ] SSL certificate obtained and configured in ALB
- [ ] ALB listener rules configured (HTTP → HTTPS redirect)
- [ ] ECS task definitions updated with environment variables
- [ ] Auth0 application settings updated with HTTPS URLs
- [ ] Security groups configured for HTTPS traffic

### 2. Environment-Specific Configuration

#### Staging Environment
```bash
BASE_URL=https://staging.your-domain.com
FORCE_HTTPS=true
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_AUDIENCE=your-api-audience
AUTH0_CLIENT_ID=your-staging-client-id
AUTH0_CLIENT_SECRET=your-staging-client-secret
```

#### Production Environment
```bash
BASE_URL=https://your-domain.com
FORCE_HTTPS=true
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_AUDIENCE=your-api-audience
AUTH0_CLIENT_ID=your-production-client-id
AUTH0_CLIENT_SECRET=your-production-client-secret
```

### 3. Testing

#### 1. SSL Certificate Validation
```bash
# Test SSL certificate
curl -I https://your-domain.com/health

# Test HTTP to HTTPS redirect
curl -I http://your-domain.com/health
# Should return 301 redirect to HTTPS
```

#### 2. Auth0 Integration Testing
```bash
# Test Auth0 login flow
curl -X GET "https://your-domain.com/login"

# Test callback URL
curl -X GET "https://your-domain.com/debug/callback-url"
# Should return the correct callback URL
```

#### 3. Content Management API Testing
```bash
# Test protected endpoints (should require authentication)
curl -X POST "https://your-domain.com/api/content/ingest" \
  -H "Authorization: Bearer YOUR_AUTH0_TOKEN"

curl -X POST "https://your-domain.com/api/content/vectorize" \
  -H "Authorization: Bearer YOUR_AUTH0_TOKEN"
```

## Security Considerations

### 1. Cookie Security
- Cookies are automatically set to `secure=True` when `FORCE_HTTPS=true`
- Session cookies are `httponly` and `samesite=lax` for security

### 2. JWT Token Security
- Tokens are only transmitted over HTTPS
- Token validation includes signature verification
- Tokens have appropriate expiration times

### 3. CORS Configuration
- Only configured domains are allowed
- Credentials are included for authenticated requests

## Troubleshooting

### Common Issues

#### 1. "Invalid Callback URL" Error
- **Cause**: Auth0 callback URL doesn't match configured URLs
- **Solution**: Update Auth0 application settings with correct HTTPS URLs

#### 2. "Secure Cookie" Warnings
- **Cause**: Application trying to set secure cookies over HTTP
- **Solution**: Ensure `FORCE_HTTPS=true` and ALB is configured for HTTPS

#### 3. "CORS" Errors
- **Cause**: Origin not allowed in Auth0 settings
- **Solution**: Add your domain to Auth0 CORS settings

#### 4. SSL Certificate Issues
- **Cause**: Certificate not properly configured or expired
- **Solution**: Check ACM certificate status and ALB listener configuration

### Debug Endpoints

The application provides debug endpoints for troubleshooting:

```bash
# Check callback URL configuration
GET https://your-domain.com/debug/callback-url

# Check session state
GET https://your-domain.com/debug/session
```

## Monitoring

### 1. SSL Certificate Monitoring
- Set up CloudWatch alarms for certificate expiration
- Monitor ALB health checks

### 2. Auth0 Monitoring
- Monitor failed authentication attempts
- Track token usage and errors

### 3. Application Monitoring
- Monitor HTTPS traffic patterns
- Track authentication success/failure rates

## Rollback Plan

If issues occur after deployment:

1. **Immediate Rollback**: Revert to previous task definition
2. **Auth0 Rollback**: Revert Auth0 settings to previous configuration
3. **ALB Rollback**: Revert ALB listener rules if needed

## Support

For issues with this configuration:
1. Check CloudWatch logs for application errors
2. Verify Auth0 dashboard for authentication issues
3. Test SSL configuration with external tools
4. Review ALB access logs for traffic patterns
