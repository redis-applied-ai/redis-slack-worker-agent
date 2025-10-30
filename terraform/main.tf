# Main Terraform configuration for Applied AI Agent

# Configure the AWS Provider
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project    = var.project_name
      ManagedBy  = "terraform"
      Repository = "https://github.com/redis-applied-ai/redis-slack-worker-agent"
    }
  }
}

# Data sources for existing resources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Default VPC data (used when var.use_default_vpc=true)
data "aws_vpc" "default" {
  count   = var.use_default_vpc ? 1 : 0
  default = true
}

data "aws_subnets" "default" {
  count = var.use_default_vpc ? 1 : 0
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default[0].id]
  }
}

# VPC Module (skipped when using default VPC)
module "vpc" {
  count  = var.use_default_vpc ? 0 : 1
  source = "./modules/vpc"

  project_name = var.project_name
  vpc_cidr     = var.vpc_cidr
  azs          = var.availability_zones
  single_az    = var.single_az
}

# Security groups when using default VPC
resource "aws_security_group" "alb_default" {
  count  = var.use_default_vpc ? 1 : 0
  name   = "${var.project_name}-alb"
  vpc_id = data.aws_vpc.default[0].id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "ecs_default" {
  count  = var.use_default_vpc ? 1 : 0
  name   = "${var.project_name}-ecs"
  vpc_id = data.aws_vpc.default[0].id

  ingress {
    description     = "Application port"
    from_port       = var.app_port
    to_port         = var.app_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb_default[0].id]
  }

  ingress {
    description     = "Memory server port"
    from_port       = var.memory_server_port
    to_port         = var.memory_server_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb_default[0].id]
  }

  # Allow ECS services to talk to the memory server over the internal network
  ingress {
    description = "ECS inter-service access to memory server"
    from_port   = var.memory_server_port
    to_port     = var.memory_server_port
    protocol    = "tcp"
    self        = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Common locals for networking
locals {
  vpc_id          = var.use_default_vpc ? data.aws_vpc.default[0].id : module.vpc[0].vpc_id
  public_subnets  = var.use_default_vpc ? data.aws_subnets.default[0].ids : module.vpc[0].public_subnets
  private_subnets = var.use_default_vpc ? data.aws_subnets.default[0].ids : module.vpc[0].private_subnets
  security_groups = var.use_default_vpc ? {
    alb = aws_security_group.alb_default[0].id
    ecs = aws_security_group.ecs_default[0].id
  } : module.vpc[0].security_groups
}

# ECR Module
module "ecr" {
  source = "./modules/ecr"

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

  project_name = var.project_name
  bucket_name  = var.bucket_name
}

# Domain Module (if domain_name is provided)
module "domain" {
  count  = var.domain_name != "" ? 1 : 0
  source = "./modules/domain"

  domain_name  = var.domain_name
  project_name = var.project_name
  # Route53 alias to ALB is optional and created later to avoid dependency cycles
  # create_alias = true
  # alb_dns_name = module.alb.alb_dns_name
  # alb_zone_id  = module.alb.alb_zone_id
}

# IAM Module
module "iam" {
  source = "./modules/iam"

  project_name = var.project_name
  account_id   = data.aws_caller_identity.current.account_id
  region       = data.aws_region.current.name
  bucket_name  = var.bucket_name
}

# ALB Module
module "alb" {
  source = "./modules/alb"

  project_name    = var.project_name
  vpc_id          = local.vpc_id
  subnets         = local.public_subnets
  security_groups = local.security_groups

  # SSL configuration
  certificate_arn = var.domain_name != "" ? module.domain[0].certificate_arn : ""
  domain_name     = var.domain_name != "" ? module.domain[0].domain_name : ""
}

# ECS Module
module "ecs" {
  source = "./modules/ecs"

  project_name    = var.project_name
  vpc_id          = local.vpc_id
  subnets         = local.private_subnets
  security_groups = local.security_groups
  assign_public_ip = var.use_default_vpc

  # ECR repositories
  ecr_repositories = module.ecr.repository_urls

  # IAM roles
  task_execution_role_arn = module.iam.ecs_task_execution_role_arn
  task_role_arn           = module.iam.ecs_task_role_arn

  # S3 bucket
  s3_bucket_name = var.bucket_name

  # Domain name
  domain_name = var.domain_name != "" ? module.domain[0].domain_name : ""

  # Environment variables
  environment_variables = var.environment_variables

  # Target groups (created by ALB module)
  alb_api_target_group_arn           = module.alb.api_target_group_arn
  alb_memory_server_target_group_arn = module.alb.memory_server_target_group_arn

  # Auto scaling configuration
  max_capacity     = var.max_capacity
  min_capacity     = var.min_capacity
  desired_capacity = var.desired_capacity

  # Additional required variables
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name
}

# Monitoring Module
module "monitoring" {
  source = "./modules/monitoring"

  project_name     = var.project_name
  ecs_cluster_name = module.ecs.cluster_name
  ecs_service_name = module.ecs.api_service_name
  alb_arn          = module.alb.alb_arn
}
