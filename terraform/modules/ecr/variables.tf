# Variables for ECR Module

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "repositories" {
  description = "List of ECR repository names"
  type        = list(string)
  default     = ["applied-ai-agent", "applied-ai-agent-api", "applied-ai-agent-worker", "agent-memory-server"]
}

