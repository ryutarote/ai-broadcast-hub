###############################################################################
# Data Module: RDS Aurora, ElastiCache Redis, S3 buckets
###############################################################################

###############################################################################
# Aurora PostgreSQL Serverless v2
###############################################################################

resource "aws_db_subnet_group" "aurora" {
  name       = "${var.name_prefix}-aurora-subnet-group"
  subnet_ids = var.private_data_subnet_ids

  tags = merge(var.tags, { Name = "${var.name_prefix}-aurora-subnet-group" })
}

resource "aws_security_group" "aurora" {
  name        = "${var.name_prefix}-aurora-sg"
  description = "SG for Aurora PostgreSQL"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = var.app_security_group_ids
    description     = "PostgreSQL from app tier"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-aurora-sg" })
}

resource "random_password" "aurora_master" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "aurora_master" {
  name       = "/${var.name_prefix}/db/main"
  kms_key_id = var.kms_secrets_key_arn

  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "aurora_master" {
  secret_id = aws_secretsmanager_secret.aurora_master.id
  secret_string = jsonencode({
    username = "aegis_master"
    password = random_password.aurora_master.result
  })
}

resource "aws_rds_cluster" "aurora" {
  cluster_identifier      = "${var.name_prefix}-aurora"
  engine                  = "aurora-postgresql"
  engine_mode             = "provisioned"
  engine_version          = "16.4"
  database_name           = "aegis"
  master_username         = "aegis_master"
  master_password         = random_password.aurora_master.result
  db_subnet_group_name    = aws_db_subnet_group.aurora.name
  vpc_security_group_ids  = [aws_security_group.aurora.id]
  storage_encrypted       = true
  kms_key_id              = var.kms_rds_key_arn
  backup_retention_period = var.backup_retention_days
  preferred_backup_window = "16:00-17:00" # JST 01:00-02:00
  deletion_protection     = var.deletion_protection
  skip_final_snapshot     = !var.deletion_protection
  final_snapshot_identifier = var.deletion_protection ? "${var.name_prefix}-aurora-final-${formatdate("YYYYMMDDhhmm", timestamp())}" : null

  serverlessv2_scaling_configuration {
    min_capacity = var.aurora_min_acu
    max_capacity = var.aurora_max_acu
  }

  enabled_cloudwatch_logs_exports = ["postgresql"]

  tags = merge(var.tags, { Name = "${var.name_prefix}-aurora" })

  lifecycle {
    ignore_changes = [
      master_password,
      final_snapshot_identifier,
    ]
  }
}

resource "aws_rds_cluster_instance" "aurora" {
  count                = var.aurora_instance_count
  identifier           = "${var.name_prefix}-aurora-${count.index}"
  cluster_identifier   = aws_rds_cluster.aurora.id
  instance_class       = "db.serverless"
  engine               = aws_rds_cluster.aurora.engine
  engine_version       = aws_rds_cluster.aurora.engine_version
  db_subnet_group_name = aws_db_subnet_group.aurora.name
  performance_insights_enabled = true
  performance_insights_kms_key_id = var.kms_rds_key_arn

  tags = var.tags
}

###############################################################################
# ElastiCache Redis
###############################################################################

resource "aws_elasticache_subnet_group" "redis" {
  name       = "${var.name_prefix}-redis-subnet"
  subnet_ids = var.private_data_subnet_ids

  tags = var.tags
}

resource "aws_security_group" "redis" {
  name        = "${var.name_prefix}-redis-sg"
  description = "SG for ElastiCache Redis"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = var.app_security_group_ids
    description     = "Redis from app tier"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-redis-sg" })
}

resource "random_password" "redis_auth" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "redis_auth" {
  name       = "/${var.name_prefix}/redis/auth"
  kms_key_id = var.kms_secrets_key_arn

  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "redis_auth" {
  secret_id     = aws_secretsmanager_secret.redis_auth.id
  secret_string = random_password.redis_auth.result
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id       = "${var.name_prefix}-redis"
  description                = "Redis for ${var.name_prefix}"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = var.redis_node_type
  port                       = 6379
  parameter_group_name       = "default.redis7"
  subnet_group_name          = aws_elasticache_subnet_group.redis.name
  security_group_ids         = [aws_security_group.redis.id]
  num_cache_clusters         = var.redis_num_cache_clusters
  automatic_failover_enabled = var.redis_num_cache_clusters > 1
  multi_az_enabled           = var.redis_num_cache_clusters > 1
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = random_password.redis_auth.result
  apply_immediately          = false

  tags = merge(var.tags, { Name = "${var.name_prefix}-redis" })
}

###############################################################################
# S3 Buckets
###############################################################################

locals {
  buckets = {
    audit    = { versioning = true, lifecycle_glacier_days = 90, lifecycle_expire_days = var.audit_retention_days }
    reports  = { versioning = true, lifecycle_glacier_days = null, lifecycle_expire_days = null }
    backups  = { versioning = true, lifecycle_glacier_days = 30, lifecycle_expire_days = 365 }
    logs     = { versioning = false, lifecycle_glacier_days = 90, lifecycle_expire_days = 365 }
  }
}

resource "aws_s3_bucket" "this" {
  for_each = local.buckets
  bucket   = "${var.name_prefix}-${each.key}-${var.account_id}"

  tags = merge(var.tags, {
    Name    = "${var.name_prefix}-${each.key}"
    Purpose = each.key
  })
}

resource "aws_s3_bucket_versioning" "this" {
  for_each = { for k, v in local.buckets : k => v if v.versioning }
  bucket   = aws_s3_bucket.this[each.key].id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_s3_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each                = aws_s3_bucket.this
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "this" {
  for_each = { for k, v in local.buckets : k => v if v.lifecycle_glacier_days != null }
  bucket   = aws_s3_bucket.this[each.key].id

  rule {
    id     = "transition-and-expire"
    status = "Enabled"

    filter {}

    transition {
      days          = each.value.lifecycle_glacier_days
      storage_class = "GLACIER"
    }

    dynamic "expiration" {
      for_each = each.value.lifecycle_expire_days != null ? [1] : []
      content {
        days = each.value.lifecycle_expire_days
      }
    }
  }
}
