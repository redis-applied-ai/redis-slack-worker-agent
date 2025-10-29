# Variables for ECR Module


variable "repositories" {
  description = "List of ECR repository names (without environment prefix). Example: [\"my-ai-agent\", \"my-ai-agent-api\", \"my-ai-agent-worker\", \"agent-memory-server\"]"
  type        = list(string)
  default     = []
}

