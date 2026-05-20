output "cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "cluster_arn" {
  value = aws_ecs_cluster.this.arn
}

output "task_security_group_id" {
  value = aws_security_group.task.id
}

output "litellm_service_name" {
  value = aws_ecs_service.litellm.name
}

output "service_discovery_namespace_id" {
  value = aws_service_discovery_private_dns_namespace.this.id
}
