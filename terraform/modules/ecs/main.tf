# ECS Module for Applied AI Agent

# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "${var.project_name}-cluster"
  }
}

# Service Discovery Namespace
resource "aws_service_discovery_private_dns_namespace" "main" {
  name        = "local"
  description = "Private DNS namespace for service discovery"
  vpc         = var.vpc_id

  tags = {
    Name = "${var.project_name}-service-discovery"
  }
}

# Service Discovery Service for Agent Memory Server
# Note: This resource is managed externally to avoid conflicts with running instances
# Uncomment and manage if needed, but be aware that deletion requires all instances to be deregistered first
# resource "aws_service_discovery_service" "agent_memory_server" {
#   name = "agent-memory-server"
#
#   dns_config {
#     namespace_id = aws_service_discovery_private_dns_namespace.main.id
#
#     dns_records {
#       ttl  = 60
#       type = "A"
#     }
#
#     routing_policy = "MULTIVALUE"
#   }
#
#   health_check_custom_config {
#     failure_threshold = 3
#   }
#
#   tags = {
#     Name = "${var.project_name}-agent-memory-server-discovery"
#   }
# }


# CloudWatch Log Group for API Service
resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.project_name}-api"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-api-logs"
  }
}

# CloudWatch Log Group for Worker Service
resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${var.project_name}-worker"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-worker-logs"
  }
}

# CloudWatch Log Group for Agent Memory Server
resource "aws_cloudwatch_log_group" "memory_server" {
  name              = "/ecs/${var.project_name}-agent-memory-server"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-agent-memory-server-logs"
  }
}


# ECS Task Definition for Agent Memory Server
resource "aws_ecs_task_definition" "memory_server" {
  family                   = "${var.project_name}-agent-memory-server-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 2048
  memory                   = 8192
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.task_role_arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "agent-memory-server"
      image     = "andrewbrookins510/agent-memory-server:0.9.3"
      essential = true

      portMappings = [
        {
          containerPort = var.memory_server_port
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "PORT"
          value = tostring(var.memory_server_port)
        },
        {
          name  = "LOG_LEVEL"
          value = "INFO"
        },
        {
          name  = "ENABLE_BACKGROUND_TASKS"
          value = "true"
        },
        {
          name  = "MAX_CONVERSATION_LENGTH"
          value = "50"
        },
        {
          name  = "MEMORY_CONSOLIDATION_ENABLED"
          value = "true"
        },
        {
          name  = "MEMORY_CONSOLIDATION_INTERVAL"
          value = "3600"
        },
        {
          name  = "AUTH_MODE"
          value = "token"
        },
        {
          name  = "DISABLE_AUTH"
          value = "true"
        },
        {
          name  = "CORS_ORIGINS"
          value = "*"
        },
        {
          name  = "WORKER_CONCURRENCY"
          value = "4"
        }
      ]

      secrets = [
        {
          name      = "REDIS_URL"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/redis/url"
        },
        {
          name      = "OPENAI_API_KEY"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/openai/api_key"
        },
        {
          name      = "TAVILY_API_KEY"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/tavily/api_key"
        },
        {
          name      = "AGENT_MEMORY_SERVER_API_KEY"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/agent-memory-server/api-key"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.memory_server.name
          awslogs-region        = var.region
          awslogs-stream-prefix = "ecs-memory-server"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:${var.memory_server_port}/v1/health || exit 1"]
        interval    = 60
        timeout     = 10
        retries     = 10
        startPeriod = 300
      }
    },
    {
      name      = "agent-memory-worker"
      image     = "andrewbrookins510/agent-memory-server:0.9.3"
      essential = true

      command = [
        "agent-memory",
        "task-worker"
      ]

      environment = [
        {
          name  = "LOG_LEVEL"
          value = "INFO"
        },
        {
          name  = "WORKER_CONCURRENCY"
          value = "2"
        },
        {
          name  = "MEMORY_CONSOLIDATION_ENABLED"
          value = "true"
        },
        {
          name  = "AUTH_MODE"
          value = "token"
        },
        {
          name  = "DISABLE_AUTH"
          value = "false"
        }
      ]

      secrets = [
        {
          name      = "REDIS_URL"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/redis/url"
        },
        {
          name      = "OPENAI_API_KEY"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/openai/api_key"
        },
        {
          name      = "TAVILY_API_KEY"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/tavily/api_key"
        },
        {
          name      = "AGENT_MEMORY_SERVER_API_KEY"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/agent-memory-server/api-key"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.memory_server.name
          awslogs-region        = var.region
          awslogs-stream-prefix = "worker"
        }
      }
    }
  ])

  tags = {
    Name = "${var.project_name}-agent-memory-server-task"
  }
}


