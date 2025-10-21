# ECS Module for Applied AI Agent

# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "${var.environment}-${var.project_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "${var.environment}-${var.project_name}-cluster"
  }
}

# Service Discovery Namespace
resource "aws_service_discovery_private_dns_namespace" "main" {
  name        = "local"
  description = "Private DNS namespace for service discovery"
  vpc         = var.vpc_id

  tags = {
    Name = "${var.environment}-service-discovery"
  }
}

# Service Discovery Service for Agent Memory Server
resource "aws_service_discovery_service" "agent_memory_server" {
  name = "agent-memory-server"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id

    dns_records {
      ttl  = 60
      type = "A"
    }

    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 3
  }

  tags = {
    Name = "${var.environment}-agent-memory-server-discovery"
  }
}


# CloudWatch Log Group for API Service
resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.environment}-${var.project_name}-api"
  retention_in_days = 7

  tags = {
    Name = "${var.environment}-${var.project_name}-api-logs"
  }
}

# CloudWatch Log Group for Worker Service
resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${var.environment}-${var.project_name}-worker"
  retention_in_days = 7

  tags = {
    Name = "${var.environment}-${var.project_name}-worker-logs"
  }
}

# CloudWatch Log Group for Agent Memory Server
resource "aws_cloudwatch_log_group" "memory_server" {
  name              = "/ecs/${var.environment}-agent-memory-server"
  retention_in_days = 7

  tags = {
    Name = "${var.environment}-agent-memory-server-logs"
  }
}


