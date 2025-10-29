# Outputs for Monitoring Module

output "log_group_name" {
  description = "Name of the API CloudWatch log group (managed by ECS module)"
  value       = "/ecs/${var.project_name}-api"
}

output "dashboard_url" {
  description = "URL of the CloudWatch dashboard"
  value       = "https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=${aws_cloudwatch_dashboard.main.dashboard_name}"
}
