variable "app_name" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "ecr_repository_url" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "vpc_id" {
  type = string
}

variable "ecs_security_group_id" {
  type = string
}

variable "ecs_task_execution_role_arn" {
  type = string
}

variable "secret_key" {
  type      = string
  sensitive = true
}

variable "allowed_origin" {
  type = string
}

variable "efs_file_system_id" {
  description = "EFS file system ID for persistent SQLite storage"
  type        = string
}

variable "efs_access_point_id" {
  description = "EFS access point ID for the /data directory"
  type        = string
}

variable "service_discovery_service_arn" {
  description = "Cloud Map service ARN for API Gateway integration"
  type        = string
}

variable "s3_cache_bucket_name" {
  description = "S3 bucket name for pre-computed recommendations cache"
  type        = string
  default     = ""
}
