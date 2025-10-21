# Variables for Dev Environment
# These variables are defined in terraform.tfvars

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "aws_region" {
  description = "AWS region for resources"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
}

variable "availability_zones" {
  description = "List of availability zones"
  type        = list(string)
}

variable "bucket_name" {
  description = "S3 bucket name for content management"
  type        = string
}

variable "domain_name" {
  description = "Domain name for the application"
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
}

variable "memory_server_port" {
  description = "Port the memory server runs on"
  type        = number
}

variable "cpu_units" {
  description = "CPU units for ECS tasks"
  type        = number
}

variable "memory_units" {
  description = "Memory units for ECS tasks"
  type        = number
}

variable "single_az" {
  description = "Use single AZ for cost optimization"
  type        = bool
}

variable "enable_detailed_monitoring" {
  description = "Enable detailed monitoring (costs more)"
  type        = bool
}

variable "environment_variables" {
  description = "Map of non-secret environment variables for ECS tasks"
  type        = map(string)
}


