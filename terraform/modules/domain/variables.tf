# Domain Module Variables

variable "domain_name" {
  description = "The root domain name (e.g., redisvl.com)"
  type        = string
}


variable "project_name" {
  description = "Project name prefix for resources"
  type        = string
}

variable "alb_dns_name" {
  description = "DNS name of the ALB"
  type        = string
  default     = ""
}

variable "alb_zone_id" {
  description = "Zone ID of the ALB"
  type        = string
  default     = ""
}

variable "create_alias" {
  description = "Whether to create Route53 A alias to the ALB"
  type        = bool
  default     = false
}



