output "aurora_cluster_endpoint" {
  value = aws_rds_cluster.aurora.endpoint
}

output "aurora_reader_endpoint" {
  value = aws_rds_cluster.aurora.reader_endpoint
}

output "aurora_db_name" {
  value = aws_rds_cluster.aurora.database_name
}

output "aurora_secret_arn" {
  value = aws_secretsmanager_secret.aurora_master.arn
}

output "aurora_security_group_id" {
  value = aws_security_group.aurora.id
}

output "redis_primary_endpoint" {
  value = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "redis_auth_secret_arn" {
  value = aws_secretsmanager_secret.redis_auth.arn
}

output "s3_bucket_names" {
  value = { for k, v in aws_s3_bucket.this : k => v.bucket }
}

output "s3_bucket_arns" {
  value = { for k, v in aws_s3_bucket.this : k => v.arn }
}
