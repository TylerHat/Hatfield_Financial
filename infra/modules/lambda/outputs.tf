output "s3_cache_bucket_name" {
  description = "S3 bucket name for pre-computed recommendations"
  value       = aws_s3_bucket.sp500_cache.id
}

output "lambda_function_name" {
  description = "Lambda function name for CI/CD"
  value       = aws_lambda_function.recommendations.function_name
}

output "ecr_lambda_repository_url" {
  description = "ECR repository URL for Lambda image"
  value       = aws_ecr_repository.lambda_recommendations.repository_url
}
