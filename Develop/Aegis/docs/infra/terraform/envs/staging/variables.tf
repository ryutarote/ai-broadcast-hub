variable "region" {
  type    = string
  default = "ap-northeast-1"
}

variable "root_domain" {
  type        = string
  description = "Staging domain (e.g. staging.aegis.jp)"
}

variable "route53_zone_id" {
  type = string
}

variable "github_repo" {
  type = string
}

variable "litellm_image_uri" {
  type = string
}
