variable "app_name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  description = "Subnets for EFS mount targets (same subnets where ECS tasks run)"
  type        = list(string)
}

variable "ecs_security_group_id" {
  description = "ECS task security group — allowed to access EFS"
  type        = string
}
