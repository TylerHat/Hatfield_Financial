variable "app_name" {
  type = string
}

variable "domain_name" {
  description = "Root domain for CloudFront aliases (e.g. hatfield-financial.com)"
  type        = string
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN for the custom domain (must be in us-east-1)"
  type        = string
}
