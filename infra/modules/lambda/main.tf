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
  # 1024 MB covers the 500-ticker precompute comfortably; CloudWatch
  # showed the prior 2048 MB rarely exceeded ~700 MB. Step back up if a
  # future S&P expansion or a heavier indicator overruns. Cuts ~$3-7/mo
  # vs running at 2048 MB on the every-20-minute schedule.
  memory_size = 1024

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

# Explicit log group with retention. AWS auto-creates Lambda log groups
# on first invocation with retention=Never Expire, accumulating CloudWatch
# storage forever. Declaring the resource here pins retention to 14 days.
#
# NOTE on first-time apply: if the Lambda has already run before this
# resource is added, AWS already owns a log group with the same name.
# Run once: `terraform import module.lambda.aws_cloudwatch_log_group.recommendations /aws/lambda/${app_name}-recommendations-precompute`
# before `terraform apply` to adopt the existing group.
resource "aws_cloudwatch_log_group" "recommendations" {
  name              = "/aws/lambda/${aws_lambda_function.recommendations.function_name}"
  retention_in_days = 14
  tags              = { Name = "${var.app_name}-recommendations-precompute-logs" }
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

# ═════════════════════════════════════════════════════════════════════════════
# Custom ETF daily rebalance Lambda + EventBridge Scheduler
# Fires at 9:30 AM America/New_York, MON-FRI. POSTs to the backend's
# /api/custom-etf/auto-rebalance-all endpoint, authenticated by a shared secret.
# ═════════════════════════════════════════════════════════════════════════════

# ── IAM role for the rebalance Lambda ────────────────────────────────────────

resource "aws_iam_role" "lambda_etf_rebalance" {
  name = "${var.app_name}-lambda-etf-rebalance-role"

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

  tags = { Name = "${var.app_name}-lambda-etf-rebalance-role" }
}

resource "aws_iam_role_policy_attachment" "lambda_etf_rebalance_basic" {
  role       = aws_iam_role.lambda_etf_rebalance.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ── Lambda function (zip-based, stdlib only) ─────────────────────────────────

data "archive_file" "etf_rebalance_zip" {
  type        = "zip"
  source_file = "${path.module}/../../../Backend/lambda_rebalance_handler.py"
  output_path = "${path.module}/etf_rebalance.zip"
}

resource "aws_lambda_function" "etf_rebalance" {
  function_name    = "${var.app_name}-etf-rebalance"
  role             = aws_iam_role.lambda_etf_rebalance.arn
  runtime          = "python3.12"
  handler          = "lambda_rebalance_handler.handler"
  filename         = data.archive_file.etf_rebalance_zip.output_path
  source_code_hash = data.archive_file.etf_rebalance_zip.output_base64sha256
  timeout          = 180
  memory_size      = 128

  environment {
    variables = {
      BACKEND_URL         = var.backend_url
      INTERNAL_API_SECRET = var.internal_api_secret
    }
  }

  tags = { Name = "${var.app_name}-etf-rebalance" }
}

# Explicit log group with retention (see note on aws_cloudwatch_log_group.recommendations).
# Import on first apply if the Lambda has already run:
#   terraform import module.lambda.aws_cloudwatch_log_group.etf_rebalance /aws/lambda/${app_name}-etf-rebalance
resource "aws_cloudwatch_log_group" "etf_rebalance" {
  name              = "/aws/lambda/${aws_lambda_function.etf_rebalance.function_name}"
  retention_in_days = 14
  tags              = { Name = "${var.app_name}-etf-rebalance-logs" }
}

# ── EventBridge Scheduler (timezone-aware, beats classic cron) ───────────────

resource "aws_iam_role" "etf_rebalance_scheduler" {
  name = "${var.app_name}-etf-rebalance-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "scheduler.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy" "etf_rebalance_scheduler_invoke" {
  name = "${var.app_name}-etf-rebalance-scheduler-invoke"
  role = aws_iam_role.etf_rebalance_scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "lambda:InvokeFunction"
        Resource = aws_lambda_function.etf_rebalance.arn
      }
    ]
  })
}

resource "aws_scheduler_schedule" "etf_rebalance_daily" {
  name        = "${var.app_name}-etf-rebalance-daily"
  description = "Fire Custom ETF rebalance at NYSE open (9:30 ET, MON-FRI)"
  group_name  = "default"

  flexible_time_window {
    mode = "OFF"
  }

  # cron(minutes hours day-of-month month day-of-week year)
  # 9:30 every weekday — timezone handles DST automatically.
  schedule_expression          = "cron(30 9 ? * MON-FRI *)"
  schedule_expression_timezone = "America/New_York"

  target {
    arn      = aws_lambda_function.etf_rebalance.arn
    role_arn = aws_iam_role.etf_rebalance_scheduler.arn

    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 2
    }
  }
}