# ECS Task Definition for Agent Memory Server
resource "aws_ecs_task_definition" "memory_server" {
  family                   = "${var.environment}-agent-memory-server-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 2048
  memory                   = 8192
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn           = var.task_role_arn

  container_definitions = jsonencode([
    {
      name  = "agent-memory-server"
      image = "andrewbrookins510/agent-memory-server:0.9.3"
      essential = true

      portMappings = [
        {
          containerPort = var.memory_server_port
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "ENVIRONMENT"
          value = var.environment
        },
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
          value = "false"
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
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/redis/url"
        },
        {
          name      = "OPENAI_API_KEY"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/openai/api_key"
        },
        {
          name      = "TAVILY_API_KEY"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/tavily/api_key"
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
        command = ["CMD-SHELL", "curl -f http://localhost:${var.memory_server_port}/v1/health || exit 1"]
        interval = 60
        timeout = 10
        retries = 10
        startPeriod = 300
      }
    },
    {
      name  = "agent-memory-worker"
      image = "andrewbrookins510/agent-memory-server:0.9.3"
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
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/redis/url"
        },
        {
          name      = "OPENAI_API_KEY"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/openai/api_key"
        },
        {
          name      = "TAVILY_API_KEY"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/tavily/api_key"
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
    Name = "${var.environment}-agent-memory-server-task"
  }
}


# ECS Service for Agent Memory Server
resource "aws_ecs_service" "memory_server" {
  name            = "${var.environment}-agent-memory-server-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.memory_server.family
  desired_count   = 1
  launch_type     = "FARGATE"

  enable_execute_command = true

  network_configuration {
    subnets          = var.subnets
    security_groups  = [var.security_groups.ecs]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = var.alb_memory_server_target_group_arn
    container_name   = "agent-memory-server"
    container_port   = 8000
  }

  tags = {
    Name = "${var.environment}-agent-memory-server-service"
  }
}

# ECS Task Definition for API Service
resource "aws_ecs_task_definition" "api" {
  family                   = "${var.environment}-${var.project_name}-api-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.api_cpu_units
  memory                   = var.api_memory_units
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn           = var.task_role_arn

  container_definitions = jsonencode([
    {
      name  = "applied-ai-agent-api"
      image = "${var.ecr_repositories["applied-ai-agent-api"]}:latest"
      cpu   = var.api_cpu_units
      memory = var.api_memory_units
      command = ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "3000"]

      portMappings = [
        {
          containerPort = var.app_port
          protocol      = "tcp"
        }
      ]

      dependsOn = [
        {
          containerName = "aws-otel-collector"
          condition     = "START"
        }
      ]

      environment = concat([
        {
          name  = "ENVIRONMENT"
          value = var.environment
        },
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
        {
          name  = "OTEL_SERVICE_NAME"
          value = "${var.environment}-applied-ai-agent-api"
        },
        {
          name  = "OTLP_ENDPOINT"
          value = "http://localhost:4318"
        }
      ], [
        for key, value in var.environment_variables : {
          name  = key
          value = value
        }
      ])

      secrets = [
        {
          name      = "AGENT_MEMORY_SERVER_URL"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/agent-memory-server/url"
        },
        {
          name      = "AGENT_MEMORY_SERVER_API_KEY"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/agent-memory-server/api-key"
        },
        {
          name      = "AUTH0_DOMAIN"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/auth0/domain"
        },
        {
          name      = "AUTH0_AUDIENCE"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/auth0/audience"
        },
        {
          name      = "AUTH0_CLIENT_ID"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/auth0/client_id"
        },
        {
          name      = "AUTH0_CLIENT_SECRET"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/auth0/client_secret"
        },
        {
          name      = "REDIS_URL"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/redis/url"
        },
        {
          name      = "OPENAI_API_KEY"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/openai/api_key"
        },
        {
          name      = "TAVILY_API_KEY"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/tavily/api_key"
        },
        {
          name      = "SLACK_BOT_TOKEN"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/slack/bot_token"
        },
        {
          name      = "SLACK_SIGNING_SECRET"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/slack/signing_secret"
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
    {
      name  = "aws-otel-collector"
      image = "public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3"
      cpu   = 0
      memory = 512
      essential = true

      environment = [
        {
          name  = "AOT_CONFIG_CONTENT"
          value = "extensions:\n  health_check:\n\nreceivers:\n  otlp:\n    protocols:\n      grpc:\n        endpoint: 0.0.0.0:4317\n      http:\n        endpoint: 0.0.0.0:4318\n\nprocessors:\n  batch/traces:\n    timeout: 1s\n    send_batch_size: 50\n  batch/metrics:\n    timeout: 10s\n  resourcedetection:\n    detectors:\n      - env\n      - ecs\n      - ec2\n  resource:\n    attributes:\n      - key: TaskDefinitionFamily\n        from_attribute: aws.ecs.task.family\n        action: insert\n      - key: aws.ecs.task.family\n        action: delete\n      - key: InstanceId\n        from_attribute: host.id\n        action: insert\n      - key: host.id\n        action: delete\n      - key: TaskARN\n        from_attribute: aws.ecs.task.arn\n        action: insert\n      - key: aws.ecs.task.arn\n        action: delete\n      - key: TaskDefinitionRevision\n        from_attribute: aws.ecs.task.revision\n        action: insert\n      - key: aws.ecs.task.revision\n        action: delete\n      - key: LaunchType\n        from_attribute: aws.ecs.launchtype\n        action: insert\n      - key: aws.ecs.launchtype\n        action: delete\n      - key: ClusterARN\n        from_attribute: aws.ecs.cluster.arn\n        action: insert\n      - key: aws.ecs.cluster.arn\n        action: delete\n      - key: cloud.provider\n        action: delete\n      - key: cloud.platform\n        action: delete\n      - key: cloud.account.id\n        action: delete\n      - key: cloud.region\n        action: delete\n      - key: cloud.availability_zone\n        action: delete\n      - key: aws.log.group.names\n        action: delete\n      - key: aws.log.group.arns\n        action: delete\n      - key: aws.log.stream.names\n        action: delete\n      - key: host.image.id\n        action: delete\n      - key: host.name\n        action: delete\n      - key: host.type\n        action: delete\n\nexporters:\n  awsxray:\n  awsemf:\n    namespace: ECS/AWSOTel/Application\n    dimension_rollup_option: NoDimensionRollup\n    resource_to_telemetry_conversion:\n      enabled: true\n\nservice:\n  pipelines:\n    traces:\n      receivers: [otlp]\n      processors: [resourcedetection, batch/traces]\n      exporters: [awsxray]\n    metrics:\n      receivers: [otlp]\n      processors: [resourcedetection, resource, batch/metrics]\n      exporters: [awsemf]\n\n  extensions: [health_check]"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.api.name
          awslogs-region        = var.region
          awslogs-stream-prefix = "otel"
        }
      }

      healthCheck = {
        command = ["/healthcheck"]
        interval = 5
        timeout = 6
        retries = 5
        startPeriod = 1
      }
    }
  ])

  tags = {
    Name = "${var.environment}-${var.project_name}-api-task"
  }
}

# ECS Task Definition for Worker Service
resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.environment}-${var.project_name}-worker-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.worker_cpu_units
  memory                   = var.worker_memory_units
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn           = var.task_role_arn

  container_definitions = jsonencode([
    {
      name  = "applied-ai-agent-worker"
      image = "${var.ecr_repositories["applied-ai-agent-worker"]}:latest"
      cpu   = var.worker_cpu_units
      memory = var.worker_memory_units
      essential = true
      command = ["python", "-m", "app.worker"]

      environment = concat([
        {
          name  = "ENVIRONMENT"
          value = var.environment
        },
        {
          name  = "OTEL_SERVICE_NAME"
          value = "${var.environment}-applied-ai-agent-worker"
        },
        {
          name  = "OTLP_ENDPOINT"
          value = "http://localhost:4318"
        }
      ], [
        for key, value in var.environment_variables : {
          name  = key
          value = value
        }
      ])

      secrets = [
        {
          name      = "AGENT_MEMORY_SERVER_URL"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/agent-memory-server/url"
        },
        {
          name      = "AGENT_MEMORY_SERVER_API_KEY"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/agent-memory-server/api-key"
        },
        {
          name      = "REDIS_URL"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/redis/url"
        },
        {
          name      = "OPENAI_API_KEY"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/openai/api_key"
        },
        {
          name      = "TAVILY_API_KEY"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/tavily/api_key"
        },
        {
          name      = "SLACK_BOT_TOKEN"
          valueFrom = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/${var.environment}/slack/bot_token"
        }
      ]

      dependsOn = [
        {
          containerName = "aws-otel-collector"
          condition     = "START"
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
    {
      name  = "aws-otel-collector"
      image = "public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3"
      cpu   = 0
      memory = 512
      essential = true

      environment = [
        {
          name  = "AOT_CONFIG_CONTENT"
          value = "extensions:\n  health_check:\n\nreceivers:\n  otlp:\n    protocols:\n      grpc:\n        endpoint: 0.0.0.0:4317\n      http:\n        endpoint: 0.0.0.0:4318\n\nprocessors:\n  batch/traces:\n    timeout: 1s\n    send_batch_size: 50\n  batch/metrics:\n    timeout: 10s\n  resourcedetection:\n    detectors:\n      - env\n      - ecs\n      - ec2\n  resource:\n    attributes:\n      - key: TaskDefinitionFamily\n        from_attribute: aws.ecs.task.family\n        action: insert\n      - key: aws.ecs.task.family\n        action: delete\n      - key: InstanceId\n        from_attribute: host.id\n        action: insert\n      - key: host.id\n        action: delete\n      - key: TaskARN\n        from_attribute: aws.ecs.task.arn\n        action: insert\n      - key: aws.ecs.task.arn\n        action: delete\n      - key: TaskDefinitionRevision\n        from_attribute: aws.ecs.task.revision\n        action: insert\n      - key: aws.ecs.task.revision\n        action: delete\n      - key: LaunchType\n        from_attribute: aws.ecs.launchtype\n        action: insert\n      - key: aws.ecs.launchtype\n        action: delete\n      - key: ClusterARN\n        from_attribute: aws.ecs.cluster.arn\n        action: insert\n      - key: aws.ecs.cluster.arn\n        action: delete\n      - key: cloud.provider\n        action: delete\n      - key: cloud.platform\n        action: delete\n      - key: cloud.account.id\n        action: delete\n      - key: cloud.region\n        action: delete\n      - key: cloud.availability_zone\n        action: delete\n      - key: aws.log.group.names\n        action: delete\n      - key: aws.log.group.arns\n        action: delete\n      - key: aws.log.stream.names\n        action: delete\n      - key: host.image.id\n        action: delete\n      - key: host.name\n        action: delete\n      - key: host.type\n        action: delete\n\nexporters:\n  awsxray:\n  awsemf:\n    namespace: ECS/AWSOTel/Application\n    dimension_rollup_option: NoDimensionRollup\n    resource_to_telemetry_conversion:\n      enabled: true\n\nservice:\n  pipelines:\n    traces:\n      receivers: [otlp]\n      processors: [resourcedetection, batch/traces]\n      exporters: [awsxray]\n    metrics:\n      receivers: [otlp]\n      processors: [resourcedetection, resource, batch/metrics]\n      exporters: [awsemf]\n\n  extensions: [health_check]"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.worker.name
          awslogs-region        = var.region
          awslogs-stream-prefix = "otel"
        }
      }

      healthCheck = {
        command = ["/healthcheck"]
        interval = 5
        timeout = 6
        retries = 5
        startPeriod = 1
      }
    }
  ])

  tags = {
    Name = "${var.environment}-${var.project_name}-worker-task"
  }
}

# ECS Service for API
resource "aws_ecs_service" "api" {
  name            = "${var.environment}-${var.project_name}-api-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.family
  desired_count   = var.desired_capacity
  launch_type     = "FARGATE"

  enable_execute_command = true

  network_configuration {
    subnets          = var.subnets
    security_groups  = [var.security_groups.ecs]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = var.alb_api_target_group_arn
    container_name   = "${var.project_name}-api"
    container_port   = 3000
  }

  tags = {
    Name = "${var.environment}-${var.project_name}-api-service"
  }
}

# ECS Service for Worker
resource "aws_ecs_service" "worker" {
  name            = "${var.environment}-${var.project_name}-worker-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.family
  desired_count   = var.worker_desired_capacity
  launch_type     = "FARGATE"

  enable_execute_command = true

  network_configuration {
    subnets          = var.subnets
    security_groups  = [var.security_groups.ecs]
    assign_public_ip = false
  }

  tags = {
    Name = "${var.environment}-applied-ai-agent-worker-service"
  }
}

