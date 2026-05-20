###############################################################################
# Aegis Staging Environment
# Production の縮小版。Single-AZ DB、最小台数で運用。
###############################################################################

terraform {
  required_version = ">= 1.7.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  name_prefix = "aegis-stg"
  account_id  = data.aws_caller_identity.current.account_id
  env         = "staging"

  common_tags = {
    Project    = "aegis"
    Env        = local.env
    Owner      = "engineering"
    CostCenter = "ai-ops"
    Tier       = "normal"
  }
}

provider "aws" {
  region = var.region
  default_tags { tags = local.common_tags }
}

module "network" {
  source = "../../modules/network"

  name_prefix       = local.name_prefix
  region            = var.region
  vpc_cidr          = "10.10.0.0/16"
  nat_gateway_count = 1
  enable_flow_logs  = false
  tags              = local.common_tags
}

module "security" {
  source = "../../modules/security"

  name_prefix        = local.name_prefix
  enable_github_oidc = true
  github_repo        = var.github_repo
  waf_rate_limit     = 1000
  tags               = local.common_tags
}

module "data" {
  source = "../../modules/data"

  name_prefix             = local.name_prefix
  account_id              = local.account_id
  vpc_id                  = module.network.vpc_id
  private_data_subnet_ids = module.network.private_data_subnet_ids
  app_security_group_ids  = [module.compute.task_security_group_id]

  kms_rds_key_arn     = module.security.kms_rds_key_arn
  kms_s3_key_arn      = module.security.kms_s3_key_arn
  kms_secrets_key_arn = module.security.kms_secrets_key_arn

  aurora_min_acu           = 0.5
  aurora_max_acu           = 1
  aurora_instance_count    = 1
  backup_retention_days    = 7
  deletion_protection      = false
  redis_node_type          = "cache.t4g.micro"
  redis_num_cache_clusters = 1
  audit_retention_days     = 30

  tags = local.common_tags
}

module "edge" {
  source = "../../modules/edge"

  name_prefix         = local.name_prefix
  vpc_id              = module.network.vpc_id
  public_subnet_ids   = module.network.public_subnet_ids
  root_domain         = var.root_domain
  route53_zone_id     = var.route53_zone_id
  waf_acl_arn         = module.security.alb_waf_acl_arn
  logs_bucket_name    = module.data.s3_bucket_names["logs"]
  deletion_protection = false

  tags = local.common_tags
}

module "compute" {
  source = "../../modules/compute"

  name_prefix              = local.name_prefix
  env                      = local.env
  region                   = var.region
  vpc_id                   = module.network.vpc_id
  private_app_subnet_ids   = module.network.private_app_subnet_ids
  alb_security_group_id    = module.edge.alb_security_group_id
  litellm_target_group_arn = module.edge.litellm_target_group_arn
  audit_bucket_arn         = module.data.s3_bucket_arns["audit"]

  litellm_image_uri     = var.litellm_image_uri
  litellm_desired_count = 1
  litellm_max_capacity  = 3

  tags = local.common_tags
}

module "observability" {
  source = "../../modules/observability"

  name_prefix             = local.name_prefix
  alb_arn_suffix          = split("/", module.edge.alb_dns_name)[0]
  rds_cluster_identifier  = "${local.name_prefix}-aurora"
  rds_acu_alert_threshold = 0.8
  enable_guardduty        = false

  tags = local.common_tags
}
