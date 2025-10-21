# Terraform Security and Setup Guide

## Security Best Practices

### 1. Secrets Management

**All secrets are externalized and NOT stored in Terraform files.** Secrets are managed through AWS Systems Manager Parameter Store (SSM).

#### Required Secrets (Set in AWS SSM Parameter Store)

Before deploying, create the following parameters in AWS SSM:

```bash
# For each environment (dev, stage, prod), create:
aws ssm put-parameter --name "/{environment}/redis/url" --value "redis://..." --type "SecureString"
aws ssm put-parameter --name "/{environment}/openai/api_key" --value "sk-..." --type "SecureString"
aws ssm put-parameter --name "/{environment}/tavily/api_key" --value "..." --type "SecureString"
aws ssm put-parameter --name "/{environment}/slack/bot_token" --value "xoxb-..." --type "SecureString"
aws ssm put-parameter --name "/{environment}/slack/signing_secret" --value "..." --type "SecureString"
aws ssm put-parameter --name "/{environment}/auth0/domain" --value "..." --type "SecureString"
aws ssm put-parameter --name "/{environment}/auth0/audience" --value "..." --type "SecureString"
aws ssm put-parameter --name "/{environment}/auth0/client_id" --value "..." --type "SecureString"
aws ssm put-parameter --name "/{environment}/auth0/client_secret" --value "..." --type "SecureString"
aws ssm put-parameter --name "/{environment}/agent-memory-server/url" --value "..." --type "SecureString"
aws ssm put-parameter --name "/{environment}/agent-memory-server/api-key" --value "..." --type "SecureString"
```

### 2. Terraform State Files

**IMPORTANT:** Terraform state files contain sensitive information and should NEVER be committed to version control.

- `.gitignore` already excludes `terraform/` directory
- State files are automatically ignored
- For production, use remote state with encryption:
  - S3 backend with versioning and encryption
  - DynamoDB for state locking

### 3. Reserved Project Names

The project name `applied-ai-agent-worker` is **reserved for the Applied AI team**. 

When deploying, choose a unique project name for your organization:
- ✅ Good: `my-company-ai-agent`, `acme-ai-worker`, `custom-agent`
- ❌ Reserved: `applied-ai-agent-worker`

## Setup Instructions

### Prerequisites

1. AWS Account with appropriate permissions
2. Terraform >= 1.0
3. AWS CLI configured with credentials
4. Appropriate IAM permissions for ECS, ECR, VPC, ALB, IAM, S3, CloudWatch, etc.

### Step 1: Configure Variables

Copy the example file and customize:

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
```

Edit `terraform/terraform.tfvars`:

```hcl
environment = "dev"
project_name = "my-ai-agent"  # Change this to your project name
bucket_name = "dev-my-ai-agent"  # Must be globally unique
aws_region = "us-east-2"
vpc_cidr = "10.0.0.0/16"
availability_zones = ["us-east-2a", "us-east-2b"]

# Optional: Add domain and SSL certificate
# domain_name = "your-domain.com"
# certificate_arn = "arn:aws:acm:us-east-2:ACCOUNT:certificate/CERT-ID"
```

### Step 2: Set Up Secrets in AWS SSM

Create all required secrets in AWS Systems Manager Parameter Store (see section above).

### Step 3: Initialize and Deploy

```bash
cd terraform

# Initialize Terraform
terraform init

# Validate configuration
terraform validate

# Create a plan
terraform plan -out=tfplan

# Review the plan, then apply
terraform apply tfplan
```

### Step 4: Verify Deployment

```bash
# Check ECS cluster
aws ecs list-clusters

# Check ECR repositories
aws ecr describe-repositories

# Check S3 bucket
aws s3 ls | grep your-bucket-name
```

## File Structure

```
terraform/
├── main.tf                 # Main configuration
├── variables.tf            # Variable definitions
├── outputs.tf              # Output definitions
├── versions.tf             # Provider versions
├── terraform.tfvars        # ⚠️ DO NOT COMMIT - Local variables
├── terraform.tfvars.example # Template for terraform.tfvars
├── deploy.sh               # Deployment helper script
├── modules/
│   ├── vpc/               # VPC, subnets, security groups
│   ├── ecr/               # ECR repositories
│   ├── ecs/               # ECS cluster, services, tasks
│   ├── alb/               # Application Load Balancer
│   ├── iam/               # IAM roles and policies
│   ├── s3/                # S3 bucket configuration
│   ├── domain/            # Route53 and ACM (optional)
│   └── monitoring/        # CloudWatch dashboards and alarms
└── environments/          # Environment-specific configs (optional)
```

## Customization

### Changing Resource Names

All resource names are generated using the `project_name` variable. To customize:

1. Update `project_name` in `terraform.tfvars`
2. All resources will automatically use the new name

Example: If `project_name = "acme-ai"`, resources will be named:
- ECS Cluster: `dev-acme-ai-cluster`
- ECR Repos: `dev-acme-ai`, `dev-acme-ai-api`, `dev-acme-ai-worker`
- S3 Bucket: `dev-acme-ai` (must be globally unique)
- VPC: `dev-acme-ai-vpc`

### Adding SSL/TLS

To enable HTTPS:

1. Create an ACM certificate in AWS
2. Update `terraform.tfvars`:
   ```hcl
   domain_name = "your-domain.com"
   certificate_arn = "arn:aws:acm:us-east-2:ACCOUNT:certificate/CERT-ID"
   ```
3. Ensure Route53 hosted zone exists for your domain
4. Re-apply Terraform

## Troubleshooting

### State Lock Issues

If Terraform is stuck on a lock:

```bash
terraform force-unlock <LOCK_ID>
```

### Destroying Resources

To remove all infrastructure:

```bash
terraform destroy
```

**Warning:** This will delete all resources including the S3 bucket and its contents.

## Additional Resources

- [Terraform AWS Provider Documentation](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [AWS ECS Best Practices](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/best_practices.html)
- [AWS Security Best Practices](https://aws.amazon.com/architecture/security-identity-compliance/)

