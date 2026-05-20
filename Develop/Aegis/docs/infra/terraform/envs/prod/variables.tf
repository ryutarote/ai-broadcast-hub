variable "region" {
  description = "AWS Region"
  type        = string
  default     = "ap-northeast-1"
}

variable "root_domain" {
  description = "Root domain (e.g. aegis.jp)"
  type        = string
}

variable "route53_zone_id" {
  description = "Route53 Hosted Zone ID"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository (owner/repo) for OIDC trust"
  type        = string
}

variable "litellm_image_uri" {
  description = "ECR image URI for LiteLLM (e.g. {account}.dkr.ecr.ap-northeast-1.amazonaws.com/aegis-litellm:v1)"
  type        = string
}
