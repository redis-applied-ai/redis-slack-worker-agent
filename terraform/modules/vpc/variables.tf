# Variables for VPC Module


variable "project_name" {
  description = "Project name prefix for resources"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
}

variable "azs" {
  description = "List of availability zones"
  type        = list(string)
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

variable "single_az" {
  description = "Whether to use single AZ for cost optimization"
  type        = bool
  default     = false
}
