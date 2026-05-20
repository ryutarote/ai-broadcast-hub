variable "name_prefix" {
  type = string
}

variable "account_id" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_data_subnet_ids" {
  type = list(string)
}

variable "app_security_group_ids" {
  description = "Security groups allowed to access DB/Redis"
  type        = list(string)
}

variable "kms_rds_key_arn" {
  type = string
}

variable "kms_s3_key_arn" {
  type = string
}

variable "kms_secrets_key_arn" {
  type = string
}

variable "aurora_min_acu" {
  type    = number
  default = 0.5
}

variable "aurora_max_acu" {
  type    = number
  default = 4
}

variable "aurora_instance_count" {
  description = "Number of Aurora instances (1 writer + N-1 readers)"
  type        = number
  default     = 2
}

variable "backup_retention_days" {
  type    = number
  default = 14
}

variable "deletion_protection" {
  type    = bool
  default = true
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.micro"
}

variable "redis_num_cache_clusters" {
  type    = number
  default = 1
}

variable "audit_retention_days" {
  description = "S3 audit bucket object expiration days (max across plans)"
  type        = number
  default     = 400
}

variable "tags" {
  type    = map(string)
  default = {}
}