# ECS Service for Agent Memory Server
resource "aws_ecs_service" "memory_server" {
  name            = "${var.project_name}-agent-memory-server-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.memory_server.family
  desired_count   = 1
  launch_type     = "FARGATE"

  enable_execute_command = true

  # Note: Service discovery is managed externally to avoid conflicts with running instances
  # Uncomment if needed:
  # service_registries {
  #   registry_arn = aws_service_discovery_service.agent_memory_server.arn
  # }

  network_configuration {
    subnets          = var.subnets
    security_groups  = [var.security_groups.ecs]
    assign_public_ip = var.assign_public_ip
  }

  load_balancer {
    target_group_arn = var.alb_memory_server_target_group_arn
    container_name   = "agent-memory-server"
    container_port   = 8000
  }

  tags = {
    Name = "${var.project_name}-agent-memory-server-service"
  }
}

# ECS Task Definition for API Service
resource "aws_ecs_task_definition" "api" {
  family                   = "${var.project_name}-api-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.api_cpu_units
  memory                   = var.api_memory_units
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.task_role_arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name    = "${var.project_name}-api"
      image   = "${var.ecr_repositories["${var.project_name}-api"]}:latest"
      cpu     = var.api_cpu_units
      memory  = var.api_memory_units
      command = ["python", "-m", "uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "3000"]

      portMappings = [
        {
          containerPort = var.app_port
          protocol      = "tcp"
        }
      ]


      environment = concat([
        {
          name  = "PORT"
          value = tostring(var.app_port)
        },
        {
          name  = "S3_BUCKET"
          value = var.s3_bucket_name
        },
        {
          name  = "BASE_URL"
          value = var.domain_name != "" ? "https://${var.domain_name}" : ""
        },
        {
          name  = "FORCE_HTTPS"
          value = var.domain_name != "" ? "true" : "false"
        },
        ], [
        for key, value in var.environment_variables : {
          name  = key
          value = value
        }
      ])

      secrets = [
        {
          name      = "AGENT_MEMORY_SERVER_URL"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/agent-memory-server/url"
        },
        {
          name      = "AGENT_MEMORY_SERVER_API_KEY"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/agent-memory-server/api-key"
        },
        {
          name      = "AUTH0_DOMAIN"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/auth0/domain"
        },
        {
          name      = "AUTH0_AUDIENCE"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/auth0/audience"
        },
        {
          name      = "AUTH0_CLIENT_ID"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/auth0/client_id"
        },
        {
          name      = "AUTH0_CLIENT_SECRET"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/auth0/client_secret"
        },
        {
          name      = "REDIS_URL"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/redis/url"
        },
        {
          name      = "OPENAI_API_KEY"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/openai/api_key"
        },
        {
          name      = "TAVILY_API_KEY"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/tavily/api_key"
        },
        {
          name      = "SLACK_BOT_TOKEN"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/slack/bot_token"
        },
        {
          name      = "SLACK_SIGNING_SECRET"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/slack/signing_secret"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.api.name
          awslogs-region        = var.region
          awslogs-stream-prefix = "api"
        }
      }
    },
  ])

  tags = {
    Name = "${var.project_name}-api-task"
  }
}

# ECS Task Definition for Worker Service
resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.project_name}-worker-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.worker_cpu_units
  memory                   = var.worker_memory_units
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.task_role_arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "${var.project_name}-worker"
      image     = "${var.ecr_repositories["${var.project_name}-worker"]}:latest"
      cpu       = var.worker_cpu_units
      memory    = var.worker_memory_units
      essential = true
      command   = ["python", "-m", "app.worker"]

      environment = [
        for key, value in var.environment_variables : {
          name  = key
          value = value
        }
      ]

      secrets = [
        {
          name      = "AGENT_MEMORY_SERVER_URL"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/agent-memory-server/url"
        },
        {
          name      = "AGENT_MEMORY_SERVER_API_KEY"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/agent-memory-server/api-key"
        },
        {
          name      = "REDIS_URL"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/redis/url"
        },
        {
          name      = "OPENAI_API_KEY"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/openai/api_key"
        },
        {
          name      = "TAVILY_API_KEY"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/tavily/api_key"
        },
        {
          name      = "SLACK_BOT_TOKEN"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.project_name}/slack/bot_token"
        }
      ]


      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.worker.name
          awslogs-region        = var.region
          awslogs-stream-prefix = "worker"
        }
      }
    },
  ])

  tags = {
    Name = "${var.project_name}-worker-task"
  }
}

# ECS Service for API
resource "aws_ecs_service" "api" {
  name            = "${var.project_name}-api-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.family
  desired_count   = var.desired_capacity
  launch_type     = "FARGATE"

  enable_execute_command = true

  network_configuration {
    subnets          = var.subnets
    security_groups  = [var.security_groups.ecs]
    assign_public_ip = var.assign_public_ip
  }

  load_balancer {
    target_group_arn = var.alb_api_target_group_arn
    container_name   = "${var.project_name}-api"
    container_port   = 3000
  }

  tags = {
    Name = "${var.project_name}-api-service"
  }
}

# ECS Service for Worker
resource "aws_ecs_service" "worker" {
  name            = "${var.project_name}-worker-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.family
  desired_count   = var.worker_desired_capacity
  launch_type     = "FARGATE"

  enable_execute_command = true

  network_configuration {
    subnets          = var.subnets
    security_groups  = [var.security_groups.ecs]
    assign_public_ip = var.assign_public_ip
  }

  tags = {
    Name = "${var.project_name}-worker-service"
  }
}

