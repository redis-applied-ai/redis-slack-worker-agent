# Variables for ECS Module

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "project_name" {
  description = "Project name prefix for resources"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "subnets" {
  description = "List of subnet IDs"
  type        = list(string)
}

variable "security_groups" {
  description = "Map of security group IDs"
  type = object({
    alb = string
    ecs = string
  })
}

variable "ecr_repositories" {
  description = "Map of ECR repository URLs"
  type        = map(string)
}

variable "task_execution_role_arn" {
  description = "ARN of the ECS task execution role"
  type        = string
}

variable "task_role_arn" {
  description = "ARN of the ECS task role"
  type        = string
}

variable "s3_bucket_name" {
  description = "Name of the S3 bucket"
  type        = string
}


variable "max_capacity" {
  description = "Maximum number of ECS tasks"
  type        = number
}

variable "min_capacity" {
  description = "Minimum number of ECS tasks"
  type        = number
}

variable "desired_capacity" {
  description = "Desired number of ECS tasks"
  type        = number
}

variable "app_port" {
  description = "Port the application runs on"
  type        = number
  default     = 3000
}

variable "memory_server_port" {
  description = "Port the memory server runs on"
  type        = number
  default     = 8000
}

variable "cpu_units" {
  description = "CPU units for ECS tasks"
  type        = number
  default     = 1024
}

variable "memory_units" {
  description = "Memory units for ECS tasks"
  type        = number
  default     = 2048
}

variable "region" {
  description = "AWS region"
  type        = string
}

variable "account_id" {
  description = "AWS Account ID"
  type        = string
}

variable "domain_name" {
  description = "Domain name for the application"
  type        = string
  default     = ""
}

variable "environment_variables" {
  description = "Map of non-secret environment variables for ECS tasks"
  type        = map(string)
  default     = {}
}

variable "alb_memory_server_target_group_arn" {
  description = "ARN of the ALB target group for the agent memory server"
  type        = string
}

variable "alb_api_target_group_arn" {
  description = "ARN of the ALB target group for the API service"
  type        = string
}

variable "api_cpu_units" {
  description = "CPU units for API ECS tasks"
  type        = number
  default     = 1024
}

variable "api_memory_units" {
  description = "Memory units for API ECS tasks"
  type        = number
  default     = 2048
}

variable "worker_cpu_units" {
  description = "CPU units for Worker ECS tasks"
  type        = number
  default     = 512
}

variable "worker_memory_units" {
  description = "Memory units for Worker ECS tasks"
  type        = number
  default     = 1024
}

variable "worker_desired_capacity" {
  description = "Desired number of worker ECS tasks"
  type        = number
  default     = 1
}
