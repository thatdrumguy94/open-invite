resource "aws_apprunner_vpc_connector" "connector" {
  vpc_connector_name = "${var.project_name}-vpc-connector"
  subnets            = data.aws_subnets.default.ids
  security_groups    = [aws_security_group.apprunner_egress.id]
}

resource "aws_apprunner_service" "app" {
  service_name = "${var.project_name}-service"

  instance_configuration {
    cpu               = "1024" # 1 vCPU
    memory            = "2048" # 2 GB
    instance_role_arn = aws_iam_role.apprunner_instance.arn
  }

  network_configuration {
    egress_configuration {
      egress_type       = "VPC"
      vpc_connector_arn = aws_apprunner_vpc_connector.connector.arn
    }
  }

  health_check_configuration {
    protocol            = "HTTP"
    path                = "/health"
    interval            = 10
    timeout             = 5
    healthy_threshold   = 1
    unhealthy_threshold = 5
  }

  source_configuration {
    authentication_configuration {
      access_role_arn = aws_iam_role.apprunner_access.arn
    }
    auto_deployments_enabled = true

    image_repository {
      image_identifier      = "${aws_ecr_repository.app.repository_url}:latest"
      image_repository_type = "ECR"

      image_configuration {
        port = "5000"

        runtime_environment_variables = {
          FLASK_ENV           = "production"
          DATABASE_URL        = "postgresql://${var.db_username}:${var.db_password}@${aws_db_instance.postgres.endpoint}/event_db"
          STORAGE_BACKEND     = "s3"
          S3_BUCKET_NAME      = aws_s3_bucket.invitations.id
          AWS_REGION          = var.aws_region
          EMAIL_PROVIDER      = "ses"
          MAIL_DEFAULT_SENDER = var.sender_email
          AUTO_SEED           = "true"
          SECRET_KEY          = random_password.secret_key.result
        }
      }
    }
  }

  depends_on = [
    aws_db_instance.postgres,
    aws_s3_bucket.invitations
  ]
}
