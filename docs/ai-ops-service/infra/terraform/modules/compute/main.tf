###############################################################################
# Compute Module: ECS Cluster + Services
# 簡素化のため、本ファイルでは ECS Cluster と LiteLLM Proxy サービスのみを定義し、
# その他のサービス（Control Plane, Langfuse, Workers, ClickHouse）は同パターンで
# 別ファイル（services_*.tf）として実装時に追加する。
###############################################################################

###############################################################################
# ECS Cluster
###############################################################################

resource "aws_ecs_cluster" "this" {
  name = "${var.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enhanced"
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-cluster" })
}

resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name       = aws_ecs_cluster.this.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 1
  }
}

###############################################################################
# Service Discovery（内部DNS）
###############################################################################

resource "aws_service_discovery_private_dns_namespace" "this" {
  name        = "${var.name_prefix}.internal"
  description = "Private DNS namespace for Aegis services"
  vpc         = var.vpc_id
  tags        = var.tags
}

###############################################################################
# CloudWatch Log Group
###############################################################################

resource "aws_cloudwatch_log_group" "app" {
  for_each          = toset(var.service_names)
  name              = "/aws/ecs/${var.name_prefix}/${each.key}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

###############################################################################
# Common IAM Role（タスク実行ロール = ECRからのpull、ログ書込）
###############################################################################

resource "aws_iam_role" "task_execution" {
  name = "${var.name_prefix}-task-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "task_execution_secrets" {
  name = "secrets-read"
  role = aws_iam_role.task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue",
        "kms:Decrypt"
      ]
      Resource = "*"
    }]
  })
}

###############################################################################
# Common SG（タスクが ALB から受ける）
###############################################################################

resource "aws_security_group" "task" {
  name        = "${var.name_prefix}-task-sg"
  description = "SG for ECS tasks"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-task-sg" })
}

resource "aws_security_group_rule" "task_ingress_from_alb" {
  type                     = "ingress"
  from_port                = 0
  to_port                  = 65535
  protocol                 = "tcp"
  security_group_id        = aws_security_group.task.id
  source_security_group_id = var.alb_security_group_id
  description              = "Allow ALB to reach tasks"
}

###############################################################################
# LiteLLM Proxy Task & Service（代表例）
###############################################################################

resource "aws_iam_role" "litellm_task" {
  name = "${var.name_prefix}-litellm-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "litellm_task" {
  name = "litellm-permissions"
  role = aws_iam_role.litellm_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        # TODO: テナント別 secret のみに絞る
        Resource = "arn:aws:secretsmanager:*:*:secret:/${var.name_prefix}/tenants/*"
      },
      {
        Effect = "Allow"
        Action = ["kms:Decrypt"]
        # TODO: customer_payload key ARN に絞る
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject"
        ]
        Resource = "${var.audit_bucket_arn}/*"
      }
    ]
  })
}

resource "aws_ecs_task_definition" "litellm" {
  family                   = "${var.name_prefix}-litellm"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.litellm_cpu
  memory                   = var.litellm_memory
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.litellm_task.arn

  container_definitions = jsonencode([
    {
      name      = "litellm"
      image     = "${var.litellm_image_uri}" # TODO: ECRリポジトリARN
      essential = true
      portMappings = [{
        containerPort = 4000
        hostPort      = 4000
        protocol      = "tcp"
      }]
      environment = [
        { name = "AEGIS_ENV", value = var.env },
        { name = "AWS_REGION", value = var.region }
      ]
      secrets = [
        # TODO: マスターキー等
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app["litellm"].name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "litellm"
        }
      }
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:4000/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = var.tags

  lifecycle {
    ignore_changes = [container_definitions] # CI で更新するため
  }
}

resource "aws_ecs_service" "litellm" {
  name                               = "litellm"
  cluster                            = aws_ecs_cluster.this.id
  task_definition                    = aws_ecs_task_definition.litellm.arn
  desired_count                      = var.litellm_desired_count
  launch_type                        = "FARGATE"
  platform_version                   = "LATEST"
  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = 60

  network_configuration {
    subnets          = var.private_app_subnet_ids
    security_groups  = [aws_security_group.task.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = var.litellm_target_group_arn
    container_name   = "litellm"
    container_port   = 4000
  }

  service_registries {
    registry_arn = aws_service_discovery_service.litellm.arn
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }

  tags = var.tags
}

resource "aws_service_discovery_service" "litellm" {
  name = "litellm"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.this.id

    dns_records {
      ttl  = 10
      type = "A"
    }

    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }

  tags = var.tags
}

###############################################################################
# Auto Scaling（LiteLLM代表例）
###############################################################################

resource "aws_appautoscaling_target" "litellm" {
  max_capacity       = var.litellm_max_capacity
  min_capacity       = var.litellm_desired_count
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.litellm.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "litellm_cpu" {
  name               = "${var.name_prefix}-litellm-cpu-target"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.litellm.resource_id
  scalable_dimension = aws_appautoscaling_target.litellm.scalable_dimension
  service_namespace  = aws_appautoscaling_target.litellm.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 70
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}
