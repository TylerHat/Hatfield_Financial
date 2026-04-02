output "bucket_name" {
  value = aws_s3_bucket.frontend.bucket
}

output "distribution_id" {
  value = aws_cloudfront_distribution.frontend.id
}

output "cloudfront_domain" {
  value = aws_cloudfront_distribution.frontend.domain_name
}

output "cloudfront_hosted_zone_id" {
  description = "CloudFront's fixed hosted zone ID — used for Route 53 alias records"
  value       = aws_cloudfront_distribution.frontend.hosted_zone_id
}
