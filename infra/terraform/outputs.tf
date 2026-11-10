output "app_runner_service_url" {
  description = "Direct HTTPS URL for the deployed web service on AWS App Runner"
  value       = "https://${aws_apprunner_service.app.service_url}"
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
