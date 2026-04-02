# ── Route 53 hosted zone lookup ───────────────────────────────────────────────
data "aws_route53_zone" "main" {
  name         = var.domain_name
  private_zone = false
}

# ── ACM Certificate: Frontend (hatfield-financial.com + www.) ────────────────
# Must be in us-east-1 — CloudFront only accepts certs from this region.
resource "aws_acm_certificate" "frontend" {
  domain_name               = var.domain_name
  subject_alternative_names = ["www.${var.domain_name}"]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = { Name = "${var.app_name}-frontend-cert" }
}

# ── ACM Certificate: API (api.hatfield-financial.com) ────────────────────────
resource "aws_acm_certificate" "api" {
  domain_name       = "api.${var.domain_name}"
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = { Name = "${var.app_name}-api-cert" }
}

# ── DNS Validation Records ────────────────────────────────────────────────────
locals {
  all_validation_options = merge(
    { for dvo in aws_acm_certificate.frontend.domain_validation_options : dvo.domain_name => dvo },
    { for dvo in aws_acm_certificate.api.domain_validation_options : dvo.domain_name => dvo }
  )
}

resource "aws_route53_record" "cert_validation" {
  for_each = local.all_validation_options

  zone_id = data.aws_route53_zone.main.zone_id
  name    = each.value.resource_record_name
  type    = each.value.resource_record_type
  ttl     = 60
  records = [each.value.resource_record_value]
}

resource "aws_acm_certificate_validation" "frontend" {
  certificate_arn         = aws_acm_certificate.frontend.arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}

resource "aws_acm_certificate_validation" "api" {
  certificate_arn         = aws_acm_certificate.api.arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}
