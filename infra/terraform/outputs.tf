output "app_runner_service_url" {
  description = "Direct HTTPS URL for the deployed web service on AWS App Runner"
  value       = "https://${aws_apprunner_service.app.service_url}"
}

output "ecs_https_url" {
  description = "Public HTTPS URL for the optional ECS Fargate deployment (ALB+ACM or CloudFront)"
  value = var.enable_ecs_fargate ? (
    var.acm_certificate_arn != "" ? "https://${aws_lb.app[0].dns_name}" : (
      var.enable_cloudfront_https ? "https://${aws_cloudfront_distribution.app[0].domain_name}" : "http://${aws_lb.app[0].dns_name}"
    )
  ) : null
}

output "rds_endpoint" {
  description = "Private PostgreSQL database endpoint"
  value       = aws_db_instance.postgres.endpoint
}

output "s3_bucket_name" {
  description = "Amazon S3 bucket name storing PDF invitations"
  value       = aws_s3_bucket.invitations.id
}

output "ecr_repository_url" {
  description = "Amazon ECR repository URL for pushing container images"
  value       = aws_ecr_repository.app.repository_url
}
