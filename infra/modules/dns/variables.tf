variable "app_name" {
  type = string
}

variable "domain_name" {
  description = "Root domain registered in Route 53 (e.g. hatfield-financial.com)"
  type        = string
}

variable "cloudfront_domain_name" {
  description = "CloudFront distribution domain name (e.g. d1abc123.cloudfront.net)"
  type        = string
}

variable "cloudfront_hosted_zone_id" {
  description = "CloudFront's fixed hosted zone ID for Route 53 alias records"
  type        = string
}

variable "alb_dns_name" {
  description = "ALB DNS name"
  type        = string
}

variable "alb_hosted_zone_id" {
  description = "ALB hosted zone ID for Route 53 alias records"
  type        = string
}
