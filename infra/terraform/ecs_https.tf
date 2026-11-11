locals {
  ecs_use_acm        = var.enable_ecs_fargate && var.acm_certificate_arn != ""
  ecs_use_cloudfront = var.enable_ecs_fargate && var.acm_certificate_arn == "" && var.enable_cloudfront_https
}

resource "aws_security_group" "alb" {
  count       = var.enable_ecs_fargate ? 1 : 0
  name        = "${var.project_name}-alb-sg"
  description = "Allow HTTP (redirected) and HTTPS inbound to ALB"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "ecs_tasks" {
  count       = var.enable_ecs_fargate ? 1 : 0
  name        = "${var.project_name}-ecs-tasks-sg"
  description = "Allow container port 5000 only from ALB"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "App traffic from ALB"
    from_port       = 5000
    to_port         = 5000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb[0].id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group_rule" "rds_from_ecs" {
  count                    = var.enable_ecs_fargate ? 1 : 0
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds.id
  source_security_group_id = aws_security_group.ecs_tasks[0].id
  description              = "PostgreSQL from ECS Fargate tasks"
}

resource "aws_lb" "app" {
  count              = var.enable_ecs_fargate ? 1 : 0
  name               = "${var.environment}-openinvite-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb[0].id]
  subnets            = data.aws_subnets.default.ids
}

resource "aws_lb_target_group" "app" {
  count       = var.enable_ecs_fargate ? 1 : 0
  name        = "${var.environment}-openinvite-tg"
  port        = 5000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = data.aws_vpc.default.id

  health_check {
    path                = "/health"
    protocol            = "HTTP"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "http_redirect" {
  count             = local.ecs_use_acm ? 1 : 0
  load_balancer_arn = aws_lb.app[0].arn
  port              = 80
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

resource "aws_lb_listener" "https" {
  count             = local.ecs_use_acm ? 1 : 0
  load_balancer_arn = aws_lb.app[0].arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.acm_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app[0].arn
  }
}

resource "aws_lb_listener" "http_origin" {
  count             = var.enable_ecs_fargate && !local.ecs_use_acm ? 1 : 0
  load_balancer_arn = aws_lb.app[0].arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app[0].arn
  }
}

resource "aws_cloudfront_distribution" "app" {
  count        = local.ecs_use_cloudfront ? 1 : 0
  enabled      = true
  comment      = "${var.environment} OpenInvite HTTPS Edge"
  http_version = "http2"

  origin {
    domain_name = aws_lb.app[0].dns_name
    origin_id   = "alb-origin"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "alb-origin"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    min_ttl                = 0
    default_ttl            = 0
    max_ttl                = 0

    forwarded_values {
      query_string = true
      headers      = ["Host", "Origin", "Referer", "Accept", "Accept-Language", "User-Agent", "CloudFront-Forwarded-Proto"]

      cookies {
        forward = "all"
      }
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

resource "aws_iam_role" "ecs_execution" {
  count = var.enable_ecs_fargate ? 1 : 0
  name  = "${var.project_name}-ecs-exec-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  count      = var.enable_ecs_fargate ? 1 : 0
  role       = aws_iam_role.ecs_execution[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task" {
  count = var.enable_ecs_fargate ? 1 : 0
  name  = "${var.project_name}-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_s3_ses" {
  count      = var.enable_ecs_fargate ? 1 : 0
  role       = aws_iam_role.ecs_task[0].name
  policy_arn = aws_iam_policy.apprunner_s3_ses.arn
}

resource "aws_cloudwatch_log_group" "ecs" {
  count             = var.enable_ecs_fargate ? 1 : 0
  name              = "/ecs/${var.project_name}"
  retention_in_days = 14
}

resource "aws_ecs_cluster" "main" {
  count = var.enable_ecs_fargate ? 1 : 0
  name  = "${var.project_name}-cluster"
}

resource "aws_ecs_task_definition" "app" {
  count                    = var.enable_ecs_fargate ? 1 : 0
  family                   = "${var.project_name}-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_execution[0].arn
  task_role_arn            = aws_iam_role.ecs_task[0].arn

  container_definitions = jsonencode([
    {
      name      = "openinvite-web"
      image     = "${aws_ecr_repository.app.repository_url}:latest"
      essential = true
      portMappings = [
        {
          containerPort = 5000
          protocol      = "tcp"
        }
      ]
      environment = [
        { name = "FLASK_ENV", value = "production" },
        { name = "FORCE_HTTPS", value = "true" },
        { name = "SESSION_COOKIE_SECURE", value = "true" },
        { name = "PREFERRED_URL_SCHEME", value = "https" },
        { name = "TRUST_PROXY_HEADERS", value = "true" },
        { name = "DATABASE_URL", value = "postgresql://${var.db_username}:${var.db_password}@${aws_db_instance.postgres.endpoint}/event_db" },
        { name = "STORAGE_BACKEND", value = "s3" },
        { name = "S3_BUCKET_NAME", value = aws_s3_bucket.invitations.id },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "EMAIL_PROVIDER", value = "ses" },
        { name = "MAIL_DEFAULT_SENDER", value = var.sender_email },
        { name = "AUTO_SEED", value = "true" },
        { name = "SECRET_KEY", value = random_password.secret_key.result }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs[0].name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "app" {
  count           = var.enable_ecs_fargate ? 1 : 0
  name            = "${var.project_name}-service"
  cluster         = aws_ecs_cluster.main[0].id
  task_definition = aws_ecs_task_definition.app[0].arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.ecs_tasks[0].id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app[0].arn
    container_name   = "openinvite-web"
    container_port   = 5000
  }

  depends_on = [
    aws_lb_listener.https,
    aws_lb_listener.http_origin,
  ]
}
