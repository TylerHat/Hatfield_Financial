output "db_endpoint" {
  description = "RDS instance endpoint (host:port)"
  value       = aws_db_instance.postgres.endpoint
}

output "db_host" {
  description = "RDS hostname only"
  value       = aws_db_instance.postgres.address
}
