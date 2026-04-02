variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "app_name" {
  description = "Base name used for all AWS resources"
  type        = string
  default     = "hatfield-financial"
}

variable "db_username" {
  description = "RDS master username"
  type        = string
}

variable "db_password" {
  description = "RDS master password"
  type        = string
  sensitive   = true
}

variable "secret_key" {
  description = "Flask SECRET_KEY value stored in Secrets Manager"
  type        = string
  sensitive   = true
}

variable "domain_name" {
  description = "Root domain registered in Route 53 (e.g. hatfield-financial.com)"
  type        = string
  default     = "hatfield-financial.com"
}
