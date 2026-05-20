###############################################################################
# Security Module: KMS, IAM (GitHub OIDC), WAF
###############################################################################

###############################################################################
# KMS Keys
###############################################################################

resource "aws_kms_key" "rds" {
  description             = "KMS key for RDS encryption (${var.name_prefix})"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = merge(var.tags, { Name = "${var.name_prefix}-kms-rds" })
}

resource "aws_kms_alias" "rds" {
  name          = "alias/${var.name_prefix}-rds"
  target_key_id = aws_kms_key.rds.key_id
}

resource "aws_kms_key" "s3" {
  description             = "KMS key for S3 encryption (${var.name_prefix})"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = merge(var.tags, { Name = "${var.name_prefix}-kms-s3" })
}

resource "aws_kms_alias" "s3" {
  name          = "alias/${var.name_prefix}-s3"
  target_key_id = aws_kms_key.s3.key_id
}

resource "aws_kms_key" "secrets" {
  description             = "KMS key for Secrets Manager (${var.name_prefix})"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = merge(var.tags, { Name = "${var.name_prefix}-kms-secrets" })
}

resource "aws_kms_alias" "secrets" {
  name          = "alias/${var.name_prefix}-secrets"
  target_key_id = aws_kms_key.secrets.key_id
}

# 顧客ペイロード（プロンプト/レスポンス）専用キー。最小権限で管理。
resource "aws_kms_key" "customer_payload" {
  description             = "KMS key for customer LLM payload (${var.name_prefix})"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  # TODO: key_policy で aegis-litellm-proxy-task のみ Decrypt 許可
  tags = merge(var.tags, { Name = "${var.name_prefix}-kms-customer-payload" })
}

resource "aws_kms_alias" "customer_payload" {
  name          = "alias/${var.name_prefix}-customer-payload"
  target_key_id = aws_kms_key.customer_payload.key_id
}

###############################################################################
# GitHub OIDC Provider
###############################################################################

data "tls_certificate" "github_oidc" {
  count = var.enable_github_oidc ? 1 : 0
  url   = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github" {
  count = var.enable_github_oidc ? 1 : 0

  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github_oidc[0].certificates[0].sha1_fingerprint]

  tags = merge(var.tags, { Name = "github-oidc" })
}

resource "aws_iam_role" "github_deploy" {
  count = var.enable_github_oidc ? 1 : 0
  name  = "${var.name_prefix}-github-deploy"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.github[0].arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:*"
        }
      }
    }]
  })

  tags = var.tags
}

# TODO: GitHub deploy ロールに必要な権限 (ECR Push, ECS UpdateService, etc.) を attach

###############################################################################
# WAF Web ACL（ALB 用）
###############################################################################

resource "aws_wafv2_web_acl" "alb" {
  name  = "${var.name_prefix}-alb-waf"
  scope = "REGIONAL"

  default_action {
    allow {}
  }

  # AWS マネージドルール: Common
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesCommonRuleSet"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "CommonRuleSet"
      sampled_requests_enabled   = true
    }
  }

  # AWS マネージドルール: 既知の不正入力
  rule {
    name     = "AWSManagedRulesKnownBadInputsRuleSet"
    priority = 2

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "KnownBadInputs"
      sampled_requests_enabled   = true
    }
  }

  # レート制限
  rule {
    name     = "RateLimitPerIp"
    priority = 10

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = var.waf_rate_limit
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "RateLimit"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.name_prefix}-alb-waf"
    sampled_requests_enabled   = true
  }

  tags = var.tags
}
