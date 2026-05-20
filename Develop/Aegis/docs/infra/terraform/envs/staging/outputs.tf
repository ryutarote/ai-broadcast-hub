output "vpc_id" {
  value = module.network.vpc_id
}

output "alb_dns_name" {
  value = module.edge.alb_dns_name
}

output "ecs_cluster_name" {
  value = module.compute.cluster_name
}

output "aurora_endpoint" {
  value = module.data.aurora_cluster_endpoint
}
