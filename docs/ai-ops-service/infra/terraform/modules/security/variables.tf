variable "name_prefix" {
  type = string
}

variable "enable_github_oidc" {
  description = "Provision GitHub Actions OIDC provider and deploy role"
  type        = bool
  default     = true
}

variable "github_repo" {
  description = "GitHub repo (e.g. owner/repo) for OIDC trust"
  type        = string
  default     = ""
}

variable "waf_rate_limit" {
  description = "Per-IP requests per 5 min for rate-limit rule"
  type        = number
  default     = 5000
}

variable "tags" {
  type    = map(string)
  default = {}
}
