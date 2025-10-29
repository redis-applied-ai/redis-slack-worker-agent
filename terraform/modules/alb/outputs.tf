# Outputs for ALB Module

output "alb_id" {
  description = "ID of the Application Load Balancer"
  value       = aws_lb.main.id
}

output "alb_arn" {
  description = "ARN of the Application Load Balancer"
  value       = aws_lb.main.arn
}

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = aws_lb.main.dns_name
}

output "alb_zone_id" {
  description = "Zone ID of the Application Load Balancer"
  value       = aws_lb.main.zone_id
}


output "memory_server_target_group_arn" {
  description = "ARN of the memory server target group"
  value       = aws_lb_target_group.memory_server.arn
}

output "memory_server_target_group_id" {
  description = "ID of the memory server target group"
  value       = aws_lb_target_group.memory_server.id
}

output "api_target_group_arn" {
  description = "ARN of the API target group"
  value       = aws_lb_target_group.api.arn
}

output "api_target_group_id" {
  description = "ID of the API target group"
  value       = aws_lb_target_group.api.id
}

