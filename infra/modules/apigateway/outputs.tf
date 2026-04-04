output "service_discovery_service_arn" {
  description = "Cloud Map service ARN — used by ECS service registration"
  value       = aws_service_discovery_service.backend.arn
}

output "api_gateway_domain_target" {
  description = "API Gateway custom domain target — used for Route 53 alias"
  value       = aws_apigatewayv2_domain_name.api.domain_name_configuration[0].target_domain_name
}

output "api_gateway_hosted_zone_id" {
  description = "API Gateway custom domain hosted zone — used for Route 53 alias"
  value       = aws_apigatewayv2_domain_name.api.domain_name_configuration[0].hosted_zone_id
}
