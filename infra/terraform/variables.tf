variable "aws_region" {
  description = "The AWS region to deploy infrastructure into"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment identifier (e.g. prod, staging, dev)"
  type        = string
  default     = "prod"
}

variable "project_name" {
  description = "Project name prefix"
  type        = string
  default     = "event-invitation-system"
}

variable "s3_bucket_name" {
  description = "Base name for the S3 bucket storing PDF invitations"
  type        = string
  default     = "open-invite-storage"
}

variable "db_username" {
  description = "Master username for Amazon RDS PostgreSQL"
  type        = string
  default     = "postgres"
}

variable "db_password" {
  description = "Master password for Amazon RDS PostgreSQL"
  type        = string
  sensitive   = true
  default     = "CloudComputing2026!"
}

variable "db_instance_class" {
  description = "Instance type for RDS PostgreSQL (db.t3.micro is Free Tier eligible)"
  type        = string
  default     = "db.t3.micro"
}

variable "sender_email" {
  description = "Verified sender email address for transactional communications"
  type        = string
  default     = "invitations@example.com"
}
