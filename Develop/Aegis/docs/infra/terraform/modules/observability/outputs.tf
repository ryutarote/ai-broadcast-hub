output "sns_critical_arn" {
  value = aws_sns_topic.critical.arn
}

output "sns_warn_arn" {
  value = aws_sns_topic.warn.arn
}

output "guardduty_detector_id" {
  value = try(aws_guardduty_detector.this[0].id, null)
}
