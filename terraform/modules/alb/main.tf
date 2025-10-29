# ALB Module for Applied AI Agent

# Application Load Balancer
resource "aws_lb" "main" {
  name               = "${var.project_name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.security_groups.alb]
  subnets            = var.subnets

  enable_deletion_protection = false

  tags = {
    Name = "${var.project_name}-alb"
  }
}

# HTTP Listener (for redirect to HTTPS)
resource "aws_lb_listener" "http" {
  count = var.certificate_arn != null && var.certificate_arn != "" ? 1 : 0

  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# HTTPS Listener
resource "aws_lb_listener" "https" {
  count = var.certificate_arn != null && var.certificate_arn != "" ? 1 : 0

  load_balancer_arn = aws_lb.main.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS-1-2-2017-01"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# HTTP Listener (fallback when no SSL certificate)
resource "aws_lb_listener" "http_fallback" {
  count = var.certificate_arn == "" ? 1 : 0

  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# Listener Rule for API routes
resource "aws_lb_listener_rule" "api" {
  count = var.certificate_arn != null && var.certificate_arn != "" ? 1 : 0

  listener_arn = aws_lb_listener.https[0].arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = ["/api/*", "/health", "/callback", "/login", "/logout"]
    }
  }
}

# Listener Rule for API routes (HTTP fallback)
resource "aws_lb_listener_rule" "api_http" {
  count = var.certificate_arn == "" ? 1 : 0

  listener_arn = aws_lb_listener.http_fallback[0].arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = ["/api/*", "/health", "/callback", "/login", "/logout"]
    }
  }
}

# Target Group for API Service
resource "aws_lb_target_group" "api" {
  name        = "${var.project_name}-api-tg"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200"
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = 5
    unhealthy_threshold = 2
  }

  tags = {
    Name = "${var.project_name}-api-tg"
  }
}

# Target Group for Agent Memory Server
resource "aws_lb_target_group" "memory_server" {
  # Keep the resource short to satisfy AWS 32-char limit for TG names
  name        = "${var.project_name}-mem-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200"
    path                = "/v1/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = 5
    unhealthy_threshold = 2
  }

  tags = {
    Name = "${var.project_name}-mem-tg"
  }
}

# Listener Rule for Agent Memory Server (HTTPS)
resource "aws_lb_listener_rule" "memory_server" {
  count = var.certificate_arn != null && var.certificate_arn != "" ? 1 : 0

  listener_arn = aws_lb_listener.https[0].arn
  priority     = 50

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.memory_server.arn
  }

  condition {
    path_pattern {
      values = ["/v1/*"]
    }
  }
}

# Listener Rule for Agent Memory Server (HTTP fallback)
resource "aws_lb_listener_rule" "memory_server_http" {
  count = var.certificate_arn == null || var.certificate_arn == "" ? 1 : 0

  listener_arn = aws_lb_listener.http_fallback[0].arn
  priority     = 50

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.memory_server.arn
  }

  condition {
    path_pattern {
      values = ["/v1/*"]
    }
  }
}

# CloudWatch Log Group for ALB
resource "aws_cloudwatch_log_group" "alb" {
  name              = "/aws/applicationloadbalancer/${var.project_name}"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-alb-logs"
  }
}
