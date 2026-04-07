data "aws_caller_identity" "current" {}

# ── S3 Bucket for pre-computed recommendations ────────────────────────────────

resource "aws_s3_bucket" "sp500_cache" {
  bucket_prefix = "${var.app_name}-sp500-cache-"
  tags          = { Name = "${var.app_name}-sp500-cache" }
}

resource "aws_s3_bucket_versioning" "sp500_cache" {
  bucket = aws_s3_bucket.sp500_cache.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "sp500_cache" {
  bucket = aws_s3_bucket.sp500_cache.id

  rule {
    id     = "cleanup-old-versions"
    status = "Enabled"

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }
}

resource "aws_s3_bucket_public_access_block" "sp500_cache" {
  bucket                  = aws_s3_bucket.sp500_cache.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── ECR Repository for Lambda image ──────────────────────────────────────────

resource "aws_ecr_repository" "lambda_recommendations" {
  name                 = "${var.app_name}-lambda-recommendations"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = false
  }

  tags = { Name = "${var.app_name}-lambda-recommendations" }
}

resource "aws_ecr_lifecycle_policy" "lambda_recommendations" {
  repository = aws_ecr_repository.lambda_recommendations.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 5 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 5
        }
        action = { type = "expire" }
      }
    ]
  })
}

# ── IAM Role for Lambda ──────────────────────────────────────────────────────

resource "aws_iam_role" "lambda_recommendations" {
  name = "${var.app_name}-lambda-recommendations-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "lambda.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })

  tags = { Name = "${var.app_name}-lambda-recommendations-role" }
}

# CloudWatch Logs
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_recommendations.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# S3 write access to cache bucket
resource "aws_iam_role_policy" "lambda_s3_write" {
  name = "${var.app_name}-lambda-s3-write"
  role = aws_iam_role.lambda_recommendations.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject"
        ]
        Resource = "${aws_s3_bucket.sp500_cache.arn}/*"
      }
    ]
  })
}

# ── Lambda Function ──────────────────────────────────────────────────────────

resource "aws_lambda_function" "recommendations" {
  function_name = "${var.app_name}-recommendations-precompute"
  role          = aws_iam_role.lambda_recommendations.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.lambda_recommendations.repository_url}:latest"
  timeout       = 600
  memory_size   = 2048

  reserved_concurrent_executions = 1

  environment {
    variables = {
      S3_BUCKET = aws_s3_bucket.sp500_cache.id
      S3_KEY    = "recommendations/latest.json"
    }
  }

  tags = { Name = "${var.app_name}-recommendations-precompute" }

  # Ignore image_uri changes from CI/CD deploys
  lifecycle {
    ignore_changes = [image_uri]
  }
}

# ── EventBridge Schedule (every 20 minutes) ──────────────────────────────────

resource "aws_cloudwatch_event_rule" "recommendations_schedule" {
  name                = "${var.app_name}-recommendations-schedule"
  description         = "Trigger recommendations pre-compute every 20 minutes"
  schedule_expression = "rate(20 minutes)"
  tags                = { Name = "${var.app_name}-recommendations-schedule" }
}

resource "aws_cloudwatch_event_target" "recommendations_lambda" {
  rule = aws_cloudwatch_event_rule.recommendations_schedule.name
  arn  = aws_lambda_function.recommendations.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.recommendations.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.recommendations_schedule.arn
}
