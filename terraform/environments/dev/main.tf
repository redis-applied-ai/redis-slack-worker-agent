# Development Environment Configuration

module "applied_ai_agent" {
  source = "../../"

  # All variables are now defined in terraform.tfvars
  # This makes it easy to see and update all non-secret values

  # Pass all variables from terraform.tfvars
  environment                = var.environment
  aws_region                 = var.aws_region
  vpc_cidr                   = var.vpc_cidr
  availability_zones         = var.availability_zones
  bucket_name                = var.bucket_name
  domain_name                = var.domain_name
  max_capacity               = var.max_capacity
  min_capacity               = var.min_capacity
  desired_capacity           = var.desired_capacity
  app_port                   = var.app_port
  memory_server_port         = var.memory_server_port
  cpu_units                  = var.cpu_units
  memory_units               = var.memory_units
  single_az                  = var.single_az
  enable_detailed_monitoring = var.enable_detailed_monitoring
  environment_variables      = var.environment_variables
}
