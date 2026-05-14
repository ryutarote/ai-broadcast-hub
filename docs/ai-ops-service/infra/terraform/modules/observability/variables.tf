variable "name_prefix" {
  type = string
}

variable "alb_arn_suffix" {
  description = "ALB ARN suffix (for CloudWatch dimensions)"
  type        = string
}

variable "rds_cluster_identifier" {
  type = string
}

variable "rds_acu_alert_threshold" {
  description = "Alert when ACU exceeds this value (set to ~80% of max)"
  type        = number
  default     = 3
}

variable "enable_guardduty" {
  type    = bool
  default = true
}

variable "tags" {
  type    = map(string)
  default = {}
}
