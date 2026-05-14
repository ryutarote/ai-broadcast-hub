###############################################################################
# Observability Module: CloudWatch Alarms, SNS, GuardDuty
###############################################################################

###############################################################################
# SNS Topics
###############################################################################

resource "aws_sns_topic" "critical" {
  name              = "${var.name_prefix}-alerts-critical"
  kms_master_key_id = "alias/aws/sns"
  tags              = var.tags
}

resource "aws_sns_topic" "warn" {
  name              = "${var.name_prefix}-alerts-warn"
  kms_master_key_id = "alias/aws/sns"
  tags              = var.tags
}

# Slack 連携は AWS Chatbot or 自前 Lambda Subscriber を使用。本モジュールでは Topic のみ作成。

###############################################################################
# CloudWatch Alarms（代表例）
###############################################################################

resource "aws_cloudwatch_metric_alarm" "alb_5xx_high" {
  alarm_name          = "${var.name_prefix}-alb-5xx-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "ALB 5xx errors elevated"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = var.alb_arn_suffix
  }

  alarm_actions = [aws_sns_topic.critical.arn]
  ok_actions    = [aws_sns_topic.critical.arn]

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "alb_target_response_time_p99" {
  alarm_name          = "${var.name_prefix}-alb-latency-p99"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "TargetResponseTime"
  namespace           = "AWS/ApplicationELB"
  period              = 300
  extended_statistic  = "p99"
  threshold           = 1.0
  alarm_description   = "ALB p99 latency elevated"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = var.alb_arn_suffix
  }

  alarm_actions = [aws_sns_topic.warn.arn]

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "rds_cpu_high" {
  alarm_name          = "${var.name_prefix}-rds-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 5
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "RDS CPU sustained high"

  dimensions = {
    DBClusterIdentifier = var.rds_cluster_identifier
  }

  alarm_actions = [aws_sns_topic.warn.arn]

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "rds_acu_high" {
  alarm_name          = "${var.name_prefix}-rds-acu-near-max"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 5
  metric_name         = "ServerlessDatabaseCapacity"
  namespace           = "AWS/RDS"
  period              = 60
  statistic           = "Average"
  threshold           = var.rds_acu_alert_threshold
  alarm_description   = "RDS ACU sustained near max"

  dimensions = {
    DBClusterIdentifier = var.rds_cluster_identifier
  }

  alarm_actions = [aws_sns_topic.warn.arn]

  tags = var.tags
}

###############################################################################
# GuardDuty
###############################################################################

resource "aws_guardduty_detector" "this" {
  count  = var.enable_guardduty ? 1 : 0
  enable = true

  datasources {
    s3_logs {
      enable = true
    }
    kubernetes {
      audit_logs {
        enable = false
      }
    }
    malware_protection {
      scan_ec2_instance_with_findings {
        ebs_volumes {
          enable = false # 必要に応じて
        }
      }
    }
  }

  tags = var.tags
}

###############################################################################
# Synthetic Canary（gw.aegis.jp 死活監視、シンプルな例）
###############################################################################

# Canary は別途 ZIP コードのアップロードが必要なため、TODO として残す。
# 推奨：本番ローンチ前に CloudWatch Synthetics を Console 経由で作成 → Terraform に取り込む。

###############################################################################
# Outputs
###############################################################################
