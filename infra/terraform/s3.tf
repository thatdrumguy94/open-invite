resource "aws_s3_bucket" "invitations" {
  bucket        = "${var.s3_bucket_name}-${data.aws_caller_identity.current.account_id}"
  force_destroy = false

  tags = {
    Name = "${var.project_name}-invitations"
  }
}

resource "aws_s3_bucket_versioning" "invitations" {
  bucket = aws_s3_bucket.invitations.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "invitations" {
  bucket = aws_s3_bucket.invitations.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "invitations" {
  bucket = aws_s3_bucket.invitations.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_cors_configuration" "invitations" {
  bucket = aws_s3_bucket.invitations.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = ["*"]
    max_age_seconds = 3600
  }
}
