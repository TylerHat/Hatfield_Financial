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

variable "alb_security_group_id" {
  type = string
}

variable "ecs_task_execution_role_arn" {
  type = string
}

variable "secret_key" {
  type      = string
  sensitive = true
}

variable "database_url" {
  type      = string
  sensitive = true
}

variable "allowed_origin" {
  type = string
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN for api.hatfield-financial.com (attached to HTTPS listener)"
  type        = string
}
