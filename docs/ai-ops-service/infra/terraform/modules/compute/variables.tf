variable "name_prefix" {
  type = string
}

variable "env" {
  type = string
}

variable "region" {
  type    = string
  default = "ap-northeast-1"
}

variable "vpc_id" {
  type = string
}

variable "private_app_subnet_ids" {
  type = list(string)
}

variable "alb_security_group_id" {
  type = string
}

variable "service_names" {
  description = "List of ECS service names (used for log group creation)"
  type        = list(string)
  default     = ["litellm", "control-plane", "langfuse-web", "langfuse-worker", "aegis-worker", "clickhouse"]
}

variable "log_retention_days" {
  type    = number
  default = 30
}

# --- LiteLLM ---
variable "litellm_image_uri" {
  description = "ECR image URI for LiteLLM"
  type        = string
  default     = "PLACEHOLDER_TODO_REPLACE_WITH_ECR"
}

variable "litellm_cpu" {
  type    = number
  default = 1024
}

variable "litellm_memory" {
  type    = number
  default = 2048
}

variable "litellm_desired_count" {
  type    = number
  default = 2
}

variable "litellm_max_capacity" {
  type    = number
  default = 10
}

variable "litellm_target_group_arn" {
  description = "ALB target group ARN"
  type        = string
}

variable "audit_bucket_arn" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
