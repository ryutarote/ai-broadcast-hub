output "kms_rds_key_arn" {
  value = aws_kms_key.rds.arn
}

output "kms_s3_key_arn" {
  value = aws_kms_key.s3.arn
}

output "kms_secrets_key_arn" {
  value = aws_kms_key.secrets.arn
}

output "kms_customer_payload_key_arn" {
  value = aws_kms_key.customer_payload.arn
}

output "alb_waf_acl_arn" {
  value = aws_wafv2_web_acl.alb.arn
}

output "github_deploy_role_arn" {
  value = try(aws_iam_role.github_deploy[0].arn, null)
}
