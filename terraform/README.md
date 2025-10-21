# Applied AI Agent - Terraform Infrastructure

This directory contains the Terraform configuration for deploying the Applied AI Agent application to AWS.

## Architecture

The infrastructure is organized into modules:

- **VPC**: Virtual Private Cloud with public/private subnets
- **ECS**: Elastic Container Service with Fargate tasks
- **ALB**: Application Load Balancer with SSL termination
- **S3**: Object storage for content management
- **IAM**: Roles and policies for service permissions
- **ECR**: Container registry for Docker images
- **Monitoring**: CloudWatch logs, dashboards, and alarms

## Directory Structure

```
terraform/
├── main.tf                 # Main configuration
├── variables.tf            # Variable definitions
├── outputs.tf              # Output definitions
├── versions.tf             # Provider version constraints
├── terraform.tfvars.example # Example variables file
├── modules/                # Reusable modules
│   ├── vpc/               # VPC and networking
│   ├── ecs/               # ECS cluster and services
│   ├── alb/               # Application Load Balancer
│   ├── s3/                # S3 bucket configuration
│   ├── iam/               # IAM roles and policies
│   ├── ecr/               # ECR repositories
│   └── monitoring/        # CloudWatch monitoring
└── environments/          # Environment-specific configs
    ├── dev/              # Development environment
    ├── stage/            # Staging environment
    └── prod/             # Production environment
```

## Prerequisites

1. **Terraform**: Install Terraform >= 1.0
2. **AWS CLI**: Configure AWS credentials
3. **AWS Account**: With appropriate permissions

## Quick Start

1. **Copy the example variables file:**
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   ```

2. **Update the variables:**
   Edit `terraform.tfvars` with your specific values.

3. **Initialize Terraform:**
   ```bash
   terraform init
   ```

4. **Plan the deployment:**
   ```bash
   terraform plan
   ```

5. **Apply the configuration:**
   ```bash
   terraform apply
   ```

## Environment-Specific Deployment

### Development Environment
```bash
cd environments/dev
terraform init
terraform plan
terraform apply
```

### Staging Environment
```bash
cd environments/stage
terraform init
terraform plan
terraform apply
```

### Production Environment
```bash
cd environments/prod
terraform init
terraform plan
terraform apply
```

## Configuration

### Required Variables

- `environment`: Environment name (dev, stage, prod)
- `project_name`: Unique project identifier for resource naming (e.g., "my-ai-agent"). Note: "applied-ai-agent-worker" is reserved for the Applied AI team.
- `bucket_name`: S3 bucket name for content storage
- `aws_region`: AWS region for deployment

### Optional Variables

- `domain_name`: Custom domain name
- `certificate_arn`: SSL certificate ARN for HTTPS
- `max_capacity`: Maximum number of ECS tasks
- `min_capacity`: Minimum number of ECS tasks
- `desired_capacity`: Desired number of ECS tasks

## Secrets Management

Secrets are managed through AWS Systems Manager Parameter Store:

- `/{environment}/auth0/domain`
- `/{environment}/auth0/audience`
- `/{environment}/auth0/client_id`
- `/{environment}/auth0/client_secret`
- `/{environment}/redis/url`

## Cost Optimization

The configuration is optimized for cost-effectiveness:

- **Development**: Single AZ, minimal resources
- **Staging**: 1-3 tasks, basic monitoring
- **Production**: 1-5 tasks, essential monitoring

## Monitoring

CloudWatch dashboards and alarms are automatically created:

- ECS service metrics (CPU, Memory)
- ALB metrics (Response time, Error rate)
- Log aggregation and retention

## Security

- VPC with public/private subnets
- Security groups with least privilege
- IAM roles with minimal permissions
- S3 bucket encryption and access controls
- SSL/TLS termination at ALB

## GitHub Actions Integration

The Terraform configuration is designed to work with existing GitHub Actions workflows:

1. Secrets are stored in GitHub Secrets
2. Deploy scripts inject secrets into AWS Parameter Store
3. ECS tasks pull secrets from Parameter Store at runtime

## Troubleshooting

### Common Issues

1. **Permission Denied**: Ensure AWS credentials have sufficient permissions
2. **Resource Conflicts**: Check for existing resources with same names
3. **SSL Certificate**: Verify certificate ARN is correct and in the right region

### Useful Commands

```bash
# View current state
terraform show

# List resources
terraform state list

# Import existing resource
terraform import aws_s3_bucket.main bucket-name

# Destroy resources
terraform destroy
```

## Support

For issues or questions, please refer to the main project documentation or create an issue in the repository.
