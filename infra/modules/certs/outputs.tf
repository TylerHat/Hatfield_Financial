output "frontend_cert_arn" {
  description = "Validated ACM cert ARN for hatfield-financial.com — used by CloudFront"
  value       = aws_acm_certificate_validation.frontend.certificate_arn
}

output "api_cert_arn" {
  description = "Validated ACM cert ARN for api.hatfield-financial.com — used by ALB"
  value       = aws_acm_certificate_validation.api.certificate_arn
}
