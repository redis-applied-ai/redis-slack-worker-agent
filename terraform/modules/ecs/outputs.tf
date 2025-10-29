# Outputs for ECS Module

output "cluster_id" {
  description = "ID of the ECS cluster"
  value       = aws_ecs_cluster.main.id
}

output "cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.main.name
}


output "memory_server_task_definition_arn" {
  description = "ARN of the memory server ECS task definition"
  value       = aws_ecs_task_definition.memory_server.arn
}

output "api_service_name" {
  description = "Name of the API ECS service"
  value       = aws_ecs_service.api.name
}

output "api_task_definition_arn" {
  description = "ARN of the API ECS task definition"
  value       = aws_ecs_task_definition.api.arn
}

output "worker_service_name" {
  description = "Name of the Worker ECS service"
  value       = aws_ecs_service.worker.name
}

output "worker_task_definition_arn" {
  description = "ARN of the Worker ECS task definition"
  value       = aws_ecs_task_definition.worker.arn
}


