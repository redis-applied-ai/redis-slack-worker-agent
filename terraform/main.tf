# Main Terraform configuration for Applied AI Agent

# Configure the AWS Provider
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "applied-ai-agent"
      Environment = var.environment
      ManagedBy   = "terraform"
      Repository  = "https://github.com/your-org/applied-ai-agent"
    }
  }
}

# Data sources for existing resources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# VPC Module
module "vpc" {
  source = "./modules/vpc"

  environment = var.environment
  project_name = var.project_name
  vpc_cidr    = var.vpc_cidr
  azs         = var.availability_zones
  single_az   = var.single_az
}

# ECR Module
module "ecr" {
  source = "./modules/ecr"

  environment = var.environment
  project_name = var.project_name
  repositories = [
    var.project_name,
    "${var.project_name}-api",
    "${var.project_name}-worker",
    "agent-memory-server"
  ]
}

# S3 Module
module "s3" {
  source = "./modules/s3"

  environment = var.environment
  bucket_name = var.bucket_name
}

# Domain Module (if domain_name is provided)
module "domain" {
  count = var.domain_name != "" ? 1 : 0
  source = "./modules/domain"

  domain_name = var.domain_name
  environment = var.environment
  project_name = var.project_name
  alb_dns_name = module.alb.alb_dns_name
  alb_zone_id = module.alb.alb_zone_id
}

# IAM Module
module "iam" {
  source = "./modules/iam"

  environment = var.environment
  project_name = var.project_name
  account_id  = data.aws_caller_identity.current.account_id
  region      = data.aws_region.current.name
  bucket_name = var.bucket_name
}

# ALB Module
module "alb" {
  source = "./modules/alb"

  environment = var.environment
  project_name = var.project_name
  vpc_id      = module.vpc.vpc_id
  subnets     = module.vpc.public_subnets
  security_groups = module.vpc.security_groups

  # SSL configuration
  certificate_arn = var.domain_name != "" ? module.domain[0].certificate_arn : ""
  domain_name     = var.domain_name != "" ? module.domain[0].domain_name : ""
}

# ECS Module
module "ecs" {
  source = "./modules/ecs"

  environment = var.environment
  project_name = var.project_name
  vpc_id      = module.vpc.vpc_id
  subnets     = module.vpc.private_subnets
  security_groups = module.vpc.security_groups

  # ECR repositories
  ecr_repositories = module.ecr.repository_urls

  # IAM roles
  task_execution_role_arn = module.iam.ecs_task_execution_role_arn
  task_role_arn          = module.iam.ecs_task_role_arn

  # S3 bucket
  s3_bucket_name = var.bucket_name

  # Domain name
  domain_name = var.domain_name != "" ? module.domain[0].domain_name : ""

  # Environment variables
  environment_variables = var.environment_variables

  # Target groups (created by ALB module)
  alb_api_target_group_arn = module.alb.api_target_group_arn
  alb_memory_server_target_group_arn = module.alb.memory_server_target_group_arn

  # Auto scaling configuration
  max_capacity = var.max_capacity
  min_capacity = var.min_capacity
  desired_capacity = var.desired_capacity

  # Additional required variables
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name
}

# Monitoring Module
module "monitoring" {
  source = "./modules/monitoring"

  environment = var.environment
  project_name = var.project_name
  ecs_cluster_name = module.ecs.cluster_name
  ecs_service_name = module.ecs.api_service_name
  alb_arn = module.alb.alb_arn
}
