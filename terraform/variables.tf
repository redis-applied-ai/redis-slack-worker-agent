# Variables for Applied AI Agent Terraform configuration

variable "project_name" {
  description = "Project name prefix for all resources (e.g., 'applied-ai-agent-worker')."
  type        = string
  default     = "applied-ai-agent-worker"
}

variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

# Network selection
variable "use_default_vpc" {
  description = "Use the account's default VPC and its subnets instead of creating a new VPC"
  type        = bool
  default     = false
}

variable "vpc_cidr" {
  description = "CIDR block for VPC (ignored when use_default_vpc=true)"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of availability zones (ignored when use_default_vpc=true)"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
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
  description = "Use single AZ for cost optimization (ignored when use_default_vpc=true)"
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
