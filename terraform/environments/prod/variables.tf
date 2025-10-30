# Variables for Production Environment
# Minimal declaration to pass through Bedrock/OpenAI provider env vars

variable "environment_variables" {
  description = "Map of non-secret environment variables for ECS tasks"
  type        = map(string)
  default     = {}
}

