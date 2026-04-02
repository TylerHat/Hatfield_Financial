output "cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "service_name" {
  value = aws_ecs_service.backend.name
}

output "alb_dns_name" {
  value = aws_lb.main.dns_name
}

output "alb_hosted_zone_id" {
  description = "ALB hosted zone ID — used for Route 53 alias records"
  value       = aws_lb.main.zone_id
}
