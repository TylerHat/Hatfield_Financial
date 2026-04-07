# ── Copy these values into GitHub Actions secrets after terraform apply ───────

output "ecr_repository_url" {
  description = "ECR image URL — set as ECR_REPOSITORY in GitHub secrets"
  value       = module.ecr.repository_url
}

output "ecs_cluster_name" {
  description = "ECS cluster name — set as ECS_CLUSTER in GitHub secrets"
  value       = module.ecs.cluster_name
}

output "ecs_service_name" {
  description = "ECS service name — set as ECS_SERVICE in GitHub secrets"
  value       = module.ecs.service_name
}

output "s3_frontend_bucket" {
  description = "S3 bucket name — set as S3_BUCKET_NAME in GitHub secrets"
  value       = module.cdn.bucket_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID — set as CLOUDFRONT_DISTRIBUTION_ID in GitHub secrets"
  value       = module.cdn.distribution_id
}

output "cloudfront_domain" {
  description = "Frontend URL — your live app"
  value       = "https://${var.domain_name}"
}

output "github_actions_key_id" {
  description = "IAM access key ID for GitHub Actions — set as AWS_ACCESS_KEY_ID in GitHub secrets"
  value       = module.iam.github_actions_key_id
}

output "github_actions_secret_key" {
  description = "IAM secret access key for GitHub Actions — set as AWS_SECRET_ACCESS_KEY in GitHub secrets"
  value       = module.iam.github_actions_secret_key
  sensitive   = true
}

output "lambda_ecr_repository_url" {
  description = "ECR repository URL for Lambda image — set as LAMBDA_ECR_REPOSITORY in GitHub secrets"
  value       = module.lambda.ecr_lambda_repository_url
}

output "lambda_function_name" {
  description = "Lambda function name — set as LAMBDA_FUNCTION_NAME in GitHub secrets"
  value       = module.lambda.lambda_function_name
}

output "s3_cache_bucket_name" {
  description = "S3 bucket for pre-computed recommendations — set as S3_CACHE_BUCKET in GitHub secrets"
  value       = module.lambda.s3_cache_bucket_name
}
