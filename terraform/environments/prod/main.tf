# Production Environment Configuration

module "applied_ai_agent" {
  source = "../../"

  environment = "prod"
  aws_region  = "us-east-2"

  # VPC Configuration
  vpc_cidr           = "10.2.0.0/16"
  availability_zones = ["us-east-2a", "us-east-2b"]

  # S3 Configuration
  bucket_name = "prod-applied-ai-agent"

  # Auto Scaling Configuration (cost-effective for production)
  max_capacity     = 5
  min_capacity     = 1
  desired_capacity = 2

  # Cost Optimization
  single_az                  = false
  enable_detailed_monitoring = true

  # Application Configuration
  app_port           = 3000
  memory_server_port = 8000
  cpu_units          = 1024
  memory_units       = 2048

  # SSL Configuration (required for production)
  # domain_name = "your-domain.com"
  # certificate_arn = "arn:aws:acm:us-east-2:ACCOUNT:certificate/CERT-ID"
}
