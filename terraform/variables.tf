# Variables for Applied AI Agent Terraform configuration

variable "project_name" {
  description = "Project name prefix for all resources (e.g., 'my-ai-agent'). Reserved: 'applied-ai-agent-worker' is reserved for the Applied AI team."
  type        = string
  validation {
    condition     = !startswith(var.project_name, "applied-ai-agent-worker")
    error_message = "Project name cannot start with 'applied-ai-agent-worker' as it is reserved for the Applied AI team."
  }
}

variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-2"
}

variable "environment" {
  description = "Environment name (dev, stage, prod)"
  type        = string
  validation {
    condition     = contains(["dev", "stage", "prod"], var.environment)
    error_message = "Environment must be one of: dev, stage, prod."
  }
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of availability zones"
  type        = list(string)
  default     = ["us-east-2a", "us-east-2b"]
}

variable "bucket_name" {
  description = "S3 bucket name for content management"
  type        = string
}

variable "domain_name" {
  description = "Domain name for the application"
  type        = string
  default     = ""
}

variable "certificate_arn" {
  description = "ARN of SSL certificate for HTTPS"
  type        = string
  default     = ""
}

# Auto scaling variables
variable "max_capacity" {
  description = "Maximum number of ECS tasks"
  type        = number
  default     = 3
}

variable "min_capacity" {
  description = "Minimum number of ECS tasks"
  type        = number
  default     = 1
}

variable "desired_capacity" {
  description = "Desired number of ECS tasks"
  type        = number
  default     = 1
}

# Application configuration
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

# Cost optimization flags
variable "single_az" {
  description = "Use single AZ for cost optimization"
  type        = bool
  default     = false
}

variable "enable_detailed_monitoring" {
  description = "Enable detailed monitoring (costs more)"
  type        = bool
  default     = false
}

variable "environment_variables" {
  description = "Map of non-secret environment variables for ECS tasks"
  type        = map(string)
  default     = {}
}
