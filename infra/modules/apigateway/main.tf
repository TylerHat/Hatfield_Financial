# ── Cloud Map Service Discovery ───────────────────────────────────────────────
resource "aws_service_discovery_private_dns_namespace" "main" {
  name = "internal"
  vpc  = var.vpc_id

  tags = { Name = "${var.app_name}-namespace" }
}

resource "aws_service_discovery_service" "backend" {
  name = "backend"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id

    dns_records {
      ttl  = 10
      type = "SRV"
    }

    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }

  tags = { Name = "${var.app_name}-discovery" }
}

# ── Security Group: VPC Link ─────────────────────────────────────────────────
resource "aws_security_group" "vpc_link" {
  name        = "${var.app_name}-vpclink-sg"
  description = "Allow API Gateway VPC Link to reach ECS tasks"
  vpc_id      = var.vpc_id

  egress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [var.ecs_security_group_id]
  }

  tags = { Name = "${var.app_name}-vpclink-sg" }
}

# ── API Gateway HTTP API ─────────────────────────────────────────────────────
resource "aws_apigatewayv2_api" "main" {
  name          = "${var.app_name}-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins     = ["https://${var.domain_name}", "https://www.${var.domain_name}"]
    allow_methods     = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers     = ["Content-Type", "Authorization", "X-Requested-With"]
    expose_headers    = ["Content-Type", "Authorization"]
    allow_credentials = true
    max_age           = 86400
  }

  tags = { Name = "${var.app_name}-api" }
}

# ── VPC Link (free for HTTP APIs) ────────────────────────────────────────────
resource "aws_apigatewayv2_vpc_link" "main" {
  name               = "${var.app_name}-vpclink"
  subnet_ids         = var.subnet_ids
  security_group_ids = [aws_security_group.vpc_link.id]

  tags = { Name = "${var.app_name}-vpclink" }
}

# ── Integration: VPC Link → Cloud Map → ECS ──────────────────────────────────
resource "aws_apigatewayv2_integration" "backend" {
  api_id             = aws_apigatewayv2_api.main.id
  integration_type   = "HTTP_PROXY"
  integration_method = "ANY"
  integration_uri    = aws_service_discovery_service.backend.arn
  connection_type    = "VPC_LINK"
  connection_id      = aws_apigatewayv2_vpc_link.main.id
}

# ── Route: catch-all ─────────────────────────────────────────────────────────
resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.backend.id}"
}

# ── Stage: auto-deploy ───────────────────────────────────────────────────────
resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "$default"
  auto_deploy = true

  tags = { Name = "${var.app_name}-api-stage" }
}

# ── Custom Domain ────────────────────────────────────────────────────────────
resource "aws_apigatewayv2_domain_name" "api" {
  domain_name = "api.${var.domain_name}"

  domain_name_configuration {
    certificate_arn = var.acm_certificate_arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }

  tags = { Name = "${var.app_name}-api-domain" }
}

resource "aws_apigatewayv2_api_mapping" "api" {
  api_id      = aws_apigatewayv2_api.main.id
  domain_name = aws_apigatewayv2_domain_name.api.id
  stage       = aws_apigatewayv2_stage.default.id
}
