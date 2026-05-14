###############################################################################
# Aegis Production Environment
###############################################################################

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
  }

  # backend.tf を別ファイルとして配置（コミット対象、{ACCOUNT_ID}埋め込み済み）
}

data "aws_caller_identity" "current" {}

locals {
  name_prefix = "aegis-prod"
  account_id  = data.aws_caller_identity.current.account_id
  env         = "prod"

  common_tags = {
    Project    = "aegis"
    Env        = local.env
    Owner      = "engineering"
    CostCenter = "ai-ops"
    Tier       = "critical"
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = local.common_tags
  }
}

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  default_tags { tags = local.common_tags }
}

###############################################################################
# Modules
###############################################################################

module "network" {
  source = "../../modules/network"

  name_prefix       = local.name_prefix
  region            = var.region
  vpc_cidr          = "10.0.0.0/16"
  nat_gateway_count = 2
  enable_flow_logs  = true
  tags              = local.common_tags
}

module "security" {
  source = "../../modules/security"

  name_prefix        = local.name_prefix
  enable_github_oidc = true
  github_repo        = var.github_repo
  waf_rate_limit     = 5000
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
  aurora_max_acu           = 4
  aurora_instance_count    = 2
  backup_retention_days    = 14
  deletion_protection      = true
  redis_node_type          = "cache.t4g.micro"
  redis_num_cache_clusters = 2
  audit_retention_days     = 400

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
  deletion_protection = true

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

  # TODO: ECR repository を作成し image URI を埋める
  litellm_image_uri     = var.litellm_image_uri
  litellm_desired_count = 2
  litellm_max_capacity  = 10

  tags = local.common_tags
}

module "observability" {
  source = "../../modules/observability"

  name_prefix             = local.name_prefix
  alb_arn_suffix          = split("/", module.edge.alb_dns_name)[0] # placeholder
  rds_cluster_identifier  = "${local.name_prefix}-aurora"
  rds_acu_alert_threshold = 3
  enable_guardduty        = true

  tags = local.common_tags
}
