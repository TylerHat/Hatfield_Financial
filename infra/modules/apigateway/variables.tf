variable "app_name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  description = "Subnets for the VPC Link (same subnets where ECS tasks run)"
  type        = list(string)
}

variable "ecs_security_group_id" {
  description = "ECS task security group — VPC Link needs to reach these"
  type        = string
}

variable "acm_certificate_arn" {
  description = "ACM certificate for the API custom domain"
  type        = string
}

variable "domain_name" {
  description = "Root domain (e.g. hatfield-financial.com)"
  type        = string
}
