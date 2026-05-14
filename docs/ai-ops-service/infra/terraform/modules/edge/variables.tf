variable "name_prefix" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "root_domain" {
  description = "Root domain (e.g. aegis.jp)"
  type        = string
}

variable "route53_zone_id" {
  description = "Route53 Hosted Zone ID for root_domain"
  type        = string
}

variable "waf_acl_arn" {
  type = string
}

variable "logs_bucket_name" {
  type = string
}

variable "deletion_protection" {
  type    = bool
  default = true
}

variable "tags" {
  type    = map(string)
  default = {}
}
