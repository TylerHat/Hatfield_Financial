variable "app_name" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "backend_url" {
  description = "Public backend URL (e.g. https://api.hatfield-financial.com) used by the daily ETF rebalance Lambda"
  type        = string
}

variable "internal_api_secret" {
  description = "Shared secret used by the daily ETF rebalance Lambda to authenticate to the backend. Must match INTERNAL_API_SECRET on the ECS task."
  type        = string
  sensitive   = true
}
