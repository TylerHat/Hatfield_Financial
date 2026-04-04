output "file_system_id" {
  value = aws_efs_file_system.main.id
}

output "access_point_id" {
  value = aws_efs_access_point.data.id
}
