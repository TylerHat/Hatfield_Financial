# ── Route 53 hosted zone lookup ───────────────────────────────────────────────
data "aws_route53_zone" "main" {
  name         = var.domain_name
  private_zone = false
}

# ── Route 53 A Records ────────────────────────────────────────────────────────

# hatfield-financial.com → CloudFront
resource "aws_route53_record" "frontend_root" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = var.cloudfront_domain_name
    zone_id                = var.cloudfront_hosted_zone_id
    evaluate_target_health = false
  }
}

# www.hatfield-financial.com → CloudFront
resource "aws_route53_record" "frontend_www" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "www.${var.domain_name}"
  type    = "A"

  alias {
    name                   = var.cloudfront_domain_name
    zone_id                = var.cloudfront_hosted_zone_id
    evaluate_target_health = false
  }
}

# api.hatfield-financial.com → API Gateway
resource "aws_route53_record" "api" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "api.${var.domain_name}"
  type    = "A"

  alias {
    name                   = var.api_gateway_domain_target
    zone_id                = var.api_gateway_hosted_zone_id
    evaluate_target_health = false
  }
}
